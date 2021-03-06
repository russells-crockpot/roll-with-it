"""Internal representations of rollit objects.
"""
import itertools
import os
from abc import ABCMeta, abstractmethod
from collections import namedtuple
from contextlib import suppress

from .ast import elements, ModelElement, ModelEnumElement, constants
from .exceptions import RollitTypeError, InvalidNameError
from .runtime import context
from .util import is_valid_iterable

__all__ = (
    'RollitNonErrorException',
    'LeaveException',
    'RestartException',
    'OopsException',
    'Dice',
    'Roll',
    'BagSpecialEntries',
    'Bag',
    'Modifier',
    'RollitBasedModifier',
    'NoSubject',
    'NoValue',
)


def __create_no_value():

    class _NoValueBase(tuple):
        __the_object = None

        def __new__(cls):
            if not cls.__the_object:
                cls.__the_object = super().__new__(cls)
            return cls.__the_object

        def __bool__(self):
            return False

        @staticmethod
        def __str__():
            return 'NoValue'

        @staticmethod
        def __repr__():
            return 'NoValue'

    return _NoValueBase()


NoValue = __create_no_value()
""" """
del __create_no_value


def __create_no_subject():

    class _NoSubjectBase(tuple):
        __the_object = None

        def __new__(cls):
            if not cls.__the_object:
                cls.__the_object = super().__new__(cls)
            return cls.__the_object

        def __bool__(self):
            return False

        @staticmethod
        def __str__():
            return 'NoSubject'

        @staticmethod
        def __repr__():
            return 'NoSubject'

    return _NoSubjectBase()


NoSubject = __create_no_subject()
""" """
del __create_no_subject


class RollitNonErrorException(BaseException):
    """An exception that is used as a sort of internal marker, but not as any sort of error.
    """


class LeaveException(RollitNonErrorException):
    """Used to indicate that a ``leave`` statement was issued.
    """
    __slots__ = ()
    __THE_EXCEPTION = None

    def __new__(cls):
        if not cls.__THE_EXCEPTION:
            cls.__THE_EXCEPTION = super().__new__(cls)
        return cls.__THE_EXCEPTION


class RestartException(RollitNonErrorException):
    """Used to indicate that a ``restart`` statement was issued.
    """
    __slots__ = ('location_specifier', 'name')

    #pylint: disable=super-init-not-called
    def __init__(self, location_specifier, name, *args):
        self.location_specifier = location_specifier
        self.name = name


class OopsException(RollitNonErrorException):
    """
    """
    __slots__ = ('value', 'stacktrace')

    #pylint: disable=super-init-not-called
    def __init__(self, value):
        self.value = value
        self.stacktrace = None

    @property
    def msg(self):
        """
        """
        return str(self.value)


class OperatorImplementations:
    """
    """
    __slots__ = (
        *(op.left_python_name for op in elements.TwoSidedOperator),
        *(op.right_python_name for op in elements.TwoSidedOperator),
        *(op.python_name for op in elements.OneSidedOperator),
        *(op.python_name for op in elements.OverloadOnlyOperator),
    )

    def __init__(self, *, copy_from=None):
        if not copy_from:
            for attr in self.__slots__:
                setattr(self, attr, NotImplemented)
        else:
            for attr in self.__slots__:
                setattr(self, attr, getattr(copy_from, attr, NotImplemented))

    @staticmethod
    def _convert_key(key):
        if isinstance(key, elements.OverloadOperator):
            if key.side == elements.OperationSide.NA:
                return key.operator.python_name
            return getattr(key.operator, f'{key.side.name.lower()}_python_name')
        return key

    def __delattr__(self, name):
        setattr(self, name, NotImplemented)

    def get_impl(self, operator, side=elements.OperationSide.NA):
        """
        """
        if isinstance(operator, elements.TwoSidedOperator):
            if not side:
                raise ValueError()
            key = getattr(operator, f'{side.name.lower()}_python_name')
        else:
            key = operator.python_name
        return getattr(self, key)

    def add_impl(self, operator, side=elements.OperationSide.NA):
        """
        """

        def _decorator(func):
            if isinstance(operator, elements.TwoSidedOperator):
                if not side:
                    raise ValueError()
                key = getattr(operator, f'{side.name.lower()}_python_name')
            else:
                key = operator.python_name
            setattr(self, key, func)
            return func

        return _decorator

    def set_impl(self, operator, side, impl):
        """
        """
        if isinstance(operator, elements.TwoSidedOperator):
            if not side:
                raise ValueError()
            key = getattr(operator, f'{side.name.lower()}_python_name')
        else:
            key = operator.python_name
        setattr(self, key, impl)


