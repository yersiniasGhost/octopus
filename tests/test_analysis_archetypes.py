"""Archetypes are queries, not stored labels. These filters are a contract the bolt-od port must reproduce."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.archetypes import compile_archetype  # noqa: E402
from src.analysis_engine.registry import load_registry  # noqa: E402

RULES = load_registry().rules


def test_bill_assistance():
    assert compile_archetype('bill_assistance', RULES) == (
        {'$and': [{'dims.0': {'$gte': 2}}]}, {'$and': [{'dims.0': {'$gte': 0}}]})


def test_weatherization_needs_multi_unit_known():
    match, known = compile_archetype('weatherization', RULES)
    assert match == {'$and': [{'dims.0': {'$gte': 1}}, {'dims.2': {'$gte': 1}}, {'multi_unit': {'$ne': True}}]}
    assert known == {'$and': [{'dims.0': {'$gte': 0}}, {'dims.2': {'$gte': 0}}, {'multi_unit': {'$exists': True}}]}


def test_electrification_allows_unknown_owner():
    match, known = compile_archetype('electrification', RULES)
    assert match == {'$and': [{'dims.5': {'$eq': 2}}, {'owner': {'$ne': False}}]}
    assert known == {'$and': [{'dims.5': {'$gte': 0}}]}


def test_likely_no_benefit_requires_four_known_dims():
    known_count = {'$expr': {'$gte': [{'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}, 4]}}
    assert compile_archetype('likely_no_benefit', RULES) == (
        {'$and': [known_count, {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, known_count)
