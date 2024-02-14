import re
from typing import Type

import pyvisa

from . import util
from . import scope_logger

class MSO4TriggerBase(util.DisableNewAttr):
	'''Base trigger for the MSO 4-Series, used for settings shared by all trigger types'''

	_sources = ['auxiliary', 'aux', 'line'] # NOTE: Digital channels are not supported yet
	_couplings = ['dc', 'hfrej', 'lfrej', 'noiserej']
	_events = ['A', 'B']
	_modes = ['auto', 'normal']

	_type = None

	def __init__(self, res: pyvisa.resources.MessageBasedResource, ch_a_count: int, event: str = 'A'):
		'''Create a new trigger object

		Args:
			res: The VISA resource to use for communication
			ch_a_count: The number of analog channels available on the scope
			event: The event channel (``A`` or ``B``) to use as a trigger
				See: 4/5/6 Series MSO Help § Trigger on sequential events (A and B triggers)
				(https://www.tek.com/en/sitewide-content/manuals/4/5/6/4-5-6-series-mso-help)
		'''
		super().__init__()

		self.sc: pyvisa.resources.MessageBasedResource = res
		self._ch_a_count: int = ch_a_count
		if event not in MSO4TriggerBase._events:
			raise ValueError(f'Invalid event {event}. Valid events: {MSO4TriggerBase._events}')
		self._event = event

		if not self._type:
			raise NotImplementedError("Can't instantiate MSO4TriggerBase directly. Use a subclass instead.")
		self.sc.write(f'TRIGGER:{self._event}:TYPE {self._type}')

		self._cached_source = None
		self._cached_coupling = None
		self._cached_level = None
		self._cached_mode = None

	def clear_caches(self):
		'''Resets the local configuration cache so that values will be fetched from
		the scope.

		This is useful when the scope configuration is (potentially) changed externally.
		'''
		self._cached_source = None
		self._cached_coupling = None
		self._cached_level = None
		self._cached_mode = None

	def force(self):
		'''Force the trigger to occur immediately'''
		self.sc.write('TRIGGER FORCe')

	@property
	def source(self):
		'''The source of the event currently configured as a trigger. Valid values are
		``chN`` (Analog channel n) and ``auxiliary``, ``aux``, ``line``

		*Cached*

		:Getter: Return the current trigger source

		:Setter: Set the trigger source

		Raises:
			ValueError: if value is not one of the allowed strings
		'''
		if not self._cached_source:
			self._cached_source = self.sc.query(f'TRIGGER:{self._event}:{self._type}:SOURCE?').strip()
		return self._cached_source
	@source.setter
	def source(self, src: str):
		src = src.lower()
		valid = False
		if src.lower()[:2] == 'ch':
			try:
				ch_num = int(src[2:])
				if ch_num < self._ch_a_count:
					valid = True
			except ValueError:
				pass
		else:
			valid = src in MSO4TriggerBase._sources
		if not valid:
			raise ValueError(f'Invalid trigger source {src}. Valid sources are ch1-ch{self._ch_a_count} and {MSO4TriggerBase._sources}')

		if self._cached_source == src:
			return
		self._cached_source = src
		self.sc.write(f'TRIGGER:{self._event}:{self._type}:SOURCE {src}')

	@property
	def coupling(self) -> str:
		'''The coupling of the trigger source. Valid couplings are ``dc``, ``hfrej``, ``lfrej``, ``noiserej``

		*Cached*

		:Getter: Return the current trigger coupling

		:Setter: Set the trigger coupling

		Raises:
			ValueError: if value is not one of the allowed strings
		'''
		if not self._cached_coupling:
			self._cached_coupling = self.sc.query(f'TRIGGER:{self._event}:{self._type}:COUPLING?').strip()
		return self._cached_coupling
	@coupling.setter
	def coupling(self, coupling: str):
		if coupling.lower() not in MSO4TriggerBase._couplings:
			raise ValueError(f'Invalid trigger coupling {coupling}. Valid coupling: {MSO4TriggerBase._couplings}')
		if self._cached_coupling == coupling:
			return
		self._cached_coupling = coupling
		self.sc.write(f'TRIGGER:{self._event}:{self._type}:COUPLING {coupling}')

	@property
	def level(self) -> float:
		'''The trigger level

		*Cached*

		:Getter: Return the current trigger level

		:Setter: Set the trigger level (int or float)

		Raises:
			ValueError: if value is not a float
		'''
		if not self._cached_level:
			resp = self.sc.query(f'TRIGGER:{self._event}:LEVEL:{self.source}?').strip()
			try:
				self._cached_level = float(resp)
			except ValueError as exc:
				raise ValueError(f'Got invalid trigger level from oscilloscope `{resp}`. Must be a float.') from exc
		return self._cached_level
	@level.setter
	def level(self, level: float):
		if not isinstance(level, float) and not isinstance(level, int):
			raise ValueError(f'Invalid trigger level {level}. Must be a float or an int.')
		if self._cached_level == level:
			return
		self.sc.write(f'TRIGGER:{self._event}:LEVEL:{self.source} {level:.4e}')

		self._cached_level = None
		self._cached_level = self.level
		if self._cached_level != level:
			scope_logger.warning('Failed to set trigger level to %f. Got %f instead.', level, self._cached_level)

	@property
	def mode(self) -> str:
		'''The trigger mode (``auto``/``normal``)

		*Cached*

		:Getter: Return the current trigger mode

		:Setter: Set the trigger mode

		Raises:
			NotImplementedError: if trigger event is not A
			ValueError: if value is not one of the allowed strings
		'''
		if self._event != 'A':
			raise NotImplementedError('Trigger mode is only supported for event A.')
		if not self._cached_mode:
			self._cached_mode = self.sc.query('TRIGGER:A:MODe?').strip()
		return self._cached_mode
	@mode.setter
	def mode(self, mode: str):
		if self._event != 'A':
			raise NotImplementedError('Trigger mode is only supported for event A.')
		if mode.lower() not in MSO4TriggerBase._modes:
			raise ValueError(f'Invalid trigger mode {mode}. Valid modes: {MSO4TriggerBase._modes}')
		if self._cached_mode == mode:
			return
		self._cached_mode = mode
		self.sc.write(f'TRIGGER:A:MODe {mode}')

