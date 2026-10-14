"""Archetypes are queries, not stored labels. These filters are a contract the bolt-od port must reproduce."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.archetypes import compile_archetype, proxy_mask  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402

REG = load_registry()
RULES = REG.rules
NR = {'nonres': {'$ne': True}}


def test_bill_assistance():
    assert compile_archetype('bill_assistance', RULES) == (
        {'$and': [NR, {'dims.0': {'$gte': 2}}]}, {'$and': [NR, {'dims.0': {'$gte': 0}}]})


def test_weatherization_needs_multi_unit_known():
    match, known = compile_archetype('weatherization', RULES)
    assert match == {'$and': [NR, {'dims.0': {'$gte': 1}}, {'dims.2': {'$gte': 1}}, {'multi_unit': {'$ne': True, '$exists': True}}]}
    assert known == {'$and': [NR, {'dims.0': {'$gte': 0}}, {'dims.2': {'$gte': 0}}, {'multi_unit': {'$exists': True}}]}


def test_electrification_allows_unknown_owner():
    match, known = compile_archetype('electrification', RULES)
    assert match == {'$and': [NR, {'dims.5': {'$eq': 2}}, {'owner': {'$ne': False}}]}
    assert known == {'$and': [NR, {'dims.5': {'$gte': 0}}]}


def test_likely_no_benefit_requires_four_known_dims():
    known_count = {'$expr': {'$gte': [{'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}, 4]}}
    assert compile_archetype('likely_no_benefit', RULES) == (
        {'$and': [known_count, NR, {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, {'$and': [known_count, NR]})


def test_behavioural_needs_known_zero_income():
    assert compile_archetype('behavioural', RULES) == (
        {'$and': [NR, {'dims.3': {'$gte': 1}}, {'dims.0': {'$eq': 0}}]}, {'$and': [NR, {'dims.3': {'$gte': 0}}, {'dims.0': {'$gte': 0}}]})


def test_denominators_exclude_nonres():
    match, known = compile_archetype('bill_assistance', RULES)
    assert {'nonres': {'$ne': True}} in match['$and'] and {'nonres': {'$ne': True}} in known['$and']
    match, known = compile_archetype('likely_no_benefit', RULES)
    assert {'nonres': {'$ne': True}} in known['$and']


def test_proxy_mask_covers_dims_used_by_the_archetype():
    assert proxy_mask('weatherization', RULES) == 1 << REG.dims.index('building_inefficiency') | 1 << 0
    assert proxy_mask('likely_no_benefit', RULES) == 0
