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

    db.applications.find = _chainable_find(applications_docs or [])
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


def test_overview_six_months_ago_uses_first_of_month_to_avoid_invalid_day():
    """Regression: six_months_ago must snap to day=1.

    Previously the impl did `now.replace(month=X)` keeping `now.day`, which
    raised ValueError on day-31 months when the target month was shorter
    (Mar 31 → Sep, May 31 → Nov, Aug 31 → Feb, Oct 31 → Apr, Dec 31 → Jun).

    We patch `datetime.datetime` on the stdlib `datetime` module — the impl
    does `from datetime import datetime, timezone` *inside* the function,
    so the patch resolves on each call. We then sweep across each historically
    failing day-31 month and (a) confirm no ValueError, (b) confirm the
    time-series $match $gte is anchored to day=1.
    """
    import datetime as _dt_mod
    from datetime import datetime as _dt, timezone as _tz
    from unittest.mock import patch as _patch

    real_datetime = _dt_mod.datetime

    class _FakeDatetime(real_datetime):
        _frozen_now = None

        @classmethod
        def now(cls, tz=None):
            return cls._frozen_now

    captured_pipelines = []

    def _capture(pipeline):
        captured_pipelines.append(pipeline)
        return iter([])

    failing_dates = [
        _dt(2026, 3, 31, 12, 0, 0, tzinfo=_tz.utc),
        _dt(2026, 5, 31, 12, 0, 0, tzinfo=_tz.utc),
        _dt(2026, 8, 31, 12, 0, 0, tzinfo=_tz.utc),
        _dt(2026, 10, 31, 12, 0, 0, tzinfo=_tz.utc),
        _dt(2026, 12, 31, 12, 0, 0, tzinfo=_tz.utc),
    ]

    for fake_now in failing_dates:
        captured_pipelines.clear()
        _FakeDatetime._frozen_now = fake_now

        service = _make_service()
        service.db.applications.count_documents = MagicMock(return_value=0)
        service.db.applications.aggregate = MagicMock(side_effect=_capture)
        service.db.applications.find = _chainable_find([])

        with _patch('datetime.datetime', _FakeDatetime):
            # Must not raise ValueError("day is out of range for month").
            service._build_applicant_overview()

        # Third aggregate call is the time-series pipeline.
        ts_pipeline = captured_pipelines[2]
        gte_value = ts_pipeline[0]['$match']['entry_date']['$gte']
        assert isinstance(gte_value, real_datetime)
        assert gte_value.day == 1, f"expected day=1, got {gte_value.day} for now={fake_now}"


# ===========================
# Demographics tab tests
# ===========================

def test_demographics_returns_required_keys():
    service = _make_service()
    service.db.applications.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.count_documents = MagicMock(return_value=0)
    result = service._build_applicant_demographics()
    assert set(result.keys()) == {'age', 'income', 'household_size', 'energy_burden', 'income_age_scatter'}
    for key in ('age', 'income', 'household_size'):
        assert set(result[key].keys()) == {'labels', 'counts', 'n'}


def test_demographics_age_bins_match_spec():
    """Spec bins: <30, 30-44, 45-59, 60-74, 75+."""
    service = _make_service()
    # Mongo $bucket returns _id = lower bound and a count per bucket.
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([
            {'_id': 0, 'count': 5},   # <30
            {'_id': 30, 'count': 12}, # 30-44
            {'_id': 45, 'count': 20}, # 45-59
            {'_id': 60, 'count': 8},  # 60-74
            {'_id': 75, 'count': 3},  # 75+
        ]),
        iter([]),  # income
        iter([]),  # household_size
        iter([]),  # top counties
        iter([]),  # scatter
    ])
    service.db.applicants.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.count_documents = MagicMock(return_value=616)

    result = service._build_applicant_demographics()
    assert result['age']['labels'] == ['<30', '30-44', '45-59', '60-74', '75+']
    assert result['age']['counts'] == [5, 12, 20, 8, 3]
    assert result['age']['n'] == 48


def test_demographics_energy_burden_caption_includes_total_applications():
    service = _make_service()
    service.db.applications.aggregate = MagicMock(return_value=iter([]))
    service.db.applicants.aggregate = MagicMock(return_value=iter([
        {'_id': 0, 'count': 10},
        {'_id': 0.06, 'count': 20},
        {'_id': 0.10, 'count': 15},
        {'_id': 0.15, 'count': 5},
    ]))
    service.db.applications.count_documents = MagicMock(return_value=616)

    result = service._build_applicant_demographics()
    assert result['energy_burden']['labels'] == ['<6%', '6-10%', '10-15%', '15%+']
    assert result['energy_burden']['counts'] == [10, 20, 15, 5]
    assert result['energy_burden']['n'] == 50
    assert result['energy_burden']['total'] == 616


