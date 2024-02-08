import time
from typing import Sequence

import pyvisa
import numpy

from pyvisa import constants

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
		self.rm: pyvisa.ResourceManager = None # type: ignore
		self.sc: pyvisa.resources.MessageBasedResource = None # type: ignore

		# Local storage for the internal trigger instance
		self._trig = trig_type
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

	def con(self, ip: str = '', socket: bool = True, **kwargs) -> bool:
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
			socket (bool): Use socket connection instead of VISA
			kwargs: Additional arguments to pass to pyvisa.ResourceManager.open_resource

		Returns:
			True if successful, False otherwise

		Raises:
			ValueError: IP address must be specified
			OSError: Invalid vendor or model returned from scope
		'''

		if not ip:
			raise ValueError('IP address must be specified')

		self.rm = pyvisa.ResourceManager()
		if socket:
			self.sc = self.rm.open_resource(f'TCPIP::{ip}::4000::SOCKET', kwargs) # type: ignore
			self.sc.read_termination = '\n'
			self.sc.write_termination = '\n'
		else:
			self.sc = self.rm.open_resource(f'TCPIP::{ip}::INSTR') # type: ignore

		# Set visa timeout
		self.timeout = self._timeout

		self.sc.clear() # Clear buffers
		self.sc.write('*CLS') # Clear event queue, standard event status register, status byte register

		sc_id = self._id_scope()
		if sc_id['vendor'] != 'TEKTRONIX':
			self.dis()
			raise OSError(f'Invalid vendor returned from scope {sc_id["vendor"]}')
		if sc_id['model'] not in ['MSO44', 'MSO46']:
			self.dis()
			raise OSError(f'Invalid model returned from scope {sc_id["model"]}')

		self.connect_status = True

		# Configure scope environment
		try:
			# Init additional scope classes
			self.trigger = self._trig
			self.acq = MSO4Acquisition(self.sc)
			ch_a_num = int(sc_id['model'][-1]) # Hacky, I know, but even Tektronix people suggest it
			# Source: https://forum.tek.com/viewtopic.php?f=568&t=135345
			for ch_a in range(ch_a_num):
				self.ch_a.append(MSO4AnalogChannel(self.sc, ch_a + 1))

			# Enable all events reporting in the status register
			self.sc.write('DESE 255')

			# Clear: Event Queue, Standard Event Status Register, Status Byte Register
			self.sc.write('*CLS')

			# Configure waveform data
			# NOTE the DATA:ENCdg command is broken in the MSO44 firmware version 2.0.3.950
			self.acq.wfm_encoding = 'binary'
			self.acq.wfm_binary_format = 'ri' # Signed integer
			# NOTE floating point seems to be rejected in the MSO44 firmware version 2.0.3.950
			self.acq.wfm_byte_order = 'lsb' # Easier to work with little endian because numpy
			self.acq.wfm_byte_nr = 2 # 16-bit

			# Set waveform start and stop (retrieve all data)
			self.acq.wfm_start = 1
			self.acq.wfm_stop = self.acq.horiz_record_length
		except Exception:
			self.dis()
			raise

		return True

	def dis(self) -> bool:
		'''Disconnects from scope.
		'''
		# Re enable waveform display
		self.sc.clear()
		self.sc.write('*CLS') # Clear event queue, standard event status register, status byte register
		if self.acq:
			self.acq.display = True
		self.acq = None # type: ignore

		self.sc.close()
		self.sc = None # type: ignore
		self.rm.close()
		self.rm = None # type: ignore

		self.ch_a = []
		self.wfm_data_points = []

		self.connect_status = False
		return True

	def reset(self) -> None:
		'''Resets scope to default settings.
		'''
		self.sc.write("*RST")
		self.sc.write("*OPC?")
		for _ in range(100):
			if int(self.sc.read()) == 1:
				break
		else:
			raise OSError('Failed to reset scope')

	def clear(self) -> None:
		'''Clears all acquisitions, measurements, and waveforms.
		'''
		self.sc.write('CLEAR')

	def arm(self) -> None:
		'''Setup scope to begin capture/glitching when triggered.

		The scope must be armed before capture or glitching (when set to
		'ext_single') can begin.

		Raises:
			OSError: Scope isn't connected.
			Exception: Error when arming. This method catches these and
				disconnects before reraising them.
		'''

		if self.connect_status is False:
			raise OSError('Scope is not connected. Connect it first...')

		if self.acq and self.acq.curvestream:
			return # We're already in curvestream mode

		try:
			self.sc.write('ACQuire:STATE 10000') # Acquire 10000 traces # TODO is 100 a good idea?

			# Wait for the scope to arm
			for _ in range(10):
				state = self.sc.query('ACQuire:STATE?').strip()
				if '1' in state:
					# But is it really armed? Read at the end of the function...
					break
				time.sleep(0.05)
			else:
				raise OSError('Failed to arm scope')
		except Exception:
			self.dis()
			raise
		time.sleep(0.05) # Wait for the scope to *actually* arm
		# Tektronix is playing games with us

		# Enable curvestream mode
		self.acq.curvestream = True

	def capture(self):
		'''Captures trace. Scope must be armed before capturing.

		Blocks until scope triggered (or times out),
		then disarms scope and copies data back.

		Read captured data out with :code:`scope.get_last_trace()`

		Returns:
			True if capture was successful, False if it timed out.

		Raises:
		   IOError: Unknown failure.
		'''
		self.acq.configured() # Check that the scope is configured

		# Read the data
		raw_data: Sequence = []
		try:
			raw_data = self.sc.read_raw()
		except pyvisa.errors.VisaIOError as e:
			if e.error_code == constants.StatusCode.error_timeout:
				return False
			else:
				raise

		if raw_data == self.wfm_data_points:
			# We actually timed out and got the same data twice
			return False
		else:
			self.wfm_data_points = raw_data

		return True

	def get_last_trace(self, as_int: bool = False):
		'''Returns the scope data read by capture()

		Returns:
			A numpy array containing the scope data.
		'''
		# Got these from the programmer manual § WFMOutpre:BN_Fmt
		types = {
			1: {'ri': 'b', 'rp': 'B'},
			2: {'ri': 'h', 'rp': 'H'},
			4: {'ri': 'i', 'rp': 'I', 'fp': 'f'},
			8: {'ri': 'q', 'rp': 'Q', 'fp': 'd'},
		}
		endianess = ">" if self.acq.wfm_byte_order == 'msb' else "<"
		datatype = types[self.acq.wfm_byte_nr][self.acq.wfm_binary_format]
		array_length = int(len(self.wfm_data_points) / self.acq.wfm_byte_nr)
		return numpy.frombuffer(self.wfm_data_points, endianess + datatype, array_length, offset=0)

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
	
