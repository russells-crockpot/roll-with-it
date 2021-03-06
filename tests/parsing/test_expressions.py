# pylint: disable=missing-docstring,unused-import,no-member
from .util import create_scripttest_func

test_atoms = create_scripttest_func('atoms')
test_references = create_scripttest_func('references')
test_math = create_scripttest_func('math')
test_dice = create_scripttest_func('dice')
test_reduce = create_scripttest_func('reduce')
test_access = create_scripttest_func('access')
test_rolls = create_scripttest_func('rolls')
