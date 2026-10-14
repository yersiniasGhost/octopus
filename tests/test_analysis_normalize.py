"""Missing values arrive at least seven ways; every one of them must read as blank, never as a value."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.normalize import (ABSENT, BLANK, PRESENT, TRANSFORMS, UNMAPPED,  # noqa: E402
                                           is_blank, read_value)

TOKENS = ('nan', 'NaN', 'Unknown')


def test_nan_and_tokens_are_blank():
    for value in (None, float('nan'), '', '   ', 'nan', 'Unknown'):
        assert is_blank(value, (), TOKENS), value
    assert is_blank(-1, (-1,), TOKENS) and is_blank(-1.0, (-1,), TOKENS)
    assert is_blank(0, (0,), TOKENS)  # Cuyahoga poverty_level_percent = 0 co-occurs with NaN income


def test_real_values_are_not_blank():
    for value in (0, 0.0, False, 'No', 42000.0, -0.37):
        assert not is_blank(value, (-1,), TOKENS), value


def test_count_transform():
    count = TRANSFORMS['count']
    assert count(3.0) == 3 and count(2.6) == 3 and count('4') == 4
    assert count(0) is None and count(0.4) is None and count(float('nan')) is None


def test_money_years_and_year_transforms():
    assert TRANSFORMS['money']('$152,000') == 152000.0
    assert TRANSFORMS['money'](154000) == 154000.0
    assert TRANSFORMS['money']('$0') is None
    assert TRANSFORMS['years_range']('15+ years') == 15
    assert TRANSFORMS['years_range']('3-4 years') == 3
    assert TRANSFORMS['years_range']('Less than 1 year') == 0
    assert TRANSFORMS['years_range']('soon') is None
    assert TRANSFORMS['year'](1958) == 1958 and TRANSFORMS['year'](0) is None and TRANSFORMS['year'](1500) is None
    assert TRANSFORMS['positive'](-5) is None and TRANSFORMS['number'](-0.37) == -0.37
    assert TRANSFORMS['number'](True) is None and TRANSFORMS['number']('x') is None


SENIOR = {'paths': ['md_presence_of_senior', 'presence_of_senior'], 'transform': 'value_map',
          'value_map': {'Senior Present': True, 'No Senior Present': False, 'Yes': True, 'No': False}}
INCOME = {'paths': ['estimated_income'], 'transform': 'positive', 'sentinels': [-1]}
HEAT = {'paths': ['heat_type'], 'transform': 'value_map', 'value_map': {'HTP': 1, 'FHA': None}}


def test_read_value_states():
    assert read_value({'estimated_income': 42000.0}, INCOME, TOKENS) == (PRESENT, 42000.0)
    assert read_value({'estimated_income': -1}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({'estimated_income': math.nan}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({'estimated_income': 0}, INCOME, TOKENS) == (BLANK, None)
    assert read_value({}, INCOME, TOKENS) == (ABSENT, None)


def test_blank_first_path_falls_through_to_the_next():
    assert read_value({'md_presence_of_senior': '', 'presence_of_senior': 'Yes'}, SENIOR, TOKENS) == (PRESENT, True)
    assert read_value({'md_presence_of_senior': 'No Senior Present'}, SENIOR, TOKENS) == (PRESENT, False)
    assert read_value({'md_presence_of_senior': ''}, SENIOR, TOKENS) == (BLANK, None)


def test_value_map_misses_are_unmapped_and_null_mappings_absent():
    assert read_value({'md_presence_of_senior': 'Maybe'}, SENIOR, TOKENS) == (UNMAPPED, 'Maybe')
    assert read_value({'heat_type': 'HTP'}, HEAT, TOKENS) == (PRESENT, 1)
    assert read_value({'heat_type': 'FHA'}, HEAT, TOKENS) == (ABSENT, None)


def test_senior_age_is_true_only():
    from src.analysis_engine.normalize import TRANSFORMS
    f = TRANSFORMS['senior_age']
    assert f(65, min_age=65) is True and f('72', min_age=65) is True and f(64, min_age=65) is None
    assert f('abc', min_age=65) is None and f(-1, min_age=65) is None and f(68, min_age=70) is None
