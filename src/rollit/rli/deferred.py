"""
"""
import inspect
from abc import ABCMeta, abstractmethod
from collections import namedtuple
from contextlib import suppress

from .base import PythonBasedLibrary, PythonBasedModifier, PythonBag
from ..ast import ModelElement
from ..ast.elements import SpecialEntry, OperationSide
from ..objects import Modifier, Roll, Dice, Bag
from ..runtime import context
from ..util import is_valid_iterable

__all__ = [
    'ObjectPlaceholder',
    'BagPlaceholder',
    'preloader',
    'postloader',
    'entry',
    'DeferredBag',
    'DeferredPythonBasedLibrary',
]


class ObjectPlaceholder(metaclass=ABCMeta):
    """A placeholder for and internal object that will be
    """
    __slots__ = ('_preloaders', '_postloaders')

    def __init__(self, *, preloaders=None, postloaders=None):
        self._preloaders = preloaders if preloaders is not None else []
        self._postloaders = postloaders if postloaders is not None else []

    #TODO handle modifiers
    def _run_load_op(self, op, obj):
        if not op:
            return
        if is_valid_iterable(op):
            for item in op:
                self._run_load_op(item, obj)
        elif isinstance(op, ModelElement):
            context(op)
        elif callable(op):
            op(obj)
        else:
            raise TypeError()

    def resolve(self):
        """
        """
        for op in self._preloaders:
            self._run_load_op(op, self)
        obj = self.get_object()
        for op in self._postloaders:
            self._run_load_op(op, obj)
        return obj

    @abstractmethod
    def get_object(self):
        """
        """

    def preloader(self, func):
        """
        """
        self._preloaders.append(func)
        return func

    def postloader(self, func):
        """
        """
        self._postloaders.append(func)
        return func


class BagPlaceholder(ObjectPlaceholder):
    """
    """
    __slots__ = ('_entries', '_raw')

    def __init__(self, entries=None, raw=False, *, preloaders=None, postloaders=None):
        super().__init__(preloaders=preloaders, postloaders=postloaders)
        if entries is None:
            entries = {}
        self._entries = entries
        self._raw = raw

    def _get_value(self, item):
        if isinstance(item, dict):
            return PythonBag({k: self._get_value(v) for k, v in item.items()})
        if is_valid_iterable(item):
            return Roll(self._get_value(v) for v in item)
        if isinstance(item, ObjectPlaceholder):
            return item.resolve()
        return item

    def get_object(self):
        bag = Bag()
        for k, v in self._entries.items():
            v = self._get_value(v)
            if self._raw is True:
                bag.raw_set(k, v)
            else:
                bag[k] = v
        if isinstance(self._raw, dict):
            for k, v in self._raw.items():
                bag.raw_set(k, self._get_value(v))
        return bag

    def modifier(self, name_or_func):
        """
        """
        name = name_or_func
        if callable(name_or_func):
            name = name_or_func.__name__

        def _decorator(func):
            if not isinstance(func, Modifier):
                func = PythonBasedModifier(func)
            self._entries[name] = func
            return func

        if callable(name_or_func):
            return _decorator(name_or_func)
        return _decorator

    def on_access(self, modifier):
        """
        """
        if not isinstance(modifier, Modifier):
            modifier = PythonBasedModifier(modifier)
        self._entries[SpecialEntry.ACCESS] = modifier
        return modifier

    def on_set(self, modifier):
        """
        """
        if not isinstance(modifier, Modifier):
            modifier = PythonBasedModifier(modifier)
        self._entries[SpecialEntry.SET] = modifier
        return modifier

    def on_clear(self, modifier):
        """
        """
        if not isinstance(modifier, Modifier):
            modifier = PythonBasedModifier(modifier)
        self._entries[SpecialEntry.CLEAR] = modifier
        return modifier

    def on_create(self, modifier):
        """
        """
        if not isinstance(modifier, Modifier):
            modifier = PythonBasedModifier(modifier)
        self._entries[SpecialEntry.CREATE] = modifier
        return modifier

    def on_destroy(self, modifier):
        """
        """
        if not isinstance(modifier, Modifier):
            modifier = PythonBasedModifier(modifier)
        self._entries[SpecialEntry.DESTROY] = modifier
        return modifier


