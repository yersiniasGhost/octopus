"""Frame assembly for the fable model series.

Enforces the universal data-quality gates from
``.claude_docs/20260708_1635_bayesian_model_proposals.md`` in ONE place:

1. Dedupe exposures on (participant_id, campaign_id).
2. Normalize county_key (strip 'County' suffix).
3. Weather models use only campaigns with weather.status == 'ok'.
4. Adjust with estimated_income (99.8% coverage), not income_level (13.2%).
5. Z-score continuous predictors in-model; persist scaler params.
6. `replied` is the universal text outcome; `clicked` only for the 2026
   IMPACT cohort (tracking-regime finding #5).
"""
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from core import bootstrap  # noqa: F401  (sys.path side effect)

MESSAGE_TYPES = ['urgency_deadline', 'savings_financial', 'relief_reassurance',
                 'informational', 'personalized_qualified', 'motivational_struggle']

PARTICIPANT_COVARIATES = ['estimated_income', 'household_size', 'total_energy_burden']

# Sparse Franklin-enrichment demographics: exported for the analyst, only used
# by models as explicit variants (coverage 13-47%, Franklin-skewed).
SPARSE_DEMOGRAPHICS = ['owner_age', 'presence_of_children', 'presence_of_senior',
                       'number_of_adults']

# Days between send and receipt. Physical mail lands ~5-7 days after send
# (analyst guidance); electronic channels are same-day.
RECEIPT_LAG_DAYS = {'letter': 6}


def normalize_county(key: Optional[str]) -> Optional[str]:
    """Collapse the 'Franklin' / 'FranklinCounty' spelling drift."""
    if not key:
        return None
    return key[:-6] if key.endswith('County') else key


def zscore(series: pd.Series) -> Tuple[np.ndarray, Dict[str, float]]:
    """Standardize, returning values and the scaler params to persist."""
    mean, std = float(series.mean()), float(series.std())
    if std == 0 or np.isnan(std):
        raise ValueError(f"Cannot z-score '{series.name}': zero/NaN std")
    return ((series - mean) / std).to_numpy(), {'mean': mean, 'std': std}


def index_factor(series: pd.Series) -> Tuple[np.ndarray, Dict[str, int]]:
    """Map a categorical column to 0..K-1 integer indices."""
    levels = sorted(series.dropna().unique())
    mapping = {level: i for i, level in enumerate(levels)}
    return series.map(mapping).to_numpy(dtype=int), mapping


def _load_campaigns(db, require_weather: bool) -> pd.DataFrame:
    query = {'sent_at': {'$ne': None}}
    if require_weather:
        query['weather.status'] = 'ok'
    rows = []
    for c in db.campaigns.find(query, {
            'campaign_id': 1, 'channel': 1, 'sent_at': 1, 'agency': 1,
            'message_types': 1, 'weather': 1}):
        weather = c.get('weather') or {}
        temps = weather.get('temp_f') or {}
        degree_days = weather.get('degree_days') or {}
        extremes = weather.get('extremes') or {}
        row = {
            'campaign_id': c.get('campaign_id'),
            'channel': c.get('channel'),
            'agency': c.get('agency'),
            'sent_at': c.get('sent_at'),
            'weather_status': weather.get('status'),
            'temp_mean_f': temps.get('mean'),
            'hdd_base65': degree_days.get('hdd_base65'),
            'cdd_base65': degree_days.get('cdd_base65'),
            'freezing_hours': extremes.get('freezing_hours'),
            'hot_hours': extremes.get('hot_hours'),
            'county_recipient_share': weather.get('county_recipient_share'),
        }
        message_types = c.get('message_types') or []
        for mt in MESSAGE_TYPES:
            row[f'has_{mt}'] = int(mt in message_types)
        rows.append(row)
    df = pd.DataFrame(rows).dropna(subset=['campaign_id'])
    df['month'] = pd.to_datetime(df['sent_at']).dt.strftime('%Y-%m')
    return df


