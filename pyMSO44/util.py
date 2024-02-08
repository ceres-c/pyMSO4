from typing import List
from . import scope_logger

class DisableNewAttr(object):
    # Copied from https://github.com/newaetech/chipwhisperer/blob/develop/software/chipwhisperer/common/utils/util.py
    """Provides an ability to disable setting new attributes in a class, useful to prevent typos.

    Usage:
    1. Make a class that inherits this class:
    >>> class MyClass(DisableNewAttr):
    >>>     # Your class definition here

    2. After setting up all attributes that your object needs, call disable_newattr():
    >>>     def __init__(self):
    >>>         self.my_attr = 123
    >>>         self.disable_newattr()

    3. Subclasses raise an AttributeError when trying to make a new attribute:
    >>> obj = MyClass()
    >>> #obj.my_new_attr = 456   <-- Raises AttributeError
    """
    _new_attributes_disabled = False
    _new_attributes_disabled_strict = False
    _read_only_attrs : List[str] = []

    def __init__(self):
        self._read_only_attrs = []
        self.enable_newattr()

    def disable_newattr(self):
        self._new_attributes_disabled = True
        self._new_attributes_disabled_strict = False

    def enable_newattr(self):
        self._new_attributes_disabled = False
        self._new_attributes_disabled_strict = False

    def disable_strict_newattr(self):
        self._new_attributes_disabled = True
        self._new_attributes_disabled_strict = True

    def add_read_only(self, name):
        if isinstance(name, list):
            for a in name:
                self.add_read_only(a)
            return
        if name in self._read_only_attrs:
            return
        self._read_only_attrs.append(name)

    def remove_read_only(self, name):
        if isinstance(name, list):
            for a in name:
                self.remove_read_only(a)
                return
        if name in self._read_only_attrs:
            self._read_only_attrs.remove(name)

    def __setattr__(self, name, value):
        if hasattr(self, '_new_attributes_disabled') and self._new_attributes_disabled and not hasattr(self, name):  # would this create a new attribute?
            #raise AttributeError("Attempt to set unknown attribute in %s"%self.__class__, name)
            scope_logger.error("Setting unknown attribute {} in {}".format(name, self.__class__))
            if hasattr(self, '_new_attributes_disabled_strict') and self._new_attributes_disabled_strict and not hasattr(self, name):
                raise AttributeError("Attempt to set unknown attribute in %s"%self.__class__, name)
        if name in self._read_only_attrs:
            raise AttributeError("Attribute {} is read-only!".format(name))
        super(DisableNewAttr, self).__setattr__(name, value)