def _idgenerator():
    i = 0
    while True:
        i += 1
        yield i


class InternalObject(metaclass=ABCMeta):
    """
    """
    __slots__ = ('_op_impls', '_rollit_id')
    __idgenerator = _idgenerator()

    default_ops_impl = None
    """ """

    def __init__(self):
        self._op_impls = OperatorImplementations(copy_from=self.default_ops_impl)

    def __setattr__(self, name, value):
        if name == '_rollit_id':
            with suppress(AttributeError):
                self._rollit_id  # pylint: disable=pointless-statement
                raise ValueError('Cannot change and object\'s ID once it has been set')
        super().__setattr__(name, value)

    def __getattr__(self, name):
        if name in self._op_impls.__slots__:
            return getattr(self._op_impls, name)
        raise AttributeError(name)

    def operate_on(self, operator, side=None, other=None):
        """
        """
        op_impl = self._op_impls.get_impl(operator, side=side)
        args = ()
        if not isinstance(operator, elements.OverloadOnlyOperator):
            args = (other,)
        if isinstance(op_impl, Modifier):
            return op_impl.call(*args, subject=self)
        if callable(op_impl):
            return op_impl(self, *args)
        return op_impl

    def override_operator(self, operator, side, impl):
        """
        """
        self._op_impls.set_impl(operator, side, impl)

    #pylint: disable=access-member-before-definition,attribute-defined-outside-init
    def getid(self):
        """
        """
        with suppress(AttributeError):
            return self._rollit_id
        self._rollit_id = next(self.__idgenerator)
        return self._rollit_id

    if int(os.environ.get('TESTING_ROLLIT', 0)):

        @abstractmethod
        def _to_eval_test_repr(self):
            pass


del _idgenerator


class Dice(InternalObject):
    """
    """
    __slots__ = ('num_dice', 'sides')
    default_ops_impl = OperatorImplementations()

    def __init__(self, num_dice, sides, *args, **kwargs):
        super().__init__()
        self.num_dice = num_dice
        self.sides = sides

    # pylint: disable=no-member, protected-access
    def __getitem__(self, key):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.LENGTH._value_):
            return self.num_dice
        if key in (elements.SpecialAccessor.PARENT, elements.SpecialAccessor.PARENT._value_):
            return self.sides
        raise RollitTypeError(f'Attempted to get invalid item {key} from a dice.')

    # pylint: disable=no-member, protected-access
    def __setitem__(self, key, value):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.LENGTH._value_):
            self.num_dice = value
        elif key in (elements.SpecialAccessor.PARENT, elements.SpecialAccessor.PARENT._value_):
            self.sides = value
        else:
            raise RollitTypeError()

    def __repr__(self):
        return str(self)

    def __str__(self):
        num_dice = self.num_dice
        if isinstance(num_dice, ModelElement):
            num_dice = f'({num_dice.codeinfo.text})'
        sides = self.sides
        if isinstance(sides, ModelElement):
            sides = f'({sides.codeinfo.text})'
        return f'{num_dice}d{sides}'

    def operate_on(self, operator, side=None, other=None):
        op_impl = super().operate_on(operator, side=side, other=other)
        if op_impl is NotImplemented and side:
            # pylint: disable=too-many-function-args
            value = context(elements.Reduce(self, codeinfo=None))
            if side == elements.OperationSide.LEFT:
                kwargs = {'left': value, 'right': other, 'op': operator}
            else:
                kwargs = {'left': other, 'right': value, 'op': operator}
            # pylint: disable=unexpected-keyword-arg
            return elements.BinaryOp(**kwargs, codeinfo=None)
        return op_impl

    if int(os.environ.get('TESTING_ROLLIT', 0)):

        def _to_eval_test_repr(self):
            return (self.num_dice, self.sides)


@Dice.default_ops_impl.add_impl(elements.OverloadOnlyOperator.REDUCE)
def _(obj):
    num_dice = context(obj.num_dice)
    return Roll([context.roll(context(obj.sides)) for _ in range(num_dice)])


