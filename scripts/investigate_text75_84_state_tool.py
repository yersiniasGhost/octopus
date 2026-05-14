"""Stage 1 — Read-only investigation of DB state vs source xlsx for Text75–84.

Surveys each of the 10 EmpowerSaves_OH_Text{75..84} workbooks at
data/campaign-updated-20260512/ and reports, per file:

  - Source-of-truth from the Stats sheet (sent count, slug, action #, reply tag)
  - Candidate campaign docs in the live DB (by name regex, source_file, id prefix)
  - For each candidate: exposure count, unified_status distribution, sent_at range,
    duplicate (participant_id, campaign_id) pairs, orphan FKs (no matching
    participant row), legacy off-model `text_clicked` count
  - File-vs-DB phone delta (in file but not in DB exposures, and vice-versa)
  - Cross-contamination scan: count of click_<other_slug> tokens that this file's
    contacts carry (informs the Stage 4b coverage audit)

Pure reads. No writes anywhere. Emits a markdown report to .claude_docs/.

Usage:
    source venv/bin/activate
    python scripts/investigate_text75_84_state_tool.py
    python scripts/investigate_text75_84_state_tool.py --report-only   # skip console summary
"""

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# Reuse the canonical xlsx readers from the existing impact ingest tool.
sys.path.insert(0, str(Path(__file__).parent))
from ingest_impact_cold_20260310_campaign_tool import (  # noqa: E402
    aggregate_contacts,
    normalize_phone,
    read_conversations,
    read_stats_sheet,
)

DATA_DIR = Path('/home/yersinia/devel/octopus/data/campaign-updated-20260512')

# Per the brief (verified via Stats sheets in the prior session). The slug, action
# number, and reply tag are what we filter Tags by; the proposed_campaign_id is
# what we WOULD use if we end up creating a fresh doc (Stage 3 decision per file).
TEXT_FILE_CONFIG = [
    # filename                                                  text#  action  slug   reply_tag    proposed_campaign_id
    ('EmpowerSaves_OH_Text75_Winter_Section1.xlsx',                75,   76,  'lmss', 'replied76', 'text_impact_winter_75'),
    ('EmpowerSaves_OH_Text76_Winter_Section2.xlsx',                76,   77,  'lmss', 'replied77', 'text_impact_winter_76'),
    ('EmpowerSaves_OH_Text77_WCP_Section1.xlsx',                   77,   79,  'sMcs', 'replied79', 'text_impact_wcp_77'),
    ('EmpowerSaves_OH_Text78_WCP_Section2.xlsx',                   78,   78,  'lmLs', 'replied78', 'text_impact_wcp_78'),
    ('EmpowerSaves_OH_Text79_Cold_Section1.xlsx',                  79,   80,  'qXJi', 'replied80', 'text_impact_cold_79'),
    ('EmpowerSaves_OH_Text80_Cold_Section2.xlsx',                  80,   81,  'mWaR', 'replied81', 'text_impact_cold_80'),
    ('EmpowerSaves_OH_Text81_EndsSoon_Section1.xlsx',              81,   82,  'iXJM', 'replied82', 'text_impact_endssoon_81'),
    ('EmpowerSaves_OH_Text82_EndsSoon_Section2.xlsx',              82,   83,  'Ytxw', 'replied83', 'text_impact_endssoon_82'),
    ('EmpowerSaves_OH_Text83_LastDay_Section1.xlsx',               83,   84,  'pRJQ', 'replied84', 'text_impact_lastday_83'),
    ('EmpowerSaves_OH_Text84_LastDay_Section2.xlsx',               84,   85,  'pRJQ', 'replied85', 'text_impact_lastday_84'),
]

# All known slugs across the 10 files — for cross-contamination scanning.
ALL_SLUGS = {cfg[3] for cfg in TEXT_FILE_CONFIG}