def _load_participants(db, require_thermal: bool) -> pd.DataFrame:
    query = {'demographics.estimated_income': {'$type': 'number'},
             'linkage.county_key': {'$exists': True}}
    if require_thermal:
        query['thermal.kwh_cl_slope'] = {'$type': 'number'}
    rows = []
    projection = {'participant_id': 1, 'linkage.county_key': 1,
                  'demographics.estimated_income': 1, 'demographics.household_size': 1,
                  'demographics.total_energy_burden': 1,
                  'thermal.kwh_cl_slope': 1, 'thermal.kwh_cl_r2': 1}
    projection.update({f'demographics.{f}': 1 for f in SPARSE_DEMOGRAPHICS})
    for p in db.participants.find(query, projection):
        demographics = p.get('demographics') or {}
        thermal = p.get('thermal') or {}
        row = {
            'participant_id': p.get('participant_id'),
            'county': normalize_county((p.get('linkage') or {}).get('county_key')),
            'estimated_income': demographics.get('estimated_income'),
            'household_size': demographics.get('household_size'),
            'total_energy_burden': demographics.get('total_energy_burden'),
            'kwh_cl_slope': thermal.get('kwh_cl_slope'),
            'kwh_cl_r2': thermal.get('kwh_cl_r2'),
        }
        row.update({f: demographics.get(f) for f in SPARSE_DEMOGRAPHICS})
        rows.append(row)
    df = pd.DataFrame(rows).dropna(subset=['participant_id', 'county'])
    return df.drop_duplicates(subset='participant_id')


def _load_exposures(db, channel: Optional[str], include_send_meta: bool = False) -> pd.DataFrame:
    query = {'channel': channel} if channel else {}
    projection = {'participant_id': 1, 'campaign_id': 1,
                  'email_engagement.opened': 1, 'email_engagement.clicked': 1,
                  'text_engagement.clicked': 1, 'text_engagement.replied': 1,
                  'text_engagement.opted_out': 1}
    if include_send_meta:
        projection.update({'sent_at': 1, 'channel': 1, 'agency': 1})
    rows = []
    for e in db.exposures.find(query, projection):
        email = e.get('email_engagement') or {}
        text = e.get('text_engagement') or {}
        row = {
            'participant_id': e.get('participant_id'),
            'campaign_id': e.get('campaign_id'),
            'opened': int(bool(email.get('opened'))),
            'email_clicked': int(bool(email.get('clicked'))),
            'text_clicked': int(bool(text.get('clicked'))),
            'replied': int(bool(text.get('replied'))),
            'opted_out': int(bool(text.get('opted_out'))),
        }
        if include_send_meta:
            row.update({'sent_at': e.get('sent_at'), 'channel': e.get('channel'),
                        'agency': e.get('agency')})
        rows.append(row)
    df = pd.DataFrame(rows).dropna(subset=['participant_id', 'campaign_id'])
    # Gate 1: dedupe (129k duplicate pairs in the raw collection). Keep max
    # engagement per pair so a duplicate that recorded the event survives.
    if not include_send_meta:
        return df.groupby(['participant_id', 'campaign_id'], as_index=False).max()
    agg = {c: 'max' for c in ['opened', 'email_clicked', 'text_clicked', 'replied', 'opted_out']}
    agg.update({'sent_at': 'min', 'channel': 'first', 'agency': 'first'})
    return df.groupby(['participant_id', 'campaign_id'], as_index=False).agg(agg)


def load_exposure_frame(channel: str = 'text', require_weather: bool = True,
                        require_thermal: bool = False,
                        required_covariates=PARTICIPANT_COVARIATES) -> pd.DataFrame:
    """Exposure-grain frame: deduped exposures ⋈ campaigns ⋈ participants.

    required_covariates: rows missing any of these are dropped. Callers on the
    2026 IMPACT cohort must NOT require total_energy_burden — it covers only
    ~8% of that cohort and silently guts the frame (found 2026-07-16).
    """
    from src.tools.mongo import get_campaign_db
    db = get_campaign_db()
    exposures = _load_exposures(db, channel)
    campaigns = _load_campaigns(db, require_weather)
    participants = _load_participants(db, require_thermal)
    df = exposures.merge(campaigns, on='campaign_id', how='inner')
    df = df.merge(participants, on='participant_id', how='inner')
    return df.dropna(subset=list(required_covariates))


