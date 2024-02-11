import time
from typing import Sequence

import pyvisa as visa


from .triggers import MSO4Triggers, MSO4EdgeTrigger
from .acquisition import MSO4Acquisition
from .channel import MSO4AnalogChannel
from . import scope_logger

# TODO:
# * Implement the other trigger types (mostly sequence)
# * Change binary format to 8 bit when in low res mode?
# * Add note about starting off with a freshly booted machine to avoid issues
# * Add note in readme about "smart" Dell docking stations and ethernet

class MSO4:
	'''Tektronix MSO 4-Series scope object. This is not usable until `con()` is called.

	Attributes:
		rm: pyvisa.ResourceManager instance
		sc: pyvisa.resources.MessageBasedResource instance
		ch_a (list):  1-based list of MSO4AnalogChannel instances
		trigger: MSO4Triggers type (not an instance)
	'''

	sources = ['ch1', 'ch2', 'ch3', 'ch4'] # TODO add MATH_, REF_, CH_D...
	# See programmer manual § DATa:SOUrce

	def __init__(self, trig_type: MSO4Triggers = MSO4EdgeTrigger, timeout: float = 2000.0):
		'''Creates a new MSO4 object.

		Args:
			trig_type: The type of trigger to use. This can be changed later.
			timeout: Timeout (in ms) for each VISA operation, including the CURVE? query.
		'''
		self.rm: visa.ResourceManager = None # type: ignore
		self.sc: visa.resources.MessageBasedResource = None # type: ignore

		# Local storage for the internal trigger instance
		self._trig: MSO4Triggers = trig_type
		self._timeout = timeout # Never read this value, use self.sc.timeout instead, this is only temporary storage until `con()` is called
		self.acq: MSO4Acquisition = None # type: ignore

		self.ch_a: list[MSO4AnalogChannel] = []
		self.ch_a.append(None) # Dummy channel to make indexing easier # type: ignore

		self.wfm_data_points: Sequence = []

		self.connect_status = False

	def clear_cache(self) -> None:
		'''Resets the local configuration cache so that values will be fetched from
		the scope.

		This is useful when the scope configuration is (potentially) changed externally.
		'''
		if self._trig:
			self._trig.clear_caches()
		if self.acq:
			self.acq.clear_caches()
		for ch in self.ch_a:
			ch.clear_caches()
		self.wfm_data_points = []

	def _id_scope(self) -> dict:
		'''Reads identification string from scope

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

	def con(self, ip: str = '', **kwargs) -> bool:
		'''Connects to scope and sets default configuration:
			- timeout = timeout from init
			- event reporting enabled on all events
			- clear event queue, standard event status register, status byte register
			- waveform start = 1
			- waveform length = max (record length)
			- waveform encoding = binary
			- waveform binary format = signed integer
			- waveform byte order = lsb
			- waveform byte number = 2

		Args:
			ip (str): IP address of scope
			kwargs: Additional arguments to pass to pyvisa.ResourceManager.open_resource

		Returns:
			True if successful, False otherwise

		Raises:
			ValueError: IP address must be specified
			OSError: Invalid vendor or model returned from scope
		'''

		if not ip:
			raise ValueError('IP address must be specified')

		self.rm = visa.ResourceManager()
		self.sc = self.rm.open_resource(f'TCPIP0::{ip}::inst0::INSTR') # type: ignore

		# Set visa timeout
		self.timeout = self._timeout

		sc_id = self._id_scope()
		if sc_id['vendor'] != 'TEKTRONIX':
			self.dis()
			raise OSError(f'Invalid vendor returned from scope {sc_id["vendor"]}')
		if sc_id['model'] not in ['MSO44', 'MSO46']:
			self.dis()
			raise OSError(f'Invalid model returned from scope {sc_id["model"]}')

		self.connect_status = True

		# Init additional scope classes
		self.trigger = self._trig
		self.acq = MSO4Acquisition(self.sc)
		ch_a_num = int(sc_id['model'][-1]) # Hacky, I know, but even Tektronix people suggest it
		# Source: https://forum.tek.com/viewtopic.php?f=568&t=135345
		for ch_a in range(ch_a_num):
			self.ch_a.append(MSO4AnalogChannel(self.sc, ch_a + 1))

		return True

	def dis(self) -> None:
		'''Disconnects from scope and clears all local data.
		'''
		# Re enable waveform display
		self.clear_buffers()
		self.cls()
		self.display = True

		self.acq = None # type: ignore

		self.sc.close()
		self.sc = None # type: ignore
		self.rm.close()
		self.rm = None # type: ignore

		self.ch_a = []
		self.wfm_data_points = []

		self.connect_status = False

	def reboot(self) -> None:
		'''Reboots the UI (as well as VISA server) on the scope. Note this will kill the current connection
		'''
		self.sc.write('SCOPEApp REBOOT')
		self.acq = None # type: ignore

		self.sc.close()
		self.sc = None # type: ignore
		self.rm.close()
		self.rm = None # type: ignore

		self.ch_a = []
		self.wfm_data_points = []

		self.connect_status = False


	def reset(self) -> None:
		'''Resets scope to default settings.
		'''
		self.sc.write("*RST")
		self.sc.write("*OPC?")
		while self.sc.stb == 0:
			pass
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
			Also configures the scope accordingly.
		'''
		return self._trig
	@trigger.setter
	def trigger(self, trig_type: MSO4Triggers):
		if not self.connect_status:
			raise OSError('Scope is not connected. Connect it first...')
		self._trig = trig_type(self.sc)

	@property
	def timeout(self) -> float:
		'''Timeout (in ms) for each VISA operation, including the CURVE? query.

		:Getter: Return the number of milliseconds before a timeout (float)

		:Setter: Set the timeout in milliseconds (float)
		'''
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
		Not cached

		:Getter: Return the display state (bool)

		:Setter: Set the display state (bool)
		'''
		return self.sc.query('DISplay:WAVEform?').strip().lower() == 'on'
	@display.setter
	def display(self, value: bool):
		self.sc.write(f'DISplay:WAVEform {int(value)}')