def find_candidate_campaigns(db, text_num: int, proposed_id: str, filename: str) -> list[dict]:
    """Return campaign docs that *could* be the canonical record for this file."""
    or_clauses = [
        {'campaign_id': proposed_id},
        {'name': {'$regex': f'Text{text_num}\\b', '$options': 'i'}},
        {'name_variants': {'$regex': f'Text{text_num}\\b', '$options': 'i'}},
        {'source_file': filename},
        # Loose: any campaign_id that ends with _<N>
        {'campaign_id': {'$regex': f'_{text_num}$'}},
    ]
    return list(db.campaigns.find(
        {'$or': or_clauses},
        {'campaign_id': 1, 'name': 1, 'channel': 1, 'sent_at': 1,
         'source_file': 1, 'campaign_group': 1, 'platform_stats': 1},
    ))


def survey_exposures(db, campaign_id: str) -> dict:
    """Read-only profile of exposures for a campaign."""
    pipeline = [
        {'$match': {'campaign_id': campaign_id}},
        {'$group': {
            '_id': '$unified_status',
            'n': {'$sum': 1},
            'min_sent': {'$min': '$sent_at'},
            'max_sent': {'$max': '$sent_at'},
        }},
    ]
    status_dist = {}
    overall_min, overall_max = None, None
    total = 0
    for r in db.exposures.aggregate(pipeline):
        status_dist[r['_id']] = r['n']
        total += r['n']
        if r['min_sent'] and (overall_min is None or r['min_sent'] < overall_min):
            overall_min = r['min_sent']
        if r['max_sent'] and (overall_max is None or r['max_sent'] > overall_max):
            overall_max = r['max_sent']

    # Duplicate (participant_id, campaign_id) detection
    dup_count = 0
    dup_examples = []
    for r in db.exposures.aggregate([
        {'$match': {'campaign_id': campaign_id}},
        {'$group': {'_id': '$participant_id', 'n': {'$sum': 1}}},
        {'$match': {'n': {'$gt': 1}}},
        {'$limit': 5000},
    ]):
        dup_count += 1
        if len(dup_examples) < 3:
            dup_examples.append(f"{r['_id']} ({r['n']}x)")

    # Off-model legacy click count
    legacy_clicked = db.exposures.count_documents({
        'campaign_id': campaign_id,
        'text_clicked': True,
    })

    # Orphan FK detection: exposures whose participant_id doesn't resolve to a participants row
    orphan_count = 0
    orphan_examples = []
    for r in db.exposures.aggregate([
        {'$match': {'campaign_id': campaign_id}},
        {'$lookup': {
            'from': 'participants',
            'localField': 'participant_id',
            'foreignField': 'participant_id',
            'as': '_p',
        }},
        {'$match': {'_p': {'$size': 0}}},
        {'$project': {'participant_id': 1}},
        {'$limit': 100},
    ]):
        orphan_count += 1
        if len(orphan_examples) < 3:
            orphan_examples.append(r['participant_id'])

    # participant_oid coverage
    oid_present = db.exposures.count_documents({
        'campaign_id': campaign_id,
        'participant_oid': {'$exists': True, '$ne': None},
    })

    return {
        'total': total,
        'status_dist': status_dist,
        'sent_at_min': overall_min,
        'sent_at_max': overall_max,
        'dup_count': dup_count,
        'dup_examples': dup_examples,
        'legacy_clicked': legacy_clicked,
        'orphan_count': orphan_count,
        'orphan_examples': orphan_examples,
        'oid_present': oid_present,
    }


def db_phones_for_campaign(db, campaign_id: str) -> set[str]:
    """Set of normalized phones present as participant_id in this campaign's exposures."""
    phones = set()
    for e in db.exposures.find({'campaign_id': campaign_id}, {'participant_id': 1}):
        p = normalize_phone(e.get('participant_id'))
        if p:
            phones.add(p)
    return phones


