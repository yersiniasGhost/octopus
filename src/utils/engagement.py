"""Compute participant engagement rollups on demand from the `exposures` collection.

Replaces the denormalized `participants.engagement_summary` field. Same shape as
the legacy field, computed via a single server-side aggregation, so the only
change required at call sites is a one-line `attach_engagement_summaries(db, docs)`
after a participants `.find()`.

Status hierarchy used to derive the per-participant `unified_status`:
    engaged > clicked > received > opted_out > undeliverable > no_engagement
This matches the precedence the legacy ingest scripts implemented.
"""
from __future__ import annotations

from typing import Iterable, Optional

# Highest-priority status wins when a participant has exposures across multiple
# states. Order is most-engaged → least-engaged.
STATUS_PRIORITY = [
    "converted",         # legacy status, kept for completeness
    "engaged",
    "clicked",
    "negative_response", # legacy status, kept for completeness
    "received",
    "opted_out",
    "undeliverable",
    "no_engagement",
]
_STATUS_RANK = {s: i for i, s in enumerate(STATUS_PRIORITY)}

# An exposure counts as "received" if it reached the recipient at all — any
# status downstream of plain delivery qualifies.
RECEIVED_STATUSES = {"received", "clicked", "engaged", "converted"}

# Channel keys the rollup tracks (matches the legacy EngagementSummary schema).
CHANNEL_KEYS = ("email", "text", "text_morning", "text_evening", "mailer", "letter")


def _empty_channel() -> dict:
    return {"exposures": 0, "received": 0, "engaged": 0}


def _empty_summary() -> dict:
    return {
        "total_campaigns": 0,
        "total_exposures": 0,
        "by_channel": {ch: _empty_channel() for ch in CHANNEL_KEYS},
        "unified_status": "no_engagement",
        "ever_received": False,
        "ever_engaged": False,
        "first_campaign_date": None,
        "last_campaign_date": None,
        "overall_receive_rate": 0.0,
        "overall_engage_rate": 0.0,
    }


def _build_pipeline(participant_ids: Optional[Iterable[str]]) -> list:
    """Aggregation pipeline that produces one document per participant_id with
    all the counts the rollup needs. Counts are computed via $cond inside $sum
    so the entire reduction happens server-side in a single pass over the
    `exposures` collection (or just the participant subset, if filtered)."""

    match_stage: dict = {}
    if participant_ids is not None:
        ids = list(participant_ids)
        if not ids:
            return []  # empty input → empty output
        match_stage = {"$match": {"participant_id": {"$in": ids}}}

    def channel_sum(channel: str, condition: dict) -> dict:
        """Sum where channel matches AND `condition` is true."""
        return {
            "$sum": {
                "$cond": [
                    {"$and": [{"$eq": ["$channel", channel]}, condition]},
                    1,
                    0,
                ]
            }
        }

    is_received = {"$in": ["$unified_status", list(RECEIVED_STATUSES)]}
    is_engaged = {"$eq": ["$unified_status", "engaged"]}

    group_fields = {
        "_id": "$participant_id",
        "total_exposures": {"$sum": 1},
        "campaigns": {"$addToSet": "$campaign_id"},
        "first_sent": {"$min": "$sent_at"},
        "last_sent": {"$max": "$sent_at"},
        "statuses": {"$addToSet": "$unified_status"},
    }
    for ch in CHANNEL_KEYS:
        group_fields[f"{ch}_exposures"] = channel_sum(ch, {"$ne": ["$channel", None]})  # placeholder; replaced below
        # exposures-per-channel is just "channel matches"
        group_fields[f"{ch}_exposures"] = {"$sum": {"$cond": [{"$eq": ["$channel", ch]}, 1, 0]}}
        group_fields[f"{ch}_received"] = channel_sum(ch, is_received)
        group_fields[f"{ch}_engaged"] = channel_sum(ch, is_engaged)

    pipeline = []
    if match_stage:
        pipeline.append(match_stage)
    pipeline.append({"$group": group_fields})
    return pipeline


def _best_status(statuses: Iterable[str]) -> str:
    """Pick the highest-priority status from a set, defaulting to no_engagement."""
    best_rank = len(STATUS_PRIORITY)
    best = "no_engagement"
    for s in statuses:
        rank = _STATUS_RANK.get(s, len(STATUS_PRIORITY))
        if rank < best_rank:
            best_rank, best = rank, s
    return best


def _shape_summary(agg_row: dict) -> dict:
    """Convert an aggregation result row into the legacy engagement_summary shape."""
    summary = _empty_summary()
    summary["total_exposures"] = agg_row.get("total_exposures", 0)
    summary["total_campaigns"] = len(agg_row.get("campaigns") or [])
    summary["first_campaign_date"] = agg_row.get("first_sent")
    summary["last_campaign_date"] = agg_row.get("last_sent")

    total_received = 0
    total_engaged = 0
    for ch in CHANNEL_KEYS:
        ex = agg_row.get(f"{ch}_exposures", 0)
        rec = agg_row.get(f"{ch}_received", 0)
        eng = agg_row.get(f"{ch}_engaged", 0)
        summary["by_channel"][ch] = {"exposures": ex, "received": rec, "engaged": eng}
        total_received += rec
        total_engaged += eng

    summary["ever_received"] = total_received > 0
    summary["ever_engaged"] = total_engaged > 0
    summary["unified_status"] = _best_status(agg_row.get("statuses") or [])

    total = summary["total_exposures"] or 0
    summary["overall_receive_rate"] = (total_received / total) if total else 0.0
    summary["overall_engage_rate"] = (total_engaged / total) if total else 0.0
    return summary


def build_engagement_summaries(db, participant_ids: Optional[Iterable[str]] = None) -> dict[str, dict]:
    """Compute engagement summaries for the given participants (or all participants
    with at least one exposure if `participant_ids` is None).

    Returns a dict keyed by participant_id. Participants with no exposures are
    not in the dict — callers should default to an empty summary.
    """
    pipeline = _build_pipeline(participant_ids)
    if not pipeline:
        return {}
    out: dict[str, dict] = {}
    for row in db.exposures.aggregate(pipeline, allowDiskUse=True):
        pid = row.get("_id")
        if pid is None:
            continue
        out[pid] = _shape_summary(row)
    return out


def get_engagement_summary(db, participant_id: str) -> dict:
    """Single-participant version. Always returns a full summary dict —
    participants with no exposures get the zero-valued default."""
    summaries = build_engagement_summaries(db, [participant_id])
    return summaries.get(participant_id) or _empty_summary()


def attach_engagement_summaries(db, participants: list[dict]) -> None:
    """In-place: add `engagement_summary` to each dict in `participants`.

    Drop-in replacement for the denormalized field on freshly-loaded participant
    docs. Participants without exposures get a zero-valued summary (matching the
    legacy default-factory behavior).
    """
    if not participants:
        return
    ids = [p.get("participant_id") for p in participants if p.get("participant_id")]
    summaries = build_engagement_summaries(db, ids)
    for p in participants:
        pid = p.get("participant_id")
        p["engagement_summary"] = summaries.get(pid) if pid else None
        if p["engagement_summary"] is None:
            p["engagement_summary"] = _empty_summary()
