import pyvisa as visa
import usbtmc

from . import scope_logger
from .triggers import MSO4Triggers, MSO4EdgeTrigger
from .acquisition import MSO4Acquisition
from .channel import MSO4AnalogChannel

# TODO:
# * Implement the other trigger types (mostly sequence)
# * Change binary format to 8 bit when in low res mode?
# * Add note about starting off with a freshly booted machine to avoid issues

TEKTRONIX_USB_VID = 0x0699
MSO44_USB_PID = 0x0527

class MSO4:
	'''Tektronix MSO 4-Series scope object. This is not usable until :func:`MSO4.con()` is called.'''

	_pyvisa_methods = ['write', 'write_ascii_values', 'write_binary_values',
		'read_bytes', 'read', 'read_ascii_values', 'read_binary_values', 'query',
		'query_ascii_values', 'query_binary_values'] # Ignore write_raw and read_raw as
		# they are used in all the methods above, thus everything would be printed twice

	def __init__(self, trig_type: MSO4Triggers = MSO4EdgeTrigger, timeout: float = 2000.0, debug: bool = False):
		'''Creates a new MSO4 object.

		Args:
			trig_type: The type of trigger to use. This can be changed later.
			timeout: Timeout (in ms) for each VISA operation, including the CURVE? query.
			debug: Enable printing each VISA operation to the console
		'''
		#: pyvisa ResourceManager object used tp setup the connection
		self.rm: visa.ResourceManager = None # type: ignore
		#: pyvisa MessageBasedResource object used to communicate with the scope
		self.sc: visa.resources.MessageBasedResource = None # type: ignore

		# Temporary storage until `con()` is called
		self._trig_type: MSO4Triggers = trig_type # Trigger TYPE container
		self._trig: MSO4Triggers = None # Trigger INSTANCE container # type: ignore
		self._timeout = timeout # Don't read: use self.sc.timeout instead

		#: MSO4Acquisition instance used to control the acquisition settings
		self.acq: MSO4Acquisition = None # type: ignore
		#: List of MSO4AnalogChannel instances used to control the analog channels
		self.ch_a: list[MSO4AnalogChannel] = []
		self.ch_a.append(None) # Dummy channel to make indexing easier # type: ignore

		#: Debug mode
		self.debug: bool = debug
		#: Current connection status
		self.connect_status: bool = False

	def clear_cache(self) -> None:
		'''Resets the local configuration cache so that values will be fetched from
		the scope. Is recursively called on all subobjects (trigger, acquisition, channels).

		This is useful when the scope configuration is (potentially) changed externally.
		'''
		if self._trig:
			self._trig.clear_caches()
		if self.acq:
			self.acq.clear_caches()
		for ch in self.ch_a:
			if ch:
				ch.clear_caches()

	def _id_scope(self) -> dict[str, str]:
		'''Reads identification string from scope and returns a dictionary with the
		following keys:
			- vendor
			- model
			- serial
			- firmware

		Raises:
			Exception: Error when arming. This method catches these and
				disconnects before reraising them.
		'''

		try:
			idn = self.sc.query('*IDN?') # TEKTRONIX,MSO44,C019654,CF:91.1CT FV:2.0.3.950
		except Exception:
			self.dis()
			raise

		s = idn.split(',')
		if len(s) != 4:
			raise OSError(f'Invalid IDN string returned from scope: {idn}')
		return {
			'vendor': s[0],
			'model': s[1],
			'serial': s[2],
			'firmware': s[3]
		}

	def con(self, ip: str = '', usb_addr: str = '', **kwargs) -> bool:
		'''Connects to scope and resets it. It will also:
			- timeout = timeout from init
			- clear event queue, standard event status register, status byte register

		To obtain the USB VISA resource string, you can use the list command in ``pyvisa-shell``
		(binary provided by pyvisa), see
		https://pyvisa.readthedocs.io/en/latest/introduction/names.html#visa-resource-syntax-and-examples
		for more information.

		Args:
			ip (str): IP address of scope
			usb_addr (str): VISA resource string for USB connection
			kwargs: Additional arguments to pass to ``pyvisa.ResourceManager.open_resource``

		Returns:
			True if successful, False otherwise

		Raises:
			ValueError: IP address must be specified
			OSError: Invalid vendor or model returned from scope
		'''

		def _decorator_print(func):
			'''Decorator added to pyvisa functions to debug what is happening at a lower level.
			It is a nested function to have access to the pyMSO4 class instance context
			'''
			def wrapper(*args, **kwargs):
				if self.debug: # This is why I declared here
					print("[D]", func.__name__, *args)
				return func(*args, **kwargs)
			return wrapper

		if self.connect_status:
			try:
				self.dis()
			except Exception:
				scope_logger.warning('Failed to disconnect from scope. Trying to connect anyway...')

		self.rm = visa.ResourceManager()
		if ip and usb_addr:
			raise ValueError('Only one of IP address or USB resource string must be specified')
		elif ip:
			self.sc = self.rm.open_resource(f'TCPIP0::{ip}::inst0::INSTR', **kwargs) # type: ignore
		elif usb_addr:
			self.sc = self.rm.open_resource(usb_addr, **kwargs) # type: ignore
		else:
			raise ValueError('Either IP address or USB resource string must be specified')

		# Apply debugging decorator
		for method in self._pyvisa_methods:
			setattr(self.sc, method, _decorator_print(getattr(self.sc, method)))

		# Set visa timeout
		self.timeout = self._timeout

		# Reset scope
		self.reset()

		sc_id = self._id_scope()
		if sc_id['vendor'] != 'TEKTRONIX':
			self.dis()
			raise OSError(f'Invalid vendor returned from scope {sc_id["vendor"]}')
		if sc_id['model'] not in ['MSO44', 'MSO46']:
			self.dis()
			raise OSError(f'Invalid model returned from scope {sc_id["model"]}')

		self.connect_status = True

		# Init additional scope classes
		ch_a_num = int(sc_id['model'][-1]) # Hacky, I know, but even Tektronix people suggest it
		# Source: https://forum.tek.com/viewtopic.php?f=568&t=135345
		for ch_a in range(ch_a_num):
			self.ch_a.append(MSO4AnalogChannel(self.sc, ch_a + 1))
		self.trigger = self._trig_type
		self.acq = MSO4Acquisition(self.sc, ch_a_num)

		return True

	def dis(self) -> None:
		'''Disconnects from scope and clears all local data.
		'''
		# Re enable waveform display
		self.clear_buffers()
		self.cls()
		self.display = True

		self.clear_cache()

		self.acq = None # type: ignore

		self.sc.close()
		self.sc = None # type: ignore
		self.rm.close()
		self.rm = None # type: ignore

		self.ch_a = []
		self.ch_a.append(None) # Dummy channel to make indexing easier # type: ignore

		self.connect_status = False

	def reboot(self) -> None:
		'''Reboots the UI (as well as VISA server) on the scope. Note this will kill the current connection
		'''
		self.sc.write('SCOPEApp REBOOT')
		self.clear_cache()
		self.acq = None # type: ignore

		self.sc.close()
		self.sc = None # type: ignore
		self.rm.close()
		self.rm = None # type: ignore

		self.ch_a = []
		self.ch_a.append(None) # Dummy channel to make indexing easier # type: ignore

		self.connect_status = False

	def reset(self) -> None:
		'''Resets scope to default settings.
		'''
		self.sc.write("*RST")
		self.sc.write("*OPC?")
		# Technically we could use "*OPC" to avoid the scope sending data on the bus, but
		# that actually does not work, so we need to use "*OPC?" and read
		while self.sc.read().strip() != "1":
			pass
		self.sc.clear() # Discard the `1` sent by the scope
		self.sc.write("*CLS")

	def cls(self) -> None:
		'''Clears event queue, standard event status register, status byte register.
		'''
		self.sc.write('*CLS')

	def clear_cmd(self) -> None:
		'''Clears all acquisitions, measurements, and waveforms.
		'''
		self.sc.write('CLEAR')

	def clear_buffers(self) -> None:
		'''Clears the resource buffers.
		'''
		self.sc.clear()

	def ch_a_enable(self, value: list[bool]) -> None:
		'''Convenience function to enable/disable analog channels.
		Will start at channel 1 and enable/disable as many channels as
		there are values in the list.'''
		for i in range(0, min(len(value), self.ch_a_num)):
			self.ch_a[i + 1].enable = value[i]

	@property
	def trigger(self) -> MSO4Triggers:
		'''Current trigger object instance.

		:Getter: Return the current trigger object instance (MSO4Triggers)

		:Setter: Instantiate a new trigger object given a MSO4Triggers type.
			Also applies the configuration to the scope.
		'''
		return self._trig
	@trigger.setter
	def trigger(self, trig_type: MSO4Triggers):
		if not self.connect_status:
			raise OSError('Scope is not connected. Connect it first...')
		if self.ch_a_num < 1:
			raise OSError('No analog channels available. Init them first...')
		self._trig = trig_type(self.sc, self.ch_a_num)

	@property
	def timeout(self) -> float:
		'''Timeout (in ms) for each VISA operation (also those that will stall on the scope end, like CURVE?).

		:Getter: Return the number of milliseconds before a timeout (float)

		:Setter: Set the timeout in milliseconds (float)
		'''
		if self.sc is None:
			raise OSError('Scope is not connected. Connect it first...')
		return self.sc.timeout
	@timeout.setter
	def timeout(self, value: float):
		if self.sc is None:
			raise OSError('Scope is not connected. Connect it first...')
		self.sc.timeout = value

	@property
	def ch_a_num(self) -> int:
		'''Number of analog channels on the scope.

		:Getter: Return the number of analog channels (int)
		'''
		if not self.connect_status:
			raise OSError('Scope is not connected. Connect it first...')
		return len(self.ch_a) - 1

	@property
	def display(self) -> bool:
		'''Enable or disable the waveform display on the scope display.

		*Not cached*

		:Getter: Return the display state (bool)

		:Setter: Set the display state (bool)
		'''
		return self.sc.query('DISplay:WAVEform?').strip().lower() == 'on'
	@display.setter
	def display(self, value: bool):
		self.sc.write(f'DISplay:WAVEform {int(value)}')

def usb_reboot(vid: int, pid: int) -> bool:
	'''Reboots the scope via USB when it is not reachable through TCP/IP.

	Args:
		usb_addr: VISA resource string for USB connection (see :func:`MSO4.con()` for more information)
	'''

	instr = usbtmc.Instrument(vid, pid) # Using python-usbtmc as pyvisa-py seems to always timeout here
	try:
		instr.write("SCOPEAPP REBOOT")
		instr.close()
	except Exception:
		# Don't act on it, because it should be rebooting anyway now
		scope_logger.warning('Failed to close USB TMC scope during reboot')
		return False
	return True