def file_phones_and_tags(filepath: Path) -> tuple[dict, dict]:
    """Returns (contacts_dict, slug_token_counts) from one xlsx.

    contacts_dict: phone → {all_tags, has_outbound, status}
    slug_token_counts: Counter of click_<slug> tokens observed across all UNIQUE
        contacts (de-dup'd by phone — a tag attached to a contact who appears
        on 3 rows counts once, not three times).

    NOTE: the inherited aggregate_contacts() reads only 'Msg Tags' and
    'Contact Tags'. The xlsx files for Text75-84 also have a third column
    literally named 'Tags' (contact-aggregated by the vendor) that contains
    the click_<slug> and replied<N> tokens. This function unions all three
    columns into contact['all_tags'] before slug-counting.
    """
    rows = read_conversations(filepath)
    contacts = aggregate_contacts(rows)  # reads Msg Tags + Contact Tags

    # Union the missing 'Tags' column into each contact's all_tags
    for row in rows:
        phone = normalize_phone(row.get('Phone Number'))
        if not phone or phone not in contacts:
            continue
        for tag in (row.get('Tags') or '').split(','):
            tag = tag.strip()
            if tag:
                contacts[phone]['all_tags'].add(tag)
        # Tester re-check now that we have the full tag set
        if 'tester' in contacts[phone]['all_tags'] or 'test_phone' in contacts[phone]['all_tags']:
            contacts[phone]['is_tester'] = True

    slug_token_counts = Counter()
    for c in contacts.values():
        if c.get('is_tester'):
            continue  # don't count tester clicks
        for tag in c['all_tags']:
            if tag.startswith('click_'):
                slug_token_counts[tag] += 1
    return contacts, slug_token_counts


def newly_created_estimate(db, campaign_id: str) -> int:
    """Heuristic: participants whose source_campaigns has only this one campaign."""
    return db.participants.count_documents({
        'source_campaigns': [campaign_id],
    })


def dual_keyed_phones(db, campaign_id: str) -> list[str]:
    """Phones that appear both as their own participant_id AND as .phone on
    an email-keyed participant. Indicates duplicate participant rows."""
    phones_as_pid = set()
    for p in db.participants.find(
        {'source_campaigns': campaign_id, 'participant_id': {'$regex': r'^\d{10}$'}},
        {'participant_id': 1},
    ):
        phones_as_pid.add(p['participant_id'])
    if not phones_as_pid:
        return []
    dual = []
    for p in db.participants.find(
        {'phone': {'$in': list(phones_as_pid)}, 'email': {'$nin': [None, '']}},
        {'phone': 1, 'email': 1},
    ):
        dual.append(f"{p['phone']} (also email-keyed @ {p.get('email')})")
        if len(dual) >= 5:
            break
    return dual


def fmt_dt(dt) -> str:
    if dt is None:
        return 'None'
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M')
    return str(dt)