class Roll(InternalObject):
    """
    """
    default_ops_impl = OperatorImplementations()
    __slots__ = ('_items', '_value')

    def __init__(self, results=()):
        super().__init__()
        self._items = list(results)
        self._value = None

    @property
    def total(self):
        """
        """
        if not self._items:
            return 0
        running_total = self._items[0]
        for item in self._items[1:]:
            # pylint: disable=unexpected-keyword-arg
            running_total = context(
                elements.BinaryOp(
                    left=running_total,
                    op=elements.TwoSidedOperator.ADD,
                    right=item,
                    codeinfo=None,
                ))
        return running_total

    @property
    def value(self):
        """
        """
        if self._value is None:
            return self.total
        return context(self._value)

    @value.setter
    def value(self, value):
        self._value = value

    @value.deleter
    def value(self):
        self._value = None

    def __getitem__(self, key):
        if key == elements.SpecialAccessor.LENGTH:
            return len(self)
        if key in (elements.SpecialAccessor.VALUE, 0):
            return self.value
        if key == elements.SpecialAccessor.TOTAL:
            return self.total
        if key == elements.SpecialAccessor.EVERY:
            raise NotImplementedError()
        try:
            if key >= 1:
                key -= 1
            return self._items[key]
        except TypeError:
            raise RollitTypeError() from None

    def __setitem__(self, key, value):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.TOTAL):
            raise RuntimeError()
        if key in (elements.SpecialAccessor.VALUE, 0):
            self._value = value
        elif key == elements.SpecialAccessor.EVERY:
            raise NotImplementedError()
        else:
            try:
                if key >= 1:
                    key -= 1
                self._items[key] = value
            except TypeError:
                raise RollitTypeError() from None

    def __delitem__(self, key):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.TOTAL):
            raise RuntimeError()
        if key in (elements.SpecialAccessor.VALUE, 0):
            self._value = None
        if key == elements.SpecialAccessor.EVERY:
            self.clear()
        else:
            try:
                if key >= 1:
                    key -= 1
                del self._items[key]
            except TypeError:
                raise RollitTypeError() from None

    def __len__(self):
        return len(self._items)

    def __contains__(self, key):
        return key in self._items

    def __str__(self):
        return f'[{", ".join(str(r) for r in self._items)}]'

    def __repr__(self):
        return str(self)

    def __iter__(self):
        return iter(self._items)

    def extend(self, roll):
        """
        """
        self._items.extend(roll)

    def append(self, obj):
        """
        """
        self._items.append(obj)

    def insert(self, obj, idx=1):
        """
        """
        self._items.insert(idx - 1, obj)

    def operate_on(self, operator, side=None, other=None):
        op_impl = super().operate_on(operator, side=side, other=other)
        if op_impl is NotImplemented:
            if isinstance(other, Roll) and operator not in (
                    elements.TwoSidedOperator.AMPERSAND,
                    elements.OneSidedOperator.HAS,
            ):
                other = other.value
            if isinstance(self.value, InternalObject):
                return self.value.operate_on(operator, side=side, other=other)
            if operator.value in constants.OPERATOR_MAP:
                if side == elements.OperationSide.LEFT:
                    return constants.OPERATOR_MAP[operator.value](self.value, other)
                return constants.OPERATOR_MAP[operator.value](other, self.value)
        return op_impl

    if int(os.environ.get('TESTING_ROLLIT', 0)):

        def _to_eval_test_repr(self):
            return self._items


#TODO
@Roll.default_ops_impl.add_impl(elements.OneSidedOperator.HAS)
def _(obj, other):
    return other in obj


@Roll.default_ops_impl.add_impl(elements.TwoSidedOperator.AMPERSAND, elements.OperationSide.LEFT)
def _(obj, other):
    new_roll = Roll(obj)
    if isinstance(other, elements.Expand):
        new_roll.extend(context(other.value))
    else:
        new_roll.append(context(other))
    return new_roll


@Roll.default_ops_impl.add_impl(elements.TwoSidedOperator.AMPERSAND, elements.OperationSide.RIGHT)
def _(obj, other):
    if isinstance(other, elements.Expand):
        new_roll = context(other.value)
        new_roll.extend(obj)
        return new_roll
    return Roll((other, *obj))


@Roll.default_ops_impl.add_impl(elements.OverloadOnlyOperator.ITERATE)
def _(obj):
    return iter(obj)


@Roll.default_ops_impl.add_impl(elements.OverloadOnlyOperator.LENGTH)
def _(obj):
    return len(obj)


@Roll.default_ops_impl.add_impl(elements.OverloadOnlyOperator.REDUCE)
# pylint: disable=protected-access
def _(obj):
    value_reduced = False
    new_values = []
    for result in obj._items:
        if not isinstance(result, (int, float, str)):
            # pylint: disable=too-many-function-args
            new_result = context(elements.Reduce(result, codeinfo=None))
            value_reduced = new_result is not result
            result = new_result
        new_values.append(result)
    if not value_reduced:
        return obj.value
    roll = Roll(new_values)
    roll._value = obj._value
    return roll


