from typing import Literal
import pyvisa

from . import util
from . import scope_logger

# Taken from pyvisa.util
BINARY_DATATYPES = Literal[
    "s", "b", "B", "h", "H", "i", "I", "l", "L", "q", "Q", "f", "d"
]

class MSO4Acquisition(util.DisableNewAttr):
	'''Handle all the properties related to waveform acquisition.

	Attributes: # TODO update this list
		ch<n> (MSO4Vertical): The vertical channel settings for channel n.
		mode (str): The acquisition mode of the scope.
		stop_after (str): Wether the instrument continually acquires acquisitions or acquires a single sequence
		num_seq (int): In single sequence acquisition mode, specify the number of acquisitions or measurements that comprise the sequence.
		display (bool): Enable or disable the waveform display on the scope display.
		horiz_record_length (int): The horizontal record length of the waveform.
		wfm_src (list[str]): The analog FlexChannel(s) source(s) of the waveform.
		wfm_start (int): The starting data point for waveform transfer.
		wfm_stop (int): The last data point that will be transferred when using the CURVe? query.
		wfm_encoding (str): The encoding of the waveform data.
		wfm_binary_format (str): The data format of binary waveform data.
		wfm_byte_nr (int): The number of bytes per data point in the waveform.
		wfm_byte_order (str): The byte order of the waveform data.
	'''

	# See programmer manual for explanation of these
	modes = ['sample', 'peakdetect', 'hires', 'average', 'envelope']
	sources = ['ch1', 'ch2', 'ch3', 'ch4'] # TODO how to retrieve this from the scope?
	stop_afters = ['sequence', 'runstop']
	horiz_modes = ['auto', 'manual']
	wfm_encodings = ['binary', 'ascii']
	wfm_binary_formats = ['ri', 'rp', 'fp']
	wfm_byte_nrs = [1, 2, 8] # Programmer manual § WFMOutpre:BYT_Nr
	wfm_byte_orders = ['lsb', 'msb']
	wfm_datatypes: dict[int, dict[str, BINARY_DATATYPES]] = { # Got these from the programmer manual § WFMOutpre:BN_Fmt
		1: {'ri': 'b', 'rp': 'B'},
		2: {'ri': 'h', 'rp': 'H'},
		4: {'ri': 'i', 'rp': 'I', 'fp': 'f'},
		8: {'ri': 'q', 'rp': 'Q', 'fp': 'd'},
	}

	def __init__(self, res: pyvisa.resources.MessageBasedResource):
		super().__init__()

		self.sc: pyvisa.resources.MessageBasedResource = res

		self._cached_wfm_encoding = None
		self._cached_wfm_format = None
		self._cached_wfm_byte_nr = None
		self._cached_wfm_order = None
		self._cached_curvestream = None
		self._cached_fast_acq = None

		self.disable_newattr()

	def clear_caches(self):
		'''Resets the local configuration cache so that values will be fetched from
		the scope.

		This is useful when the scope configuration is (potentially) changed externally.
		'''
		self._cached_wfm_encoding = None
		self._cached_wfm_format = None
		self._cached_wfm_byte_nr = None
		self._cached_wfm_order = None
		self._cached_curvestream = None
		self._cached_fast_acq = None

	def configured(self) -> bool:
		'''Check if the scope have been configured for acquisition.

		Returns: True if configured, raises otherwise

		Raises: ValueError if any of the required variables are not set
		'''
		if self.curvestream:
			# Can't send any command while in curvestream mode, or it will be interrupted
			return True
		if all([self.mode, self.wfm_src, self.wfm_encoding, self.wfm_binary_format, self.wfm_byte_nr, self.wfm_byte_order]):
			return True
		raise ValueError('Variables [acq.mode, acq.src, acq.wfm_encoding, acq.wfm_binary_format, acq.wfm_byte_nr, acq.wfm_byte_order] must be set before acquisition')

	@property
	def mode(self) -> str:
		'''The acquisition mode of the scope.
		Not cached

		:Getter: Return the acquisition mode (str)

		:Setter: Set the acquisition mode. Valid modes are:
			* 'sample': SAMple specifies that the displayed data point value is the
			sampled value that is taken during the acquisition interval
			* 'peakdetect': PEAKdetect specifies the display of high-low range of the
			samples taken from a single waveform acquisition.
			* 'hires': HIRes specifies Hi Res mode where the displayed data point
			value is the average of all the samples taken during the acquisition interval
			* 'average': AVErage specifies averaging mode, in which the resulting
			waveform shows an average of SAMple data points from several separate
			waveform acquisitions.
			* 'envelope': ENVelope specifies envelope mode, where the resulting waveform
			displays the range of PEAKdetect from continued waveform acquisitions.
		'''
		return self.sc.query('ACQuire:MODe?').strip().lower()
	@mode.setter
	def mode(self, value: str):
		if value.lower() not in self.modes:
			raise ValueError(f'Invalid mode {value}. Valid modes are {self.modes}')
		self.sc.write(f'ACQuire:MODe {value}')

	@property
	def stop_after(self) -> str:
		'''Wether the instrument continually acquires acquisitions or acquires a single sequence
		Not cached

		:Getter: Return the acquisition mode (str)

		:Setter: Set the acquisition mode. Valid modes are:
			* 'sequence': specifies that the next acquisition will be a single-sequence acquisition
			* 'runstop': specifies that the instrument will continually acquire data, if
			ACQuire:STATE is turned on.
		'''
		return self.sc.query('ACQuire:STOPAfter?').strip().lower()
	@stop_after.setter
	def stop_after(self, value: str):
		if value.lower() not in self.stop_afters:
			raise ValueError(f'Invalid stop after {value}. Valid stop afters are {self.stop_afters}')
		self.sc.write(f'ACQuire:STOPAfter {value}')

	@property
	def num_seq(self) -> int:
		'''In single sequence acquisition mode, specify the number of acquisitions or measurements
		that comprise the sequence.
		Not cached

		:Getter: Return the number of acquisitions or measurements (int)

		:Setter: Set the number of acquisitions or measurements (int)
		'''
		return int(self.sc.query('ACQuire:SEQuence:NUMSEQuence?').strip())
	@num_seq.setter
	def num_seq(self, value: int):
		stopafter = self.stop_after
		if stopafter != 'sequence':
			raise ValueError(f'Cannot set number of acquisitions or measurements in {stopafter} mode. Must be in sequence mode.')
		if not isinstance(value, int):
			raise ValueError(f'Invalid number of acquisitions or measurements {value}. Must be an int.')
		self.sc.write(f'ACQuire:SEQuence:NUMSEQuence {value}')

	@property
	def horiz_mode(self) -> str:
		'''The horizontal operating mode.
		Not cached

		:Getter: Return the mode (str)

		:Setter: Set the mode. Valid values are:
			* 'auto': automatically adjusts the sample rate and record length to provide
					  a high acquisition rate in Fast Acq or signal fidelity in analysis
			* 'manual': lets you change the sample rate, horizontal scale, and record length.
						These values interact. For example, when you change record length
						then the horizontal scale also changes.
		'''
		return self.sc.query('HORizontal:MODe?').strip().lower()
	@horiz_mode.setter
	def horiz_mode(self, value: str):
		if value.lower() not in self.horiz_modes:
			raise ValueError(f'Invalid mode {value}. Valid modes are {self.horiz_modes}')
		self.sc.write(f'HORizontal:MODe {value}')

	@property
	def horiz_sample_rate(self) -> float:
		'''The horizontal sample rate of the waveform.
		Not cached

		:Getter: Return the sample rate in Hz (float)

		:Setter: Set the sample rate in Hz (int or float)
		'''
		return float(self.sc.query('HORizontal:MODe:SAMPlerate?').strip())
	@horiz_sample_rate.setter
	def horiz_sample_rate(self, value: float | int):
		if not isinstance(value, float) and not isinstance(value, int):
			raise ValueError(f'Invalid sample rate {value}. Must be a float or an int.')
		self.sc.write(f'HORizontal:MODe:SAMPlerate {value}')
		# Check if the sample rate was set correctly
		actual = self.horiz_sample_rate
		if actual != value:
			scope_logger.warning('Failed to set horizontal sample rate to %f. Got %f instead.', value, actual)

	@property
	def horiz_scale(self) -> float:
		'''The horizontal scale of the waveform.
		Not cached

		:Getter: Return the scale in s (float)

		:Setter: Set the scale in s (int or float)
		'''
		return float(self.sc.query('HORizontal:SCAle?').strip())
	@horiz_scale.setter
	def horiz_scale(self, value: float | int):
		if not isinstance(value, float) and not isinstance(value, int):
			raise ValueError(f'Invalid scale {value}. Must be a float or an int.')
		self.sc.write(f'HORizontal:SCAle {value}')
		# Check if the scale was set correctly
		actual = self.horiz_scale
		if actual != value:
			scope_logger.warning('Failed to set horizontal scale to %f. Got %f instead.', value, actual)

	@property
	def horiz_pos(self) -> float:
		'''The horizontal position of the waveform in percent of the screen:
		0% is the left edge of the screen and 100% is the right edge of the screen.
		Not cached

		:Getter: Return the position in % (float)

		:Setter: Set the position in % (int or float)
		'''
		return float(self.sc.query('HORizontal:POSition?').strip())
	@horiz_pos.setter
	def horiz_pos(self, value: float | int):
		if not isinstance(value, float) and not isinstance(value, int):
			raise ValueError(f'Invalid position {value}. Must be a float or an int.')
		if value < 0 or value > 100:
			raise ValueError(f'Invalid position {value}. Must be between 0 and 100.')
		self.sc.write(f'HORizontal:POSition {value}')
		# Check if the position was set correctly
		actual = self.horiz_pos
		if actual != value:
			scope_logger.warning('Failed to set horizontal position to %f. Got %f instead.', value, actual)

	@property
	def horiz_record_length(self) -> int:
		'''The horizontal record length of the waveform.
		Not cached

		:Getter: Return the record length (int)

		:Setter: Set the record length (int)
		'''
		return int(self.sc.query('HORizontal:MODe:RECOrdlength?').strip())
	@horiz_record_length.setter
	def horiz_record_length(self, value: int):
		if not isinstance(value, int):
			raise ValueError(f'Invalid record length {value}. Must be an int.')
		self.sc.write(f'HORizontal:MODe:RECOrdlength {value}')

	@property
	def wfm_src(self) -> list[str]:
		'''Source of the retrieved waveform (analog FlexChannel(s) source(s)).
		Not cached

		:Getter: Return the source (str)

		:Setter: Set the source. Valid values are:
			* 'ch1': Channel 1
			* 'ch2': Channel 2
			* 'ch3': Channel 3
			* 'ch4': Channel 4
		'''
		return self.sc.query('DATa:SOUrce?').strip().split()
	@wfm_src.setter
	def wfm_src(self, value: list[str]):
		for v in value:
			if v.lower() not in self.sources:
				raise ValueError(f'Invalid source {v}. Valid sources are {self.sources}')
		self.sc.write(f'DATa:SOUrce {" ".join(value)}')

	@property
	def wfm_start(self) -> int:
		'''The starting data point for waveform transfer.
		Not cached

		:Getter: Return the start index (int)

		:Setter: Set the start index (int)
		'''
		return int(self.sc.query('DATa:STARt?').strip())
	@wfm_start.setter
	def wfm_start(self, value: int):
		if not isinstance(value, int):
			raise ValueError(f'Invalid start index {value}. Must be an int.')
		self.sc.write(f'DATa:STARt {value}')

	@property
	def wfm_stop(self) -> int:
		'''The last data point that will be transferred when using the CURVe? query.
		Not cached

		:Getter: Return the stop index (int)

		:Setter: Set the stop index (int)
		'''
		return int(self.sc.query('DATa:STOP?').strip())
	@wfm_stop.setter
	def wfm_stop(self, value: int):
		if not isinstance(value, int):
			raise ValueError(f'Invalid stop index {value}. Must be an int.')
		self.sc.write(f'DATa:STOP {value}')

	@property
	def wfm_len(self) -> int:
		'''The number of data points in the waveform.
		Not cached

		:Getter: Return the number of data points (int)
		'''
		return int(self.sc.query('WFMOutpre:NR_Pt?').strip())

	@property
	def wfm_encoding(self) -> str:
		'''The encoding of the waveform data.
		Cached

		:Getter: Return the encoding (str)

		:Setter: Set the encoding. Valid values are:
			* 'binary': Binary
			* 'ascii': ASCII

		Raises:
			ValueError: Invalid encoding
		'''
		if not self._cached_wfm_encoding:
			self._cached_wfm_encoding = self.sc.query('WFMOutpre:ENCdg?').strip().lower()
		return self._cached_wfm_encoding
	@wfm_encoding.setter
	def wfm_encoding(self, value: str):
		if value.lower() not in self.wfm_encodings:
			raise ValueError(f'Invalid encoding {value}. Valid encodings are {self.wfm_encodings}')
		if self._cached_wfm_encoding == value:
			return
		self._cached_wfm_encoding = value
		self.sc.write(f'WFMOutpre:ENCdg {value}')

	@property
	def wfm_binary_format(self) -> str:
		'''The data format of binary waveform data.
		Cached

		:Getter: Return the data format (str)

		:Setter: Set the data format. Valid values are:
			* 'ri': Signed integer
			* 'rp': Unsigned integer
			* 'fp': Floating point

		Raises:
			ValueError: Invalid data format
		'''
		if not self._cached_wfm_format:
			self._cached_wfm_format = self.sc.query('WFMOutpre:BN_Fmt?').strip().lower()
		return self._cached_wfm_format
	@wfm_binary_format.setter
	def wfm_binary_format(self, value: str):
		if value.lower() not in self.wfm_binary_formats:
			raise ValueError(f'Invalid binary format {value}. Valid binary formats are {self.wfm_binary_formats}')
		if self._cached_wfm_format == value:
			return
		self._cached_wfm_format = value
		self.sc.write(f'WFMOutpre:BN_Fmt {value}')

	@property
	def wfm_byte_nr(self) -> int:
		'''The number of bytes per data point in the waveform.
		Cached

		:Getter: Return the number of bytes per data point (int)

		:Setter: Set the number of bytes per data point (int)
			NOTE: Check the programmer manual for valid values § WFMOutpre:BYT_Nr. If unsure, clear the cache with :code:`scope._clear_cache()` and read back the value
		'''
		if not self._cached_wfm_byte_nr:
			self._cached_wfm_byte_nr = int(self.sc.query('WFMOutpre:BYT_Nr?').strip())
		return self._cached_wfm_byte_nr
	@wfm_byte_nr.setter
	def wfm_byte_nr(self, value: int):
		if not isinstance(value, int):
			raise ValueError(f'Invalid number of bytes per data point {value}. Must be an int.')
		if value not in self.wfm_byte_nrs:
			raise ValueError(f'Invalid number of bytes per data point {value}. Valid values are {self.wfm_byte_nrs}')
		if self._cached_wfm_byte_nr == value:
			return
		self._cached_wfm_byte_nr = value
		self.sc.write(f'WFMOutpre:BYT_Nr {value}')

	@property
	def wfm_byte_order(self) -> str:
		'''The byte order of the waveform data.
		Cached

		:Getter: Return the byte order (str)

		:Setter: Set the byte order. Valid values are:
			* 'lsb': Least significant byte first
			* 'msb': Most significant byte first

		Raises:
			ValueError: Invalid byte order
		'''
		if not self._cached_wfm_order:
			self._cached_wfm_order = self.sc.query('WFMOutpre:BYT_Or?').strip().lower()
		return self._cached_wfm_order
	@wfm_byte_order.setter
	def wfm_byte_order(self, value: str):
		if value.lower() not in self.wfm_byte_orders:
			raise ValueError(f'Invalid byte order {value}. Valid byte orders are {self.wfm_byte_orders}')
		if self._cached_wfm_order == value:
			return
		self._cached_wfm_order = value
		self.sc.write(f'WFMOutpre:BYT_Or {value}')

	@property
	def is_big_endian(self) -> bool:
		'''Return True if the byte order is big endian, False otherwise.
		'''
		return self.wfm_byte_order == 'msb'

	@property
	def curvestream(self) -> bool:
		'''Enable or disable curvestream mode.
		Cached

		:Getter: Return the curvestream state (bool)

		:Setter: Set the curvestream state (bool)
		'''
		if self._cached_curvestream is None:
			self.sc.write('*CLS') # If we don't know, better disable it to be sure
			self._cached_curvestream = False
		return self._cached_curvestream
	@curvestream.setter
	def curvestream(self, value: bool):
		if self._cached_curvestream == value:
			return
		self._cached_curvestream = value
		if value:
			self.sc.write('CURVestream?')
		else:
			self.sc.write('*CLS')

	@property
	def fast_acq(self) -> bool:
		'''Enable or disable fast acquisition mode.
		Cached

		:Getter: Return the fast acquisition state (bool)

		:Setter: Set the fast acquisition state (bool)
		'''
		if self._cached_fast_acq is None:
			self._cached_fast_acq = bool(int(self.sc.query("ACQuire:FASTAcq:STATE?").strip()))
		return self._cached_fast_acq
	@fast_acq.setter
	def fast_acq(self, value: bool):
		if self._cached_fast_acq == value:
			return
		self._cached_fast_acq = value
		self.sc.write(f'ACQuire:FASTAcq:STATE {int(value)}')

	def get_datatype(self) -> BINARY_DATATYPES:
		'''Get the data type of the binary waveform data in struct.pack form. Does not return endianess.
		'''
		return self.wfm_datatypes[self.wfm_byte_nr][self.wfm_binary_format]