def render_file_report(filename: str, text_num: int, action: int, slug: str,
                       reply_tag: str, proposed_id: str,
                       stats: dict, contacts: dict, slug_tokens: Counter,
                       candidates: list[dict], surveys: dict[str, dict],
                       phone_diffs: dict[str, dict]) -> str:
    """Render the per-file markdown section."""
    lines = []
    lines.append(f'## {filename}\n')

    # Expected (from Stats sheet + brief)
    expected_sent = stats.get('sent')
    expected_delivered = stats.get('delivered')
    sent_time = stats.get('sent_time')
    lines.append(f'**Source-of-truth (Stats sheet):**')
    lines.append(f'- Text #: `{text_num}`  Action: `{action}`  Slug: `{slug}`  Reply tag: `{reply_tag}`')
    lines.append(f'- sent_time: `{sent_time}`')
    lines.append(f'- target=`{stats.get("target")}` sent=`{expected_sent}` '
                 f'delivered=`{expected_delivered}` dnd=`{stats.get("dnd")}` '
                 f'bad=`{stats.get("bad")}` err=`{stats.get("err")}` '
                 f'replies=`{stats.get("replies")}`')
    lines.append(f'- Proposed campaign_id (if creating fresh): `{proposed_id}`')
    lines.append('')

    # File-side click distribution
    self_slug_tag = f'click_{slug}'
    own_clicks = slug_tokens.get(self_slug_tag, 0)
    other_clicks = {k: v for k, v in slug_tokens.items() if k != self_slug_tag}
    lines.append(f'**File-side click tokens:**')
    lines.append(f'- `{self_slug_tag}` (this campaign): {own_clicks}')
    if other_clicks:
        lines.append(f'- Cross-contamination (other-campaign clicks present in this file\'s Tags):')
        for tag, n in sorted(other_clicks.items(), key=lambda kv: -kv[1]):
            # Identify owning campaign(s) of this slug
            tag_slug = tag.replace('click_', '')
            owners = [c[5] for c in TEXT_FILE_CONFIG if c[3] == tag_slug]
            owner_str = ', '.join(owners) if owners else '(slug not in our 10-file set)'
            lines.append(f'  - `{tag}`: {n}  → owned by {owner_str}')
    else:
        lines.append(f'- No cross-contamination detected.')
    lines.append('')
    lines.append(f'**File-side contacts:** {len(contacts)} unique phones from Conversations sheet')
    lines.append('')

    # Candidate campaign docs
    lines.append(f'**Candidate campaign docs in DB:** {len(candidates)}')
    if not candidates:
        lines.append('- _none — this campaign is not yet in `db.campaigns`_')
    for c in candidates:
        lines.append(f'')
        lines.append(f'- **`{c["campaign_id"]}`** — name=`{c.get("name")}` '
                     f'channel=`{c.get("channel")}` sent_at=`{fmt_dt(c.get("sent_at"))}` '
                     f'source_file=`{c.get("source_file")}` group=`{c.get("campaign_group")}`')
        s = surveys.get(c['campaign_id'], {})
        if not s or s.get('total', 0) == 0:
            lines.append(f'  - exposures: **0**')
            continue
        status_str = ', '.join(f'{k}={v}' for k, v in sorted(s['status_dist'].items(), key=lambda kv: -kv[1]))
        lines.append(f'  - exposures: **{s["total"]}** ({status_str})')
        lines.append(f'  - sent_at range: `{fmt_dt(s["sent_at_min"])}` .. `{fmt_dt(s["sent_at_max"])}`')
        if expected_sent:
            try:
                delta = s['total'] - int(expected_sent)
                lines.append(f'  - delta vs file sent count: `{delta:+d}` ({s["total"]}/{expected_sent} = {100*s["total"]/int(expected_sent):.1f}%)')
            except (ValueError, TypeError):
                pass
        lines.append(f'  - participant_oid populated: {s["oid_present"]}/{s["total"]} ({100*s["oid_present"]/s["total"]:.0f}%)')
        if s['dup_count']:
            lines.append(f'  - ⚠ duplicate (participant_id, campaign_id) pairs: **{s["dup_count"]}** (e.g. {s["dup_examples"]})')
        if s['orphan_count']:
            lines.append(f'  - ⚠ orphan exposures (no matching participant): **{s["orphan_count"]}** (e.g. {s["orphan_examples"]})')
        if s['legacy_clicked']:
            lines.append(f'  - legacy off-model `text_clicked: true` count: {s["legacy_clicked"]}')

        # Newly-created-by-this-campaign estimate
        new_count = newly_created_estimate(db_global, c['campaign_id'])
        lines.append(f'  - participants with `source_campaigns == [this campaign only]`: {new_count}')

        # Dual-keyed
        dual = dual_keyed_phones(db_global, c['campaign_id'])
        if dual:
            lines.append(f'  - ⚠ dual-keyed participants (phone-keyed + email-keyed copies): {len(dual)} (e.g. {dual[:3]})')

        # Phone diff
        pd = phone_diffs.get(c['campaign_id'], {})
        if pd:
            lines.append(f'  - phones in file but not in this campaign\'s exposures: {pd["only_in_file"]}')
            lines.append(f'  - phones in this campaign\'s exposures but not in file: {pd["only_in_db"]}')

    lines.append('')
    return '\n'.join(lines)