# pylint: disable=protected-access
class BagSpecialEntries:
    """
    """
    __slots__ = ('_owner', 'parent', 'access', 'set', 'clear', 'create', 'destroy')

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.parent = None
        self.access = None
        self.set = None
        self.clear = None
        self.create = None
        self.destroy = None

    @property
    def owner(self):
        """
        """
        return self._owner

    def _execute(self, entry_name, bag, *args, from_parent=False):
        with context.use_subject(bag):
            if from_parent:
                if self.parent:
                    entry = getattr(self.parent._special_entries, entry_name)
                else:
                    entry = None
            else:
                entry = getattr(self, entry_name)
            if args and isinstance(entry, Bag):
                if entry is bag:
                    return bag
                try:
                    entry = entry[args[0]]
                    args = args[1:]
                except LookupError:
                    entry = NoValue
            if isinstance(entry, Modifier):
                return entry.call(*args, subject=bag)
            if entry:
                return entry
            if self.parent:
                method = getattr(self.parent._special_entries, f'on_{entry_name}')
                return method(*args, bag=bag)
            return NoValue

    def on_access(self, name, bag=None):
        """
        """
        bag = bag or self.owner
        rval = self._execute('access', bag, name)
        if rval in (NoSubject, NoValue):
            rval = bag.raw_get(name)
        if rval in (NoSubject, NoValue, bag):
            return None
        return rval

    def on_set(self, name, value, bag=None):
        """
        """
        bag = bag or self.owner
        rval = self._execute('set', bag, name, value)
        if rval is NoValue:
            return value
        return rval

    def on_clear(self, name, bag=None):
        """
        """
        bag = bag or self.owner
        rval = self._execute('clear', bag, name)
        if rval is NoValue:
            bag.raw_clear(name)

    def on_create(self, bag=None):
        """
        """
        bag = bag or self.owner
        if not bag.parent:
            return
        self._execute('create', bag, from_parent=True)

    def on_destroy(self, bag=None):
        """
        """
        bag = bag or self.owner
        self._execute('destroy', bag)

    def __delitem__(self, key):
        return setattr(self, key._name_.lower(), None)

    def __getitem__(self, key):
        try:
            return getattr(self, key._name_.lower())
        except AttributeError:
            raise KeyError(key)

    # pylint: disable=no-member
    def __setitem__(self, key, value):
        if key in (elements.SpecialEntry.PARENT, elements.SpecialEntry.PARENT._value_):
            self.parent = value
        elif key in (elements.SpecialEntry.CREATE, elements.SpecialEntry.CREATE._value_):
            self.create = value
        elif key in (elements.SpecialEntry.ACCESS, elements.SpecialEntry.ACCESS._value_):
            self.access = value
        elif key in (elements.SpecialEntry.CLEAR, elements.SpecialEntry.CLEAR._value_):
            self.clear = value
        elif key in (elements.SpecialEntry.SET, elements.SpecialEntry.SET._value_):
            self.set = value
        else:
            raise KeyError(key)


