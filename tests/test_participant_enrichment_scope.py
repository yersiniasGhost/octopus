"""Which participants an enrichment run is allowed to touch.

3,265 participants carry an embedded thermal.* copy taken 2026-01-04. The T-15
migration replaced the fields those copies mirror, so they now hold superseded
legacy values (kwh_hl_r2 and friends) that no longer exist on the source record.

The tool had two modes and neither refreshes them:
  * default skips participants that are already enriched -- precisely the stale
    ones -- and enriches the 11,068 that never had thermal data
  * --force refreshes the stale 3,265 AND writes a new thermal block to those
    same 11,068

Refreshing a stale copy and enriching a participant for the first time are
different jobs with different blast radii. --only-refresh is the first one.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import enrich_thermal_loads as enrich  # noqa: E402


def args(**kwargs):
    base = {'county': None, 'force': False, 'only_refresh': False}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_default_run_skips_participants_that_are_already_enriched():
    query = enrich.build_participant_query(args())

    assert query['thermal.enriched_at'] == {'$exists': False}


def test_force_run_places_no_enrichment_filter():
    query = enrich.build_participant_query(args(force=True))

    assert 'thermal.enriched_at' not in query
    assert 'thermal' not in query


def test_only_refresh_selects_participants_that_already_carry_thermal():
    query = enrich.build_participant_query(args(only_refresh=True))

    assert query['thermal'] == {'$exists': True}


def test_only_refresh_does_not_also_exclude_them():
    """The default skip filter and the refresh filter are contradictory."""
    query = enrich.build_participant_query(args(only_refresh=True))

    assert 'thermal.enriched_at' not in query


def test_only_refresh_still_honours_a_county_restriction():
    query = enrich.build_participant_query(args(only_refresh=True, county='Franklin'))

    assert query['thermal'] == {'$exists': True}
    assert query['$or'] == [{'linkage.county_key': 'Franklin'},
                            {'linkage.county_key': 'FranklinCounty'}]


def test_only_refresh_implies_force_so_the_per_record_guard_cannot_skip_them():
    """enrich_participants re-checks enriched_at per document; that guard would
    skip every single record --only-refresh just selected."""
    assert enrich.refreshes_existing(args(only_refresh=True)) is True
    assert enrich.refreshes_existing(args(force=True)) is True
    assert enrich.refreshes_existing(args()) is False
