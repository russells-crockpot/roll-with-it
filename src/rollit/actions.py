# pylint: disable=unexpected-keyword-arg,no-value-for-parameter,too-many-public-methods
# pylint: disable=no-member,missing-function-docstring,redefined-outer-name
"""
"""
import inspect
import functools
import re
from collections import namedtuple
from collections.abc import Mapping
from contextlib import suppress

from . import model
from .exceptions import InvalidNameError
from .grammar import TreeNode

__all__ = ()

_ESCAPE_STR_PAT = re.compile(r"\\([\\runftvb'])")
#FIXME Unicode escapes
_ESCAPE_MAP = {
    'n': '\n',
    'r': '\r',
    'f': '\f',
    "'": "'",
    'v': '\v',
    'b': '\b',
    '\\': '\\',
}

_PredicatedStatement = namedtuple('_PredicatedStatement', ('predicate', 'statement'))


class _BaseInternalSingleValue(tuple):

    def __new__(cls, value):
        return super().__new__(cls, (value,))

    def __str__(self):
        return f'{type(self).__name__}{super().__str__()}'

    def __repr__(self):
        return f'{type(self).__name__}{super().__repr__()}'


_Otherwise = type('_Otherwise', (_BaseInternalSingleValue,), {})
_LoopName = type('_LoopName', (_BaseInternalSingleValue,), {})
_LoopBody = type('_LoopBody', (_BaseInternalSingleValue,), {})

_ELEMENT_TYPES = (model.ModelElement, _PredicatedStatement, _BaseInternalSingleValue)


def _is_valid_iterable(node):
    return isinstance(node, (list, tuple)) and not isinstance(node, _ELEMENT_TYPES)


def _unwrap_node(node):
    if _is_valid_iterable(node):
        items = type(node)(nd for nd in (_unwrap_node(n) for n in node) if nd)
        with suppress(TypeError):
            if len(items) == 1 and _is_valid_iterable(node):
                return items[0]
        return items
    if not isinstance(node, TreeNode):
        return node
    elements = _unwrap_node(node.elements)
    with suppress(TypeError):
        if len(elements) == 1 and _is_valid_iterable(node):
            return elements[0]
    return elements


# pylint: disable=too-complex
def elements_to_values(*, text_only=False, elements_only=False, must_have_text=False, unwrap=True):
    """
    """

    def _decorator(func):

        @functools.wraps(func)
        def _wrapper(*args):
            values = []
            for element in args[-1]:
                if isinstance(element, (int, float)):
                    values.append(element)
                    continue
                if not element:
                    continue
                if isinstance(element, TreeNode):
                    if must_have_text and not element.text.strip():
                        continue
                    if elements_only:
                        element = element.elements
                    elif text_only:
                        element = element.text.strip()
                    else:
                        element = element.elements or element.text.strip()
                if element:
                    if unwrap:
                        element = _unwrap_node(element)
                    values.append(element)
            return func(*args[:-1], values)

        return _wrapper

    return _decorator


class CreateTypeFunc(
        namedtuple('_CreateTypeFuncBase',
                   ('model_cls', 'single_value', 'defaults', 'value_indexes'))):
    """
    """

    def __new__(cls, model_cls, value_indexes=None, single_value=None, defaults=None):
        if single_value is None:
            single_value = True
            if inspect.isclass(model_cls) \
                    and issubclass(model_cls, (*_ELEMENT_TYPES, Mapping)) \
                    and not issubclass(model_cls, model.SingleValueElement):
                single_value = False
        if single_value and defaults:
            defaults = model_cls(defaults)
        if isinstance(value_indexes, dict):
            value_indexes = tuple(value_indexes.items())
        return super().__new__(
            cls,
            model_cls=model_cls,
            single_value=single_value,
            defaults=defaults,
            value_indexes=value_indexes,
        )

    @elements_to_values()
    def __call__(self, text, start, end, values):
        if self.single_value:
            if not values:
                return self.defaults
            if self.value_indexes is not None:
                return self.model_cls(values[self.value_indexes])
            return self.model_cls(values[0])
        if self.value_indexes:
            # TODO add defaults
            mapped_values = {name: values[idx] for name, idx in self.value_indexes}
            return self.model_cls(**mapped_values)
        return self.model_cls(*values)