class MSO4EdgeTrigger(MSO4TriggerBase):
	'''Edge trigger'''

	_type = 'EDGE'

	_slopes = ['rise', 'fall', 'either']

	def __init__(self, res: pyvisa.resources.MessageBasedResource, ch_a_count: int, event: str = 'A'):
		super().__init__(res, ch_a_count, event)

		self._cached_edge_slope = None
		self.disable_newattr()

	def clear_caches(self):
		super().clear_caches()
		self._cached_edge_slope = None

	@property
	def edge_slope(self) -> str:
		'''The edge slope (``rise``/``fall``/``either``)

		*Cached*

		:Getter: Return the current edge slope

		:Setter: Set the edge slope

		Raises:
			ValueError: if value is not one of the allowed strings
		'''
		if not self._cached_edge_slope:
			self._cached_edge_slope = self.sc.query(f'TRIGGER:{self._event}:EDGE:SLOpe?').strip()
		return self._cached_edge_slope
	@edge_slope.setter
	def edge_slope(self, slope: str):
		if slope.lower() not in MSO4EdgeTrigger._slopes:
			raise ValueError(f'Invalid edge slope {slope}. Valid slopes: {MSO4EdgeTrigger._slopes}')
		if self._cached_edge_slope == slope:
			return
		self._cached_edge_slope = slope
		self.sc.write(f'TRIGGER:{self._event}:EDGE:SLOpe {slope}')

class MSO4WidthTrigger(MSO4TriggerBase):
	'''Pulse Width trigger
	'''

	_type = 'WIDth'

	_whens = ['lessthan', 'morethan', 'equal', 'unequal', 'within', 'outside']

	def __init__(self, res: pyvisa.resources.MessageBasedResource, ch_a_count: int, event: str = 'A'):
		super().__init__(res, ch_a_count, event)

		self._cached_when = None
		self._cached_limit = None
		self.disable_newattr()

	def clear_caches(self):
		super().clear_caches()
		self._cached_when = None
		self._cached_limit = None

	# TODO lowlimit, highlimit, when & polarity properties
	# - lowlimit (float): The low limit of the pulse width.
	# - highlimit (float): The high limit of the pulse width.
	# - when (str): When to trigger (lessthan/morethan/equal/unequal/within/outside)
	# - polarity (str): The polarity of the pulse (positive/negative)

MSO4Triggers = Type[MSO4EdgeTrigger] | Type[MSO4WidthTrigger]
