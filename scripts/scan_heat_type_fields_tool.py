#!/usr/bin/env python3
"""Read-only scan of {County}CountyResidential collections for heat/fuel/hvac/furnace fields.

Samples documents with $sample, unions top-level keys, and for each matching field prints the top distinct values.
Fields that look like free text (long or high-cardinality strings) print only a distinct count. Writes nothing.

    python scripts/scan_heat_type_fields_tool.py [--sample 2000] [--top 15]
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine.sources import collection_name
from src.tools.mongo import get_empower_db

PATTERN = re.compile(r'heat|fuel|hvac|furnace', re.I)
MAX_CATEGORICAL_DISTINCT, MAX_CATEGORICAL_LEN = 60, 40


def residential_collections(db) -> list:
    suffix = collection_name('residential', '')
    return sorted(n for n in db.list_collection_names() if n.endswith(suffix))


def describe(counter: Counter, top: int) -> str:
    """Counts line for a field; suppress values that look like free text (possible PII)."""
    strings = [v for v in counter if isinstance(v, str)]
    if len(counter) > MAX_CATEGORICAL_DISTINCT or any(len(v) > MAX_CATEGORICAL_LEN for v in strings):
        return f'<free text, {len(counter)} distinct>'
    return ', '.join(f'{v!r}={n}' for v, n in counter.most_common(top))


def scan(db, name: str, sample: int, top: int) -> dict:
    docs = list(db[name].aggregate([{'$sample': {'size': sample}}]))
    fields = sorted({k for d in docs for k in d if PATTERN.search(k)})
    return {f: describe(Counter(repr_safe(d.get(f)) for d in docs), top) for f in fields}, len(docs)


def repr_safe(v):
    if isinstance(v, float) and v != v:
        return None  # NaN objects are never equal; fold them into one missing bucket
    return v if isinstance(v, (str, int, float, bool, type(None))) else f'<{type(v).__name__}>'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--sample', type=int, default=2000)
    ap.add_argument('--top', type=int, default=15)
    args = ap.parse_args()
    db = get_empower_db()
    for name in residential_collections(db):
        result, n = scan(db, name, args.sample, args.top)
        print(f'== {name} (sampled {n}) ==')
        for field, values in result.items():
            print(f'  {field}: {values}')
        if not result:
            print('  (no matching fields)')


if __name__ == '__main__':
    main()
