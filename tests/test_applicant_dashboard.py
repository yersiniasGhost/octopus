"""Unit tests for the applicant dashboard service methods.

Uses a MagicMock-wrapped pymongo collection to keep tests fast and
DB-independent. Each test verifies the structure and counts of the
returned dict without requiring a live Mongo connection.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.campaign_data_service import CampaignDataService


def _make_service(applications_docs=None, applicants_docs=None, exposures_docs=None,
                  applications_aggregate=None, applicants_aggregate=None, exposures_aggregate=None):
    """Build a CampaignDataService with mocked collections.

    Pass per-call return values for find/aggregate as needed.
    """
    with patch('app.services.campaign_data_service.MongoClient'), \
         patch('app.services.campaign_data_service.EnvVars'):
        service = CampaignDataService()

    db = MagicMock()
    service.db = db

    db.applications.count_documents = MagicMock(return_value=len(applications_docs or []))
    db.applicants.count_documents = MagicMock(return_value=len(applicants_docs or []))
    db.exposures.count_documents = MagicMock(return_value=len(exposures_docs or []))

    # `find()` chains: .sort(...).limit(...) → iterable cursor. Make a chainable mock.
    _app_cursor = MagicMock()
    _app_cursor.sort.return_value = _app_cursor
    _app_cursor.limit.return_value = iter(applications_docs or [])
    db.applications.find = MagicMock(return_value=_app_cursor)
    db.applications.aggregate = MagicMock(return_value=iter(applications_aggregate or []))
    db.applicants.aggregate = MagicMock(return_value=iter(applicants_aggregate or []))
    db.exposures.aggregate = MagicMock(return_value=iter(exposures_aggregate or []))

    return service


def _chainable_find(docs):
    """Return a MagicMock matching pymongo's find().sort(...).limit(...) cursor chain."""
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.limit.return_value = iter(docs)
    return MagicMock(return_value=cursor)


# ===========================
# Overview tab tests
# ===========================

def test_overview_returns_required_keys():
    service = _make_service()
    result = service._build_applicant_overview()
    assert set(result.keys()) == {'kpis', 'time_series', 'match_quality', 'recent_applicants'}
    assert set(result['kpis'].keys()) == {
        'total_applicants', 'this_month', 'match_rate_pct', 'top_county', 'top_channel'
    }


def test_overview_kpis_compute_match_rate_correctly():
    """Match rate = (applications with non-null participant_match.match_method) / total * 100."""
    service = _make_service()
    # Stub the count_documents calls in order: total, this_month, matched
    service.db.applications.count_documents = MagicMock(side_effect=[100, 17, 75])
    # Stub aggregates (top county, top channel)
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([{'_id': 'Franklin', 'count': 40}]),  # top county
        iter([{'_id': 'text', 'count': 30}]),       # top channel
        iter([]),                                     # time series (empty for this test)
        iter([]),                                     # match quality (empty for this test)
    ])
    service.db.applications.find = _chainable_find([])

    result = service._build_applicant_overview()
    assert result['kpis']['total_applicants'] == 100
    assert result['kpis']['this_month'] == 17
    assert result['kpis']['match_rate_pct'] == 75.0
    assert result['kpis']['top_county'] == 'Franklin'
    assert result['kpis']['top_channel'] == 'text'


def test_overview_handles_zero_applicants_without_division_error():
    service = _make_service()
    service.db.applications.count_documents = MagicMock(return_value=0)
    service.db.applications.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.find = _chainable_find([])

    result = service._build_applicant_overview()
    assert result['kpis']['total_applicants'] == 0
    assert result['kpis']['match_rate_pct'] == 0.0
    assert result['kpis']['top_county'] is None
    assert result['kpis']['top_channel'] is None


def test_overview_recent_applicants_projects_flat_shape():
    sample = [{
        'applicant': {'first_name': 'Jane', 'last_name': 'Doe'},
        'address': {'county': 'Franklin', 'zip': '43210'},
        'attribution': {'utm': {'utm_medium': 'text'}},
        'entry_date': datetime(2026, 4, 1, tzinfo=timezone.utc),
        'participant_match': {'match_method': 'email'},
    }]
    service = _make_service()
    service.db.applications.count_documents = MagicMock(return_value=1)
    service.db.applications.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.find = _chainable_find(sample)

    result = service._build_applicant_overview()
    rows = result['recent_applicants']
    assert len(rows) == 1
    assert rows[0]['name'] == 'Jane Doe'
    assert rows[0]['county'] == 'Franklin'
    assert rows[0]['zip'] == '43210'
    assert rows[0]['channel'] == 'text'
    assert rows[0]['match_method'] == 'email'
    # entry_date should be ISO-formatted string for JSON safety
    assert isinstance(rows[0]['entry_date'], str)


def test_overview_match_quality_buckets_null_as_unmatched():
    service = _make_service()
    service.db.applications.count_documents = MagicMock(return_value=10)
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([]),  # top county
        iter([]),  # top channel
        iter([]),  # time series
        iter([{'_id': 'email', 'count': 6}, {'_id': None, 'count': 4}]),  # match quality
    ])
    service.db.applications.find = _chainable_find([])

    result = service._build_applicant_overview()
    assert result['match_quality']['labels'] == ['email', 'unmatched']
    assert result['match_quality']['counts'] == [6, 4]
