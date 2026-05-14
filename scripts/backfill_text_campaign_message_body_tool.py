#!/usr/bin/env python3
"""
backfill_text_campaign_message_body_tool.py

Populate `campaigns.message_body` with the actual SMS template per text campaign.

Two sources, in priority order:

  1. PRIMARY (RumbleUp sends): data/campaign_texting/Empower_Saves_Texts_All.csv
     Each row is one rendered SMS send (column `msg`). The stats CSV
     identifies campaigns by `action` (1..74) -> `Full name`; the contacts
     CSV tags each send with `Contacted in Project` (= action). We join on
     that integer, group rendered bodies per campaign, normalize
     per-recipient tokens (street, first name, dollar amounts), and pick the
     modal form. This covers Text1-Text74.

  2. FALLBACK (campaign brief templates): data/campaign_texting/text_content.txt
     A hand-curated catalog of slot label -> template. We parse it into a dict
     keyed by normalized slot phrase (e.g. "lastday" -> "Final Day" template),
     then apply it to campaigns whose name carries one of the IMPACT slot
     tokens (Winter/WCP/Cold/EndsSoon/LastDay) so the Text75-84 detail pages
     show *something* meaningful.

Defaults to dry-run; pass --apply to write to MongoDB.
"""

import argparse
import csv
import html
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

STATS_CSV = ROOT / "data/campaign_texting/Empower_Saves_Texts_All_stats.csv"
CONTACTS_CSV = ROOT / "data/campaign_texting/Empower_Saves_Texts_All.csv"
CONTENT_TXT = ROOT / "data/campaign_texting/text_content.txt"

# Existing placeholder values written by the original ingest, of the form
# "Prequalified message campaign", "GetHelp message campaign", etc.
PLACEHOLDER_RE = re.compile(r"^[A-Za-z0-9_ ]+ message campaign$", re.IGNORECASE)

# Per-recipient dollar amounts in rendered SMS bodies (e.g. "$98.98", "$1,187")
DOLLAR_RE = re.compile(r"\$\d[\d,]*(?:\.\d{1,2})?")

# IMPACT slot keywords (used by Text75-84) -> normalized key into text_content.txt
IMPACT_SLOT_TO_CONTENT_KEY = {
    "lastday": "final day",
    "endssoon": "time running out",
    "wcp": "summer crisis program",
    "cold": "stay cool",          # closest brief in the catalog
    "winter": "stay cool",        # closest brief in the catalog
}


def get_db():
    uri = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or "mongodb://{h}:{p}".format(
            h=os.getenv("MONGODB_HOST", "localhost"),
            p=os.getenv("MONGODB_PORT", "27017"),
        )
    )
    return MongoClient(uri)[os.getenv("MONGODB_CAMPAIGN", "empower_development")]


# ---------- primary source: rumbleup CSV ----------

def load_action_to_name() -> dict[str, str]:
    """stats CSV: action sequence number -> campaign Full name."""
    out = {}
    with STATS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            action = (row.get("action") or "").strip()
            name = (row.get("Full name") or "").strip()
            if action and name:
                out[action] = name
    return out


def _strip_recipient_tokens(msg: str, street: str, first: str) -> str:
    """Replace per-send tokens with template placeholders."""
    s = (msg or "").strip()
    if not s:
        return s
    if street:
        st = street.strip()
        if st:
            s = re.sub(re.escape(st), "{ADDRESS}", s, flags=re.IGNORECASE)
    if first:
        f = first.strip()
        if len(f) >= 2:
            s = re.sub(r"\b" + re.escape(f) + r"\b", "{FIRSTNAME}", s, flags=re.IGNORECASE)
    s = DOLLAR_RE.sub("${AMOUNT}", s)
    return re.sub(r"\s+", " ", s).strip()


def load_action_to_message() -> dict[str, tuple[str, int, int]]:
    """contacts CSV: action (Contacted in Project) -> (canonical_message, modal_count, total_rows)."""
    bucket: dict[str, Counter] = defaultdict(Counter)
    with CONTACTS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            action = (row.get("Contacted in Project") or "").strip()
            msg = (row.get("msg") or "").strip()
            if not (action and msg):
                continue
            templated = _strip_recipient_tokens(msg, row.get("Street", ""), row.get("First Name", ""))
            if templated:
                bucket[action][templated] += 1
    out = {}
    for action, counter in bucket.items():
        body, count = counter.most_common(1)[0]
        out[action] = (body, count, sum(counter.values()))
    return out


# ---------- fallback source: text_content.txt ----------

