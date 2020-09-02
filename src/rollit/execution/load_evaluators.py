#pylint: disable=too-many-function-args
"""
"""
from contextlib import suppress

from ..ast import elements, constants, is_valid_iterable
from ..exceptions import RollitTypeError
from ..internal_objects import Roll, Bag, OopsException, RestartException, LeaveException, \
        RollitBasedModifier
from ..langref import OPERATORS

__all__ = ()


@elements.Reduce.reducer
@elements.Reduce.evaluator
def _(self, context):
    return context.reduce(context(self.value))


@elements.Assignment.evaluator
def _(self, context):
    if isinstance(self.target, elements.Reference):
        context[self.target.value] = context(self.value)
    else:
        # target = context.access_obj(self.target.accessing, self.target.accessors[:-1])
        target = context(
            elements.Access(self.target.accessing,
                            self.target.accessors[:-1],
                            codeinfo=self.target.codeinfo))
        final_accessor = context.full_reduce(self.target.accessors[-1])
        if isinstance(self.target, elements.Reference):
            final_accessor = final_accessor.value
        target[final_accessor] = context(self.value)


@elements.Access.evaluator
def _(self, context):
    accessing = context(self.accessing)
    for accessor in self.accessors:
        if isinstance(accessor, elements.Reduce):
            accessing = accessing[context(accessor)]
        else:
            with context.now_access(accessing):
                accessing = context(accessor)
    return accessing


@elements.Enlarge.evaluator
def _(self, context):
    size = 1 if self.size is None else self.size
    return Roll(context(self.value) for _ in range(context(size)))


@elements.Dice.evaluator
def _(self, context):
    return self


@elements.Negation.evaluator
def _(self, context):
    return not context(self.value)


@elements.BinaryOp.evaluator
def _(self, context):
    left = context(self.left)
    right = context(self.right)
    #FIXME handle string concatination and other operators
    # pylint: disable=no-member
    if self.op in OPERATORS.math:
        left = context.full_reduce(left)
        right = context.full_reduce(right)
    return constants.OPERATOR_MAP[self.op](left, right)


@elements.NewBag.evaluator
def _(self, context):
    return Bag()


# Because these objects are predicated, we can just have their children be evaluated
@elements.ButIf.evaluator
@elements.UseIf.evaluator
@elements.IfThen.evaluator
def _(self, context):
    return context.evaluate_children(self)


@elements.ClearValue.evaluator
def _(self, context):
    to_clear = self.value
    if isinstance(to_clear, elements.Access):
        #TODO
        base = context(
            elements.Access(to_clear.accessing, to_clear.accessors[:-1], codeinfo=self.codeinfo))
        last = context.get_accessor_value(to_clear.accessors[-1])
        with suppress(LookupError):
            try:
                del base[last]
            except TypeError:
                raise RollitTypeError()
    else:
        del context[to_clear]


@elements.StringLiteral.evaluator
@elements.StringLiteral.reducer
def _(self, context):
    return self.value


@elements.Reference.evaluator
def _(self, context):
    return context[self.value]


@elements.Oops.evaluator
def _(self, context):
    raise OopsException(context(self.value))


@elements.Attempt.evaluator
def _(self, context):
    raise NotImplementedError()


@elements.Leave.evaluator
def _(self, context):
    raise LeaveException()


@elements.Modify.evaluator
def _(self, context):
    context.scope.subject = context(self.subject)
    for name, args, _ in self.modifiers:
        modifier = context(name)
        try:
            modifier.modify(*(context(a) for a in args), context=context)
        except LeaveException:
            continue
    return context.scope.subject


@elements.Load.evaluator
def _(self, context):
    raise NotImplementedError()


@elements.ForEvery.evaluator
def _(self, context):
    raise NotImplementedError()


@elements.ModifierDef.evaluator
def _(self, context):
    modifier = RollitBasedModifier(self, context.scope)
    if self.target in (None, elements.SpecialReference.NONE):
        return modifier
    with context.now_access(context.scope.parent):
        context(elements.Assignment(self.target, modifier, codeinfo=self.codeinfo))
    return None


@elements.Restart.evaluator
def _(self, context):
    raise NotImplementedError()


@elements.UntilDo.evaluator
def _(self, context):

    def _before():
        if not context(self.until):
            if self.otherwise:
                context(self.otherwise)
            return True
        return False

    if _before():
        return
    do = self.do
    if not is_valid_iterable(do):
        do = (do,)
    ignore_predicate = True
    while ignore_predicate or not context(self.until):
        ignore_predicate = False
        try:
            for stmt in do:
                context(stmt)
        except RestartException as e:
            if e.name and e.name not in (elements.SpecialReference.NONE, self.name):
                raise
            if e.location_specifier == elements.RestartLocationSpecifier.AT:
                ignore_predicate = True
            elif e.location_specifier == elements.RestartLocationSpecifier.BEFORE:
                if _before():
                    return
            elif e.location_specifier == elements.RestartLocationSpecifier.AFTER:
                return


@elements.Dice.reducer
def _(self, context):
    number_of_dice = context(self.number_of_dice)
    return Roll([context.roll(context(self.sides)) for _ in range(number_of_dice)])


@elements.Reference.reducer
def _(self, context):
    return context.reduce(context(self))