binary_op = CreateTypeFunc(model.BinaryOp)
use_if = CreateTypeFunc(model.UseIf, (('use', 1), ('predicate', 3), ('otherwise', 5)))
length = CreateTypeFunc(model.Length, -1, single_value=True)
dice = CreateTypeFunc(model.Dice, (('number_of_dice', 0), ('sides', -1)))


def _to_tuple(item):
    if isinstance(item, _ELEMENT_TYPES) or not isinstance(item, (list, tuple)):
        return (item,)
    if isinstance(item, list):
        return tuple(item)
    return item


def _negate(element):
    if isinstance(element, model.Negation):
        return element.value
    return model.Negation(element)


# The Actions


def keyword(text, start, end, values):
    raise InvalidNameError(f'{text[start:end]} is a keyword and cannot be used  .')


@elements_to_values(text_only=True)
def int_(text, start, end, values):
    return int(''.join(values))


@elements_to_values(text_only=True)
def float_(text, start, end, values):
    return float(''.join(values))


@elements_to_values(text_only=True)
def string(text, start, end, values):
    return model.StringLiteral(
        _ESCAPE_STR_PAT.sub(lambda m: _ESCAPE_MAP[m.group(1)], text[start + 1:end - 1]))


@elements_to_values()
def items_with_ends(text, start, end, values):
    return _to_tuple(values)


@elements_to_values()
def items_no_ends(text, start, end, values):
    if len(values) == 2:
        return ()
    return tuple(values[1:-1])


def text(text, start, end, values):
    return text[start:end]


def special_ref(text, start, end, values):
    return model.SpecialReference(text[start:end])


@elements_to_values()
def accessor(text, start, end, values):
    return values[-1]


def ignore(*args):
    return None


@elements_to_values()
def parens(text, start, end, values):
    return values[1]


@elements_to_values()
def negate(text, start, end, values):
    return _negate(values[-1])


@elements_to_values()
def modifier_call(text, start, end, values):
    values = values[1:]
    if len(values) == 1:
        return model.ModifierCall(modifier=values[0], args=())
    return model.ModifierCall(modifier=values[0], args=_to_tuple(values[-1]))


@elements_to_values()
def modify(text, start, end, values):
    return model.Modify(subject=values[0], modifiers=_to_tuple(values[-1]))


@elements_to_values()
def arg_list(text, start, end, values):
    values = values[1:-1]
    if len(values) == 2 and isinstance(values[0], list):
        values = (*values[0], values[1])
    return tuple(values)


@elements_to_values()
def access(text, start, end, values):
    return model.Access(accessing=values[0], accessors=_to_tuple(values[-1]))


@elements_to_values()
def reduce(text, start, end, values):
    value = values[1]
    if value == '*':
        value = model.SpecialReference.ALL
    return model.Reduce(value)


@elements_to_values()
def enlarge(text, start, end, values):
    values = values[1:-1]
    size = value = None
    sep_idx = values.index('@')
    with suppress(IndexError):
        size = values[:sep_idx][0]
    with suppress(IndexError):
        value = values[sep_idx + 1:][0]
    return model.Enlarge(size=size, value=value)


@elements_to_values()
def assignment(text, start, end, values):
    target, op, value = values
    if len(op) > 1:
        value = model.BinaryOp(left=target, op=op[:-1], right=value)
    return model.Assignment(target=target, value=value)


def leave(*args):
    return model.SingleWordStatment.LEAVE


@elements_to_values()
def if_then(text, start, end, values):
    return _PredicatedStatement(predicate=values[1], statement=values[-1])


@elements_to_values()
def otherwise(text, start, end, values):
    return _Otherwise(values[-1])


