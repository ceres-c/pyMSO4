from enum import Enum
from typing import Self

import pyvisa

from . import logger

class connmode(Enum):
	LAN = 1
	USB = 2

class command(Enum):
	pass

class pyMSO44:
	"""Tektronix MSO44 main entry point."""

	_rm: pyvisa.ResourceManager
	_scope: pyvisa.resources.TCPIPInstrument | pyvisa.resources.USBInstrument
	_cmode: connmode
	_ip: str
	_usb: str

	def __init__(self, connmode: connmode = connmode.LAN, ip: str = '', usb: str = ''):
		logger.debug('Creating resource manager')
		self._rm = pyvisa.ResourceManager('@py')

		if connmode == connmode.LAN and ip == '':
			raise ValueError('ip must be specified when using LAN connection mode')
		elif connmode == connmode.USB and usb == '':
			raise ValueError('usb must be specified when using USB connection mode')

		self._cmode = connmode
		self._ip = ip
		self._usb = usb

	def __enter__(self) -> Self:
		"""Connect to the oscilloscope."""

		conn_string = ''

		match self._cmode:
			case connmode.LAN:
				conn_string = 'TCPIP::' + self._ip + '::INSTR'
			case connmode.USB:
				# TODO implement USB connection mode
				raise NotImplementedError('USB connection mode is not implemented yet')
				conn_string = 'USB::' + self._usb + '::INSTR'
			case _:
				raise ValueError('Invalid connection mode')

		# pyvisa does some magic, but trust me it's a resource.
		self._scope = self._rm.open_resource(conn_string) # type: ignore

		return self

	def __exit__(self, type, value, traceback):
		"""Disconnect from the oscilloscope."""
		self._scope.close()

	def get_id(self) -> str:
		"""Get the ID of the oscilloscope."""
		return self._scope.query('*IDN?')
