#!/usr/bin/env python3
"""
Read-only fingerprint of a MongoDB collection, for proving a rollback rolled back.

A restore that returns the right document count can still have dropped an index
(mongorestore --drop destroys indexes and rebuilds them from dump metadata) or
returned different documents. Comparing document counts alone scores both of
those as a pass. This captures count + indexes + a content hash so the claim
"the collection is byte-for-byte what it was" is actually checkable.

This tool never writes to MongoDB. There is no --execute flag because there is
nothing to execute; the only file it writes is the JSON capture you ask for.

It streams and hashes every document, so it is meant for targeted rollback
proofs. Expect a few seconds on a 260k-document collection.

Usage:
    # Capture before a destructive operation
    python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads \
        --out exports/morrow_before.json

    # Capture again afterwards and diff
    python src/scripts/collection_fingerprint_tool.py capture MorrowThermalLoads \
        --out exports/morrow_after.json
    python src/scripts/collection_fingerprint_tool.py compare \
        exports/morrow_before.json exports/morrow_after.json
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

DEFAULT_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
DEFAULT_DB = os.environ.get('MONGODB_DATABASE', 'empower_development')


def content_hash(docs) -> str:
    """SHA-256 over documents, independent of document order and key order.

    Each document is canonicalised with json_util (which handles ObjectId,
    datetime and the rest of BSON), hashed, and the digests are sorted before
    the final hash, so a restore that returns the same documents in a different
    order compares equal.
    """
    digests = sorted(
        hashlib.sha256(json_util.dumps(doc, sort_keys=True).encode()).hexdigest()
        for doc in docs
    )
    return hashlib.sha256(''.join(digests).encode()).hexdigest()


def index_fingerprint(index_information: dict) -> dict:
    """Reduce pymongo's index_information() to the parts a restore can lose."""
    return {
        name: {'key': [list(pair) for pair in spec.get('key', [])],
               'unique': bool(spec.get('unique', False))}
        for name, spec in index_information.items()
    }


def fingerprint_collection(collection) -> dict:
    """Capture count, indexes and content hash. Read-only."""
    return {
        'count': collection.count_documents({}),
        'indexes': index_fingerprint(collection.index_information()),
        'content_hash': content_hash(collection.find({})),
    }


def compare_fingerprints(before: dict, after: dict) -> list:
    """Return a human-readable list of differences. Empty list means identical."""
    diffs = []
    if before['count'] != after['count']:
        diffs.append(f"count {before['count']:,} -> {after['count']:,}")

    for name in sorted(set(before['indexes']) | set(after['indexes'])):
        b, a = before['indexes'].get(name), after['indexes'].get(name)
        if b == a:
            continue
        if a is None:
            diffs.append(f"index dropped: {name} {b}")
        elif b is None:
            diffs.append(f"index added: {name} {a}")
        else:
            diffs.append(f"index changed: {name} {b} -> {a}")

    if before['content_hash'] != after['content_hash']:
        diffs.append(f"content hash {before['content_hash'][:12]} -> {after['content_hash'][:12]}")
    return diffs


def capture(collection_name: str, uri: str, db_name: str, out: str) -> dict:
    """Fingerprint one collection and optionally write it to JSON."""
    client = MongoClient(uri)
    fp = fingerprint_collection(client[db_name][collection_name])
    client.close()
    fp['collection'] = collection_name
    fp['database'] = db_name

    print(f"  {collection_name}")
    print(f"    count         {fp['count']:,}")
    print(f"    indexes       {', '.join(sorted(fp['indexes'])) or '(none)'}")
    print(f"    content hash  {fp['content_hash']}")
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(fp, indent=2))
        print(f"    written to    {out}")
    return fp


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['capture', 'compare'])
    p.add_argument('args', nargs='+', help='capture: <Collection> | compare: <before.json> <after.json>')
    p.add_argument('--out', help='write the capture to this JSON path')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--database', default=DEFAULT_DB)
    a = p.parse_args()

    if a.action == 'capture':
        capture(a.args[0], a.uri, a.database, a.out)
        return 0

    if len(a.args) != 2:
        p.error('compare needs exactly two JSON paths')
    before = json.loads(Path(a.args[0]).read_text())
    after = json.loads(Path(a.args[1]).read_text())
    diffs = compare_fingerprints(before, after)
    if not diffs:
        print(f"  IDENTICAL  {before.get('collection', '?')}  "
              f"{before['count']:,} docs, {len(before['indexes'])} index(es)")
        return 0
    print(f"  DIFFERENT  {before.get('collection', '?')}")
    for d in diffs:
        print(f"    {d}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