@elements_to_values()
def unless(text, start, end, values):
    return _PredicatedStatement(predicate=values[1], statement=values[-1])


@elements_to_values()
def except_when(text, start, end, values):
    return _PredicatedStatement(predicate=values[2], statement=values[-1])


@elements_to_values()
def create_bag(text, start, end, values):
    return tuple(model.CreateBag(item) for item in _to_tuple(values[-1]))


@elements_to_values()
def load_from_into(text, start, end, values):
    if values[1] == '*':
        to_load = (model.SpecialReference.ALL,)
    else:
        to_load = _to_tuple(values[1])
    return model.Load(
        to_load=to_load,
        load_from=values[1],
        load_into=values[-1],
    )


@elements_to_values()
def load_from(text, start, end, values):
    return model.Load(
        to_load=_to_tuple(values[1]),
        load_from=values[1],
        load_into=model.SpecialReference.ROOT,
    )


@elements_to_values()
def load_into(text, start, end, values):
    return model.Load(
        to_load=(model.SpecialReference.ALL,),
        load_from=values[1],
        load_into=values[-1],
    )


@elements_to_values()
def load(text, start, end, values):
    items = []
    for item in _to_tuple(values[-1]):
        items.append(
            model.Load(
                to_load=(model.SpecialReference.ALL,),
                load_from=item,
                load_into=item,
            ))
    return items


# pylint: disable=protected-access
@elements_to_values()
def restart(text, start, end, values):
    location_specifier = model.RestartLocationSpecifier(values[0])
    target = model.SpecialReference.NONE
    with suppress(IndexError):
        target = values[1]
    if isinstance(target, model.SpecialReference):
        return getattr(model.Restart, f'{location_specifier._name_}_{target._name_}')
    return model.Restart(location_specifier=location_specifier, target=target)


@elements_to_values()
def if_stmt(text, start, end, values):
    if_ = values.pop(0)
    otherwise = unlesses = None
    with suppress(IndexError):
        otherwise = values.pop(-1)
        if isinstance(otherwise, _Otherwise):
            otherwise = otherwise[0]
            if values:
                unlesses = _to_tuple(values[0])
        else:
            unlesses = _to_tuple(otherwise)
            otherwise = None
    rval = model.If(
        predicate=if_.predicate,
        then=if_.statement,
        otherwise=otherwise,
    )
    if unlesses:
        previous = otherwise
        for unless in unlesses:
            previous = model.If(predicate=unless.predicate,
                                then=unless.statement,
                                otherwise=previous)
        rval = model.If(
            predicate=_negate(rval.predicate),
            then=previous,
            otherwise=rval.then,
        )
    return rval


@elements_to_values()
def loop_name(text, start, end, values):
    return _LoopName(values[1])


@elements_to_values()
def loop_body(text, start, end, values):
    return _LoopBody(values[-1])


@elements_to_values()
def until_do(text, start, end, values):
    raise NotImplementedError()


@elements_to_values()
def for_every(text, start, end, values):
    # get rid of 'for' and 'every'
    values = values[2:]
    loop_name = None
    if isinstance(values[0], _LoopName):
        loop_name = values.pop(0)[0]
    return model.ForEvery(
        name=loop_name,
        item_name=values[0],
        iterable=values[2],
        do=values[-1][0],
    )


@elements_to_values()
def modifier_def(text, start, end, values):
    target = values[0]
    values = values[2:]
    idx = values.index(':')
    params = values[:idx] or None
    if params:
        params = params[0]
        if not _is_valid_iterable(params):
            params = (params,)
    body = values[idx + 1:] or (None,)
    return model.ModifierDef(
        target=target,
        parameters=params,
        definition=body[0],
    )


@elements_to_values()
def block(text, start, end, values):
    values = values[1:-1]
    if len(values) > 1 and _is_valid_iterable(values[0]):
        return tuple((*values[0], values[1]))
    return _to_tuple(values)


def empty_block(*args):
    return ()


@elements_to_values()
def statements(text, start, end, values):
    return values