def campaign_binomial_frame(outcome_by_channel: Dict[str, str] = None) -> pd.DataFrame:
    """Campaign-grain Binomial frame for F1: one row per campaign, k events of n sends.

    Default outcome per channel: email → opened, text → replied (gate 6).
    """
    from src.tools.mongo import get_campaign_db
    outcome_by_channel = outcome_by_channel or {'email': 'opened', 'text': 'replied'}
    db = get_campaign_db()
    frames = []
    for channel, outcome in outcome_by_channel.items():
        exposures = _load_exposures(db, channel)
        grouped = exposures.groupby('campaign_id').agg(
            n=('participant_id', 'size'), k=(outcome, 'sum')).reset_index()
        grouped['channel'] = channel
        grouped['outcome'] = outcome
        frames.append(grouped)
    result = pd.concat(frames, ignore_index=True)
    # Campaign send month, so callers can gate on tracking regime / season.
    months = _load_campaigns(db, require_weather=False)[['campaign_id', 'month']]
    return result.merge(months.drop_duplicates('campaign_id'), on='campaign_id', how='left')


def _load_applications(db) -> pd.DataFrame:
    """Earliest matched application per participant with its best-confidence campaign.

    One positive event per application: when ``likely_campaigns`` holds several
    candidates only the highest-confidence one becomes the attributed trigger;
    its confidence rides along for sensitivity variants.
    """
    rows = []
    for a in db.applications.find(
            {'participant_match.participant_id': {'$ne': None}, 'entry_date': {'$ne': None}},
            {'entry_date': 1, 'participant_match.participant_id': 1,
             'attribution.likely_campaigns': 1}):
        likely = (a.get('attribution') or {}).get('likely_campaigns') or []
        best = max(likely, key=lambda lc: lc.get('confidence', 0)) if likely else {}
        rows.append({'participant_id': a['participant_match']['participant_id'],
                     'entry_date': a['entry_date'],
                     'attributed_campaign_id': best.get('campaign_id'),
                     'attribution_confidence': best.get('confidence'),
                     'attribution_method': best.get('method')})
    df = pd.DataFrame(rows)
    return df.sort_values('entry_date').drop_duplicates('participant_id', keep='first')


