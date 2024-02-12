
import logging

scope_logger = logging.getLogger("pyMSO44")
scope_logger.addHandler(logging.NullHandler())

from .pyMSO4 import *