def main():
    global db_global  # used by the renderer for ancillary lookups

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-path', type=Path, default=None,
                        help='Override output path (default: .claude_docs/<ts>_text75_84_state_investigation.md)')
    args = parser.parse_args()

    load_dotenv()
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client[os.getenv('MONGODB_CAMPAIGN', 'empower_development')]
    db_global = db  # for the renderer

    ts = datetime.now().strftime('%Y%m%d_%H%M')
    report_path = args.report_path or Path(__file__).parent.parent / '.claude_docs' / f'{ts}_text75_84_state_investigation.md'

    sections = []
    sections.append(f'# Stage 1 — Text75–84 State Investigation\n')
    sections.append(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    sections.append(f'**Source:** `{DATA_DIR}/`')
    sections.append(f'**DB:** `empower_development`')
    sections.append(f'**Mode:** read-only — no writes performed.\n')

    # Per-file pass
    grand_summary = []

    for filename, text_num, action, slug, reply_tag, proposed_id in TEXT_FILE_CONFIG:
        filepath = DATA_DIR / filename
        print(f'[scan] {filename} ... ', end='', flush=True)
        if not filepath.exists():
            sections.append(f'## {filename}\n\n⚠ FILE MISSING at {filepath}\n')
            print('MISSING')
            continue

        stats = read_stats_sheet(filepath)
        contacts, slug_tokens = file_phones_and_tags(filepath)

        candidates = find_candidate_campaigns(db, text_num, proposed_id, filename)
        surveys = {}
        phone_diffs = {}
        for c in candidates:
            surveys[c['campaign_id']] = survey_exposures(db, c['campaign_id'])
            db_phones = db_phones_for_campaign(db, c['campaign_id'])
            file_phones = set(contacts.keys())
            phone_diffs[c['campaign_id']] = {
                'only_in_file': len(file_phones - db_phones),
                'only_in_db':   len(db_phones - file_phones),
                'overlap':      len(file_phones & db_phones),
            }

        sections.append(render_file_report(
            filename, text_num, action, slug, reply_tag, proposed_id,
            stats, contacts, slug_tokens, candidates, surveys, phone_diffs,
        ))
        grand_summary.append({
            'filename': filename,
            'file_contacts': len(contacts),
            'candidates': len(candidates),
            'campaign_ids': [c['campaign_id'] for c in candidates],
            'best_match_exposures': max((surveys[c['campaign_id']]['total'] for c in candidates), default=0),
        })
        print(f'contacts={len(contacts)} candidates={len(candidates)}')

    # Top-of-file summary table (rebuild & prepend)
    summary_md = ['\n## Per-file summary table\n']
    summary_md.append('| File | File contacts | DB candidates | Existing campaign_ids | Best-match exposures |')
    summary_md.append('|---|---:|---:|---|---:|')
    for s in grand_summary:
        ids = ', '.join(f'`{c}`' for c in s['campaign_ids']) or '_(none)_'
        summary_md.append(f'| {s["filename"]} | {s["file_contacts"]} | {s["candidates"]} | {ids} | {s["best_match_exposures"]} |')
    summary_md.append('')

    # Insert summary table after the header
    sections.insert(1, '\n'.join(summary_md))

    # Append open-question section
    sections.append('\n## Per-file decisions required\n')
    sections.append('For each file, please respond with one of:')
    sections.append('- **keep** — existing campaign + exposures look correct; only add clicks in Stage 4')
    sections.append('- **augment** — keep campaign doc; update specific exposure fields (specify which)')
    sections.append('- **wipe-and-reingest** — delete all exposures for this campaign_id, re-create from xlsx')
    sections.append('- **create-fresh** — no existing doc; create new from xlsx')
    sections.append('')
    sections.append('Also flag any duplicate-participant cleanups you want done in Stage 2.\n')

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('\n'.join(sections))
    print(f'\n✅ Report written to {report_path}')
    print(f'   Size: {report_path.stat().st_size} bytes, {report_path.read_text().count(chr(10))} lines')

    client.close()


if __name__ == '__main__':
    main()