def load_content_templates() -> dict[str, str]:
    """Parse text_content.txt into a {normalized_slot_phrase: template} dict.

    Entries start with "o <Label> - <body...>" and continue until the next
    "o " marker (the file uses soft wraps inside an entry).
    """
    raw = CONTENT_TXT.read_text(encoding="utf-8")
    # Decode the HTML entities used in the source ("&#39;" -> "'", "&lt;" -> "<")
    raw = html.unescape(raw)
    entries: dict[str, str] = {}
    current_label: str | None = None
    current_body: list[str] = []
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("o "):
            if current_label is not None:
                entries[current_label] = " ".join(current_body).strip()
            head = line[2:].strip()
            if " - " in head:
                label, first_chunk = head.split(" - ", 1)
            else:
                label, first_chunk = head, ""
            current_label = label.strip().lower()
            current_body = [first_chunk.strip()] if first_chunk else []
        elif current_label is not None and line.strip():
            current_body.append(line.strip())
    if current_label is not None:
        entries[current_label] = " ".join(current_body).strip()
    # Collapse whitespace + drop trailing schedule fragments left over in label
    cleaned = {}
    for label, body in entries.items():
        key = re.sub(r"\s*\([^)]*\)\s*", "", label).strip()  # drop "(8am-10am)" etc.
        body = re.sub(r"\s+", " ", body).strip()
        # First label wins; do not overwrite with later schedule variants.
        cleaned.setdefault(key, body)
    return cleaned


def message_for_impact_slot(name: str, content_templates: dict[str, str]) -> str | None:
    """Return a template body for a Text75-84 campaign name, or None."""
    lower = (name or "").lower()
    for slot, content_key in IMPACT_SLOT_TO_CONTENT_KEY.items():
        if slot in lower:
            tmpl = content_templates.get(content_key)
            if tmpl:
                return tmpl
    return None


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Write to MongoDB (default: dry-run)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite any existing message_body, not just placeholders / nulls")
    ap.add_argument("--verbose", action="store_true", help="Print every campaign + chosen body")
    args = ap.parse_args()

    action_name = load_action_to_name()
    print(f"stats CSV       : {len(action_name):>4} action -> name rows")
    action_msg = load_action_to_message()
    print(f"contacts CSV    : {len(action_msg):>4} actions with rendered messages")
    name_msg = {action_name[a]: action_msg[a] for a in action_msg if a in action_name}
    print(f"join            : {len(name_msg):>4} campaign-name -> message entries")
    content_templates = load_content_templates()
    print(f"text_content.txt: {len(content_templates):>4} slot templates parsed")
    print()

    db = get_db()
    # Some IMPACT-drop campaigns have channel='text' but campaign_type=None.
    campaigns = list(db.campaigns.find({"$or": [{"campaign_type": "text"}, {"channel": "text"}]}))
    print(f"DB              : {len(campaigns):>4} text campaigns")
    print()

    stats = Counter()
    samples_primary: list[tuple[str, str, str]] = []
    samples_fallback: list[tuple[str, str]] = []
    samples_skipped: list[tuple[str, str]] = []

    for c in campaigns:
        name = c.get("name") or ""
        current = (c.get("message_body") or "").strip()
        is_placeholder = bool(PLACEHOLDER_RE.match(current)) if current else False
        is_overwritable = (not current) or is_placeholder or args.force

        new_body: str | None = None
        source: str | None = None

        if name in name_msg:
            new_body = name_msg[name][0]
            source = "rumbleup"
        else:
            t = message_for_impact_slot(name, content_templates)
            if t:
                new_body = t
                source = "content_txt"

        if not new_body:
            stats["no_source"] += 1
            if len(samples_skipped) < 8:
                samples_skipped.append((name, current))
            continue
        stats[f"matched_{source}"] += 1
        if not is_overwritable:
            stats["skipped_has_content"] += 1
            continue
        if new_body == current:
            stats["already_correct"] += 1
            continue

        stats[f"updated_{source}"] += 1
        if source == "rumbleup" and len(samples_primary) < 4:
            samples_primary.append((name, current or "(empty)", new_body))
        if source == "content_txt" and len(samples_fallback) < 4:
            samples_fallback.append((name, new_body))

        if args.apply:
            db.campaigns.update_one({"_id": c["_id"]}, {"$set": {"message_body": new_body}})
        if args.verbose:
            print(f"[{source:11s}] {name}")
            print(f"  -> {new_body[:160]}")

    print("Summary")
    print("-------")
    for k in sorted(stats):
        print(f"  {k:24s} : {stats[k]}")
    print()

    if samples_primary:
        print("Sample primary (rumbleup CSV):")
        for n, old, new in samples_primary:
            print(f"  - {n}")
            print(f"      old: {old[:100]}")
            print(f"      new: {new[:160]}")
        print()
    if samples_fallback:
        print("Sample fallback (text_content.txt):")
        for n, new in samples_fallback:
            print(f"  - {n}")
            print(f"      -> {new[:160]}")
        print()
    if samples_skipped:
        print("Sample skipped (no source matched):")
        for n, old in samples_skipped:
            print(f"  - {n}  (current message_body: {old[:80] or '(empty)'})")
        print()

    if not args.apply:
        print("Dry-run only. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