class DeferredBag:
    """
    """
    _initialized = False
    name = None
    isolate = False
    raw = True
    """ """

    def __init__(self, entries=None, *, raw=True):
        self.raw = raw
        self._preloaders = []
        self._postloaders = []
        self._entries = {}
        self._operator_overloads = {}
        if entries is None:
            entries = {}
        for key, value in entries.items():
            self[key] = value
        self._initialized = True

    def __setattr__(self, name, value):
        if self._initialized:
            with suppress(TypeError):
                self[name] = value
        return super().__setattr__(name, value)

    def modifier(self, name_or_func):
        """
        """
        if callable(name_or_func):
            # pylint: disable=no-member
            name = name_or_func.__name__
        else:
            name = name_or_func

        def _decorator(func):
            self._entries[name] = entry(func)
            return func

        if callable(name_or_func):
            return _decorator(name_or_func)
        return _decorator

    def add_entry(self, name, value, *, is_property=False):
        """
        """
        self._entries[name] = entry(value, is_property=is_property)

    def entry(self, name, *, is_property=True):
        """
        """

        def _decorator(entry_):
            self._entries[name] = entry(entry_, is_property=is_property)
            return entry_

        return _decorator

    def preloader(self, func):
        """
        """
        self._preloaders.append(func)

    def postloader(self, func):
        """
        """
        self._postloaders.append(func)

    def __setitem__(self, key, value):
        self._entries[key] = entry(value)

    def _get_entry_value(self, entry_info):
        value = entry_info.value
        if entry_info.is_property:
            if isinstance(value, property):
                value = value.__get__(self, type(self))
            elif callable(value):
                sig = inspect.signature(value)
                # pylint: disable=compare-to-zero
                if len(sig.parameters) == 0:
                    value = value()
                elif len(sig.parameters) == 1:
                    value = value(self)
                else:
                    raise ValueError()
            if not isinstance(value, _VALID_ENTRY_TYPES):
                value = self._get_entry_value(entry(value))
        if isinstance(value, DeferredBag):
            value = value.to_placeholder()
        return value

    # pylint: disable=protected-access
    def to_placeholder(self):
        """
        """
        preloaders = []
        postloaders = []
        entries = {}
        for attr in dir(self):
            entry_item = getattr(self, attr)
            if isinstance(entry_item, preloader):
                self._preloaders.append(entry_item.value)
                continue
            if isinstance(entry_item, postloader):
                self._postloaders.append(entry_item.value)
                continue
            if not isinstance(entry_item, entry):
                continue
            entries[attr] = self._get_entry_value(entry_item)
        preloaders += self._preloaders
        postloaders += self._postloaders
        for name, entry_item in self._entries.items():
            if not isinstance(entry_item, entry):
                continue
            entries[name] = self._get_entry_value(entry_item)
        return BagPlaceholder(
            entries,
            raw=self.raw,
            preloaders=preloaders,
            postloaders=postloaders,
        )

    def on_create(self, modifier):
        """
        """
        self._entries[SpecialEntry.CREATE] = entry(modifier)

    def on_access(self, modifier):
        """
        """
        self._entries[SpecialEntry.ACCESS] = entry(modifier)

    def on_set(self, modifier):
        """
        """
        self._entries[SpecialEntry.SET] = entry(modifier)

    def on_clear(self, modifier):
        """
        """
        self._entries[SpecialEntry.CLEAR] = entry(modifier)

    def on_destroy(self, modifier):
        """
        """
        self._entries[SpecialEntry.DESTROY] = entry(modifier)

    def overload_operator(self, operator, side=OperationSide.NA):
        """
        """

        def _decorator(func):
            self._operator_overloads[(operator, side)] = func
            return func

        return _decorator


class DeferredPythonBasedLibrary(DeferredBag, PythonBasedLibrary):
    """
    """
    name = None
    isolate = False

    def __init__(self, name, entries=None, *, raw=True, isolate=False):
        self.name = name
        self.isolate = isolate
        super().__init__(entries=entries, raw=raw)


_VALID_ENTRY_TYPES = (int, float, str, Bag, Roll, Dice, ModelElement, Modifier, ObjectPlaceholder,
                      type(None), PythonBasedLibrary, DeferredBag)


class _Loader(namedtuple('_LoaderBase', ('func',))):
    """
    """

    def __new__(cls, func):
        if isinstance(func, _Loader):
            func = func.func
        elif isinstance(func, entry):
            func = func.value
        return super().__new__(cls, func)


preloader = type('preloader', (_Loader,), {})
""" """

postloader = type('postloader', (_Loader,), {})
""" """


class entry(namedtuple('_EntryBase', ('value', 'is_property'))):
    """
    """

    def __new__(cls, value, *, is_property=False, raw=False):
        if not is_property:
            is_property = isinstance(value, property)
        if isinstance(value, entry):
            if value.is_property == is_property:
                return value
            return super().__new__(cls, value.value, is_property=is_property)
        if isinstance(value, _Loader):
            value = value.value
        if is_valid_iterable(value) and not isinstance(value, Roll):
            value = Roll(value)
        elif isinstance(value, dict):
            value = BagPlaceholder(value, raw=raw)
        elif callable(value) and not isinstance(value, _VALID_ENTRY_TYPES):
            value = PythonBasedModifier(value)
        # pylint: disable=consider-merging-isinstance
        if not (isinstance(value, _VALID_ENTRY_TYPES) or isinstance(value, property)):
            raise TypeError(f'Invalid entry type: {type(value).__qualname__}')
        return super().__new__(cls, value, is_property=is_property)

    def __getattr__(self, name):
        return getattr(self.value, name)

    def __setattr__(self, name, value):
        return setattr(self.value, name, value)

    def __delattr__(self, name):
        return delattr(self.value, name)