def load_application_frame(require_weather: bool = False, last_week_days: int = 7) -> pd.DataFrame:
    """Exposure-grain frame for the application-conversion analysis (F6).

    One row per deduped (participant, campaign) send, with:
    outcome ``applied`` (this send is the best-confidence attributed trigger of
    the participant's earliest application), communication-sequence features,
    campaign message/weather features, and participant demographics.

    Design decisions (documented for the analyst):
    - ``sent_at`` falls back to the campaign send date when the exposure lacks
      one (117k of 129k null exposure dates are recoverable this way).
    - ``received_at`` = sent_at + RECEIPT_LAG_DAYS[channel] (letters +6 days).
    - Sequence features (n_prior, recency, first/last-in-wave) are computed on
      the FULL schedule, then post-application rows are censored — schedules
      did not react to conversions (224/250 converters kept receiving sends).
    - A wave is a participant's exposure run from one agency; ``last week``
      means received within ``last_week_days`` of that run's final send.
    - Participants whose application matched but could not be attributed to
      any campaign are dropped entirely (their event exists but no row may
      claim it, and calling all their rows 0 would mislabel the trigger).
    - Participants merge is LEFT: rows without demographics survive for the
      export; models drop/filter explicitly (selection is visible, not silent).
    """
    from src.tools.mongo import get_campaign_db
    db = get_campaign_db()
    exposures = _load_exposures(db, channel=None, include_send_meta=True)
    campaigns = _load_campaigns(db, require_weather).rename(
        columns={'sent_at': 'campaign_sent_at', 'channel': 'campaign_channel',
                 'agency': 'campaign_agency'})
    df = exposures.merge(campaigns, on='campaign_id', how='inner')
    df['channel'] = df['channel'].fillna(df['campaign_channel'])
    df['agency'] = df['agency'].fillna(df['campaign_agency'])
    df['sent_at'] = pd.to_datetime(df['sent_at']).fillna(pd.to_datetime(df['campaign_sent_at']))
    df = df.dropna(subset=['sent_at', 'channel']).drop(
        columns=['campaign_sent_at', 'campaign_channel', 'campaign_agency'])

    lag = df['channel'].map(RECEIPT_LAG_DAYS).fillna(0)
    df['received_at'] = df['sent_at'] + pd.to_timedelta(lag, unit='D')
    df['month'] = df['sent_at'].dt.strftime('%Y-%m')

    # Sequence features on the full (pre-censoring) schedule.
    df = df.sort_values(['participant_id', 'received_at'])
    df['n_prior_comms'] = df.groupby('participant_id').cumcount()
    df['days_since_prev'] = (df.groupby('participant_id')['received_at'].diff()
                             .dt.total_seconds() / 86400)
    df['is_first_comm'] = (df['n_prior_comms'] == 0).astype(int)
    wave = df.groupby(['participant_id', 'agency'])['received_at']
    df['is_first_in_wave'] = (df['received_at'] == wave.transform('min')).astype(int)
    df['is_last_in_wave'] = (df['received_at'] == wave.transform('max')).astype(int)
    df['in_last_week_of_wave'] = ((wave.transform('max') - df['received_at'])
                                  <= pd.Timedelta(days=last_week_days)).astype(int)

    apps = _load_applications(db)
    unattributable = set(apps.loc[apps['attributed_campaign_id'].isna(), 'participant_id'])
    df = df[~df['participant_id'].isin(unattributable)]
    df = df.merge(apps.dropna(subset=['attributed_campaign_id']),
                  on='participant_id', how='left')
    df['applied'] = ((df['campaign_id'] == df['attributed_campaign_id'])
                     .fillna(False).astype(int))
    # Censor: a send after the application cannot have caused it.
    df = df[df['entry_date'].isna() | (df['sent_at'] <= df['entry_date']) | (df['applied'] == 1)]
    # If a filter upstream (weather gate, unresolvable dates) removed the
    # attributed trigger row, the converter's other rows would mislabel as
    # pure negatives — drop such participants outright.
    converters = set(df.loc[df['entry_date'].notna(), 'participant_id'])
    with_event_row = set(df.loc[df['applied'] == 1, 'participant_id'])
    df = df[~df['participant_id'].isin(converters - with_event_row)]

    participants = _load_participants(db, require_thermal=False)
    return df.merge(participants, on='participant_id', how='left')


ITT_REQUIRED_COLUMNS = ['texted', 'approved', 'estimated_income',
                        'household_size', 'total_energy_burden', 'county']


def load_itt_frame(csv_path: str, column_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """F4 frame from the combined campaign-control export CSV.

    The outcome must come from the IMPACT approved-report roll-up, NOT Mongo
    `applications` (which is structurally blind to control-arm conversions).
    `column_map` renames CSV columns onto ITT_REQUIRED_COLUMNS.
    """
    df = pd.read_csv(csv_path)
    if column_map:
        df = df.rename(columns=column_map)
    missing = [c for c in ITT_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"ITT export missing columns {missing}; "
                         f"pass column_map to rename. Found: {list(df.columns)}")
    df['county'] = df['county'].map(normalize_county)
    df['texted'] = df['texted'].astype(int)
    df['approved'] = df['approved'].astype(int)
    return df.dropna(subset=ITT_REQUIRED_COLUMNS)


def covariate_balance(df: pd.DataFrame, arm_col: str = 'texted') -> pd.DataFrame:
    """Standardized mean differences between arms — F4's first deliverable.

    |SMD| < 0.1 is the conventional 'balanced' threshold.
    """
    rows = []
    treated, control = df[df[arm_col] == 1], df[df[arm_col] == 0]
    for col in PARTICIPANT_COVARIATES:
        mean_t, mean_c = treated[col].mean(), control[col].mean()
        pooled_sd = np.sqrt((treated[col].var() + control[col].var()) / 2)
        rows.append({'covariate': col, 'mean_treated': mean_t, 'mean_control': mean_c,
                     'smd': (mean_t - mean_c) / pooled_sd if pooled_sd > 0 else np.nan})
    county_share = pd.crosstab(df['county'], df[arm_col], normalize='columns')
    for county, row in county_share.iterrows():
        rows.append({'covariate': f'county={county}',
                     'mean_treated': row.get(1, 0.0), 'mean_control': row.get(0, 0.0),
                     'smd': np.nan})
    return pd.DataFrame(rows)