class Bag(InternalObject):
    """
    """
    default_ops_impl = OperatorImplementations()
    __slots__ = ('_entries', '_special_entries')

    def __init__(self):
        super().__init__()
        self._special_entries = BagSpecialEntries(self)
        self._entries = {}

    def keys(self):
        """
        """
        return self._entries.keys

    def __repr__(self):
        return str(self)

    #TODO get parent items
    def __str__(self):
        parts = []
        for k, v in self._entries.items():
            if v is self:
                v = '`this-bag`'
            parts.append(f'{k} = {v!r}')
        if isinstance(self._special_entries.access, Bag):
            for k, v in self._special_entries.access._entries.items():
                if v is self:
                    v = '`this-bag`'
                parts.append(f'<.>.{k} = {v!r}')
        if isinstance(self._special_entries.set, Bag):
            for k, v in self._special_entries.set._entries.items():
                if v is self:
                    v = '`this-bag`'
                parts.append(f'<=>.{k} = {v!r}')
        if not parts:
            return '{:}'
        return str(f'{{: {" | ".join(parts)} :}}')

    @property
    def parent(self):
        """
        """
        return self._special_entries.parent

    # pylint: disable=protected-access
    def load(self, bag):
        """
        """
        if not bag:
            return
        if isinstance(bag, Bag):
            bag = bag._entries
        self._entries.update(bag)

    # pylint: disable=no-member,protected-access
    def __getitem__(self, key):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.LENGTH._value_):
            return len(self)
        if isinstance(key, elements.SpecialEntry):
            return self._special_entries[key]
        rval = self._special_entries.on_access(key)
        if rval in (NoValue, NoSubject):
            raise InvalidNameError(key)
        return rval

    def __setitem__(self, key, value):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.LENGTH._value_):
            raise RollitTypeError()
        if isinstance(key, elements.SpecialEntry):
            self._special_entries[key] = value
        else:
            rval = self._special_entries.on_set(key, value)
            if rval is not self:
                self._entries[key] = rval

    def __delitem__(self, key):
        if key in (elements.SpecialAccessor.LENGTH, elements.SpecialAccessor.LENGTH._value_):
            raise RollitTypeError()
        if isinstance(key, elements.SpecialEntry):
            del self._special_entries[key]
        else:
            self._special_entries.on_clear(key)

    def raw_clear(self, key):
        """
        """
        if isinstance(key, elements.SpecialEntry):
            del self._special_entries[key]
        else:
            del self._entries[key]

    def raw_set(self, key, value):
        """
        """
        if isinstance(key, elements.SpecialEntry):
            self._special_entries[key] = value
        else:
            self._entries[key] = value

    def raw_get(self, key):
        """
        """
        if isinstance(key, elements.SpecialEntry):
            return self._special_entries[key]
        if key in self._entries:
            return self._entries[key]
        if self._special_entries.parent:
            return self.parent.raw_get(key)
        raise InvalidNameError(key)

    def __len__(self):
        return len(self._entries)

    def __contains__(self, key):
        if isinstance(self._special_entries.access, Bag) and key in self._special_entries.access:
            return True
        return key in self._entries or (self.parent and key in self.parent)

    def __iter__(self):
        return iter(Roll(item) for item in self._entries.items())

    def __reversed__(self):
        return reversed(Roll(item) for item in self._entries.items())

    def __bool__(self):
        return True

    if int(os.environ.get('TESTING_ROLLIT', 0)):

        def _to_eval_test_repr(self):
            return self._entries


@Bag.default_ops_impl.add_impl(elements.OverloadOnlyOperator.ITERATE)
def _(obj):
    return iter(obj)


@Bag.default_ops_impl.add_impl(elements.OverloadOnlyOperator.LENGTH)
def _(obj):
    return len(obj)


@Bag.default_ops_impl.add_impl(elements.OneSidedOperator.HAS)
def _(obj, other):
    return other in obj


class Modifier(metaclass=ABCMeta):
    """
    """
    __slots__ = ()

    def call(self, *args, subject):
        """
        """
        scope = context.scope
        with context.new_scope(scope, isolate=True) as scope:
            with context.use_subject(subject):
                context.scope.error = scope.error
                self.modify(*args)
                # scope.subject = context.scope.subject
                return context.scope.subject

    @abstractmethod
    def modify(self, *args):
        """
        """

    @property
    @abstractmethod
    def display_string(self):
        """
        """

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.display_string

    if int(os.environ.get('TESTING_ROLLIT', 0)):

        def _to_eval_test_repr(self):
            return str(self)


InternalObject.register(Modifier)


class RollitBasedModifier(
        namedtuple('_RollitBasedModifierBase', ('parameters', 'body', 'scope', 'display_string')),
        Modifier):
    """
    """

    def __new__(cls, modifier_def, scope):
        target = modifier_def.target
        param_str = ', '.join(modifier_def.parameters)
        if isinstance(target, elements.Access):
            target = target.accessors[-1]
        if target in (None, elements.SpecialReference.NONE):
            display_string = f'[- lambda({param_str}) -]'
        else:
            if isinstance(target, ModelEnumElement):
                # pylint: disable=protected-access
                name = f'<{target._value_}>'
            elif isinstance(target, elements.Reference):
                name = target.value
            else:
                name = target.codeinfo.text[0:target.codeinfo.text.index('<-')].strip()
            display_string = f'[- modifier: {name}({param_str}) -]'
        body = modifier_def.definition
        if not is_valid_iterable(body):
            body = (body,)
        return super().__new__(cls,
                               display_string=display_string,
                               parameters=modifier_def.parameters,
                               body=body,
                               scope=scope)

    def modify(self, *args):
        if args is not None:
            context.scope.load(dict(itertools.zip_longest(self.parameters, args)))
        context.scope.load(self.scope)
        with suppress(LeaveException):
            for statement in self.body:
                context(statement)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.display_string