def test_demographics_scatter_groups_top_3_counties_plus_other():
    service = _make_service()
    # First 3 aggregates: age, income, household_size (all empty)
    # Then top-counties aggregate, then scatter aggregate
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([]),  # age
        iter([]),  # income
        iter([]),  # household_size
        iter([     # top counties
            {'_id': 'Franklin', 'count': 100},
            {'_id': 'Delaware', 'count': 50},
            {'_id': 'Fairfield', 'count': 30},
        ]),
        iter([     # scatter points
            {'county': 'Franklin', 'age': 45, 'income': 50000},
            {'county': 'Delaware', 'age': 60, 'income': 70000},
            {'county': 'Madison', 'age': 35, 'income': 40000},  # not top-3 → 'Other'
        ]),
    ])
    service.db.applicants.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.count_documents = MagicMock(return_value=616)

    result = service._build_applicant_demographics()
    series = {s['county']: s['points'] for s in result['income_age_scatter']['series']}
    assert set(series.keys()) >= {'Franklin', 'Delaware', 'Fairfield', 'Other'}
    assert {'x': 35, 'y': 40000} in series['Other']
    assert {'x': 45, 'y': 50000} in series['Franklin']


# ===========================
# Attribution tab tests
# ===========================

def test_attribution_returns_required_keys():
    service = _make_service()
    service.db.applications.aggregate = MagicMock(return_value=iter([]))
    service.db.applications.count_documents = MagicMock(return_value=0)
    service.db.exposures.count_documents = MagicMock(return_value=0)
    result = service._build_applicant_attribution()
    assert set(result.keys()) == {'utm_medium', 'utm_source', 'utm_campaign', 'channel_conversion'}


def test_attribution_utm_medium_buckets_null_as_direct_unknown():
    service = _make_service()
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([{'_id': 'text', 'count': 30}, {'_id': None, 'count': 10}]),  # utm_medium
        iter([]),  # utm_source
        iter([]),  # utm_campaign
        iter([]), iter([]), iter([]), iter([]),  # 4× per-channel application counts
    ])
    service.db.applications.count_documents = MagicMock(return_value=0)
    service.db.exposures.count_documents = MagicMock(return_value=0)

    result = service._build_applicant_attribution()
    assert result['utm_medium']['labels'] == ['text', 'Direct/Unknown']
    assert result['utm_medium']['counts'] == [30, 10]


def test_attribution_channel_conversion_table_computes_rate():
    """Conversion rate = applications / exposures * 100, per channel."""
    service = _make_service()
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([]),  # utm_medium
        iter([]),  # utm_source
        iter([]),  # utm_campaign
    ])
    # 4 channels: text, email, mailer, letter — each has its own count_documents call
    service.db.applications.count_documents = MagicMock(side_effect=[100, 50, 5, 2])
    service.db.exposures.count_documents = MagicMock(side_effect=[1000, 2000, 100, 50])

    result = service._build_applicant_attribution()
    by_channel = {row['channel']: row for row in result['channel_conversion']}
    assert by_channel['text']['exposures'] == 1000
    assert by_channel['text']['applications'] == 100
    assert by_channel['text']['conversion_rate'] == 10.0
    assert by_channel['email']['conversion_rate'] == 2.5
    # Zero exposures → 0.0 rate, no division error
    service2 = _make_service()
    service2.db.applications.aggregate = MagicMock(return_value=iter([]))
    service2.db.applications.count_documents = MagicMock(return_value=0)
    service2.db.exposures.count_documents = MagicMock(return_value=0)
    result2 = service2._build_applicant_attribution()
    for row in result2['channel_conversion']:
        assert row['conversion_rate'] == 0.0


def test_attribution_utm_source_and_campaign_buckets_null_as_none():
    """utm_source and utm_campaign use '(none)' as the null label, not 'Direct/Unknown'."""
    service = _make_service()
    service.db.applications.aggregate = MagicMock(side_effect=[
        iter([]),  # utm_medium
        iter([{'_id': 'google', 'count': 5}, {'_id': None, 'count': 2}]),   # utm_source
        iter([{'_id': 'spring', 'count': 8}, {'_id': None, 'count': 3}]),   # utm_campaign
    ])
    service.db.applications.count_documents = MagicMock(return_value=0)
    service.db.exposures.count_documents = MagicMock(return_value=0)

    result = service._build_applicant_attribution()
    assert result['utm_source']['labels'] == ['google', '(none)']
    assert result['utm_source']['counts'] == [5, 2]
    assert result['utm_campaign']['labels'] == ['spring', '(none)']
    assert result['utm_campaign']['counts'] == [8, 3]
