#!/usr/bin/env python3
"""
Labelled MongoDB checkpoint backups for empower_development.

Dumps collections matching a suffix pattern into a labelled checkpoint directory
so a multi-step migration can roll back to any point. Wraps mongodump/mongorestore
(mongodump has no --nsInclude, so collections are enumerated and dumped one by one).

Usage:
    # Create a checkpoint of every *ThermalLoads collection
    python src/scripts/backup_mongo_collections_tool.py create cp01-pre-typenorm --suffix ThermalLoads

    # Full-database checkpoint (single archive)
    python src/scripts/backup_mongo_collections_tool.py create cp00-baseline --full

    # List checkpoints
    python src/scripts/backup_mongo_collections_tool.py list

    # Verify a checkpoint restores cleanly (into a scratch db, production untouched)
    python src/scripts/backup_mongo_collections_tool.py verify cp01-pre-typenorm

    # Roll back one collection, or all of them
    python src/scripts/backup_mongo_collections_tool.py restore cp01-pre-typenorm --collection CuyahogaThermalLoads
    python src/scripts/backup_mongo_collections_tool.py restore cp01-pre-typenorm --all --yes
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient

DEFAULT_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
DEFAULT_DB = os.environ.get('MONGODB_DATABASE', 'empower_development')
BACKUP_ROOT = Path(os.environ.get('OCTOPUS_BACKUP_ROOT', Path.home() / 'backups' / 'octopus-thermal'))
SCRATCH_DB = '_restore_verify'


def _run(cmd: list, quiet: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, surfacing stderr on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd[:3])} ...")
    if not quiet:
        sys.stderr.write(proc.stderr)
    return proc


def collections_matching(uri: str, db_name: str, suffix: str) -> list:
    """Return sorted collection names ending with suffix."""
    client = MongoClient(uri)
    names = [n for n in client[db_name].list_collection_names() if n.endswith(suffix)]
    client.close()
    return sorted(names)


def create(label: str, uri: str, db_name: str, suffix: str, full: bool) -> Path:
    """Create a labelled checkpoint."""
    dest = BACKUP_ROOT / label
    if dest.exists():
        raise SystemExit(f"checkpoint already exists: {dest}\nPick a new label or delete it first.")
    dest.mkdir(parents=True)
    started = datetime.now()

    if full:
        archive = dest / 'full.gz'
        print(f"  dumping entire {db_name} -> {archive}", flush=True)
        _run(['mongodump', f'--uri={uri}', f'--db={db_name}', '--gzip',
              f'--archive={archive}', '--quiet'])
        cols = ['<full database archive>']
    else:
        cols = collections_matching(uri, db_name, suffix)
        if not cols:
            shutil.rmtree(dest)
            raise SystemExit(f"no collections ending in '{suffix}' found in {db_name}")
        for i, col in enumerate(cols, 1):
            print(f"  [{i}/{len(cols)}] {col}", flush=True)
            _run(['mongodump', f'--uri={uri}', f'--db={db_name}', f'--collection={col}',
                  '--gzip', f'--out={dest}', '--quiet'])

    elapsed = (datetime.now() - started).total_seconds()
    size = sum(f.stat().st_size for f in dest.rglob('*') if f.is_file())
    manifest = {
        'label': label, 'database': db_name, 'uri': uri,
        'mode': 'full' if full else f'suffix:{suffix}',
        'collections': cols, 'created_at': started.isoformat(),
        'elapsed_seconds': round(elapsed, 1), 'bytes': size,
    }
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f"\n  checkpoint '{label}' -> {dest}")
    print(f"  {len(cols)} collection(s), {size/1e6:.1f} MB, {elapsed:.0f}s")
    return dest


def list_checkpoints() -> None:
    """Print every checkpoint under BACKUP_ROOT."""
    if not BACKUP_ROOT.exists():
        print(f"no checkpoints yet ({BACKUP_ROOT} does not exist)")
        return
    rows = sorted(BACKUP_ROOT.iterdir(), key=lambda p: p.name)
    if not rows:
        print(f"no checkpoints in {BACKUP_ROOT}")
        return
    print(f"{'label':<30} {'created':<20} {'size':>10}  collections")
    for d in rows:
        mf = d / 'manifest.json'
        if not mf.exists():
            print(f"{d.name:<30} {'(no manifest)':<20}")
            continue
        m = json.loads(mf.read_text())
        print(f"{m['label']:<30} {m['created_at'][:19]:<20} {m['bytes']/1e6:>9.1f}M  {len(m['collections'])}")


def verify(label: str, uri: str) -> None:
    """Restore a checkpoint into a scratch database and compare counts. Production untouched."""
    src = BACKUP_ROOT / label
    m = json.loads((src / 'manifest.json').read_text())
    if m['mode'] == 'full':
        raise SystemExit("verify supports suffix checkpoints; restore a full archive manually to a scratch db")

    client = MongoClient(uri)
    client.drop_database(SCRATCH_DB)
    db_name = m['database']
    ok = True
    for col in m['collections']:
        _run(['mongorestore', f'--uri={uri}', '--gzip',
              f'--nsInclude={db_name}.{col}',
              f'--nsFrom={db_name}.{col}', f'--nsTo={SCRATCH_DB}.{col}',
              '--drop', str(src), '--quiet'])
        live = client[db_name][col].count_documents({})
        back = client[SCRATCH_DB][col].count_documents({})
        flag = 'ok' if live == back else 'MISMATCH'
        if live != back:
            ok = False
        print(f"  {col:<28} live {live:>9,}  backup {back:>9,}  {flag}")
    client.drop_database(SCRATCH_DB)
    client.close()
    print(f"\n  scratch database dropped. checkpoint '{label}': {'VERIFIED' if ok else 'FAILED'}")
    if not ok:
        raise SystemExit(1)


def restore(label: str, uri: str, collection: str, restore_all: bool, yes: bool) -> None:
    """Roll production back to a checkpoint. Destructive: drops before restoring."""
    src = BACKUP_ROOT / label
    m = json.loads((src / 'manifest.json').read_text())
    db_name = m['database']
    targets = m['collections'] if restore_all else [collection]
    if not restore_all and collection not in m['collections']:
        raise SystemExit(f"'{collection}' is not in checkpoint '{label}'")

    print(f"  about to DROP and restore {len(targets)} collection(s) in {db_name} from '{label}'")
    if not yes:
        if input("  type 'restore' to proceed: ").strip() != 'restore':
            raise SystemExit("aborted")
    for col in targets:
        print(f"  restoring {col}", flush=True)
        _run(['mongorestore', f'--uri={uri}', '--gzip',
              f'--nsInclude={db_name}.{col}', '--drop', str(src), '--quiet'])
    print(f"  restored {len(targets)} collection(s) from '{label}'")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['create', 'list', 'verify', 'restore'])
    p.add_argument('label', nargs='?', help='checkpoint label, e.g. cp01-pre-typenorm')
    p.add_argument('--suffix', default='ThermalLoads', help='collection name suffix to dump')
    p.add_argument('--full', action='store_true', help='dump the whole database as one archive')
    p.add_argument('--collection', help='single collection to restore')
    p.add_argument('--all', action='store_true', dest='restore_all', help='restore every collection')
    p.add_argument('--yes', action='store_true', help='skip the restore confirmation prompt')
    p.add_argument('--uri', default=DEFAULT_URI)
    p.add_argument('--database', default=DEFAULT_DB)
    args = p.parse_args()

    if args.action == 'list':
        list_checkpoints()
        return 0
    if not args.label:
        p.error(f"'{args.action}' requires a label")
    if args.action == 'create':
        create(args.label, args.uri, args.database, args.suffix, args.full)
    elif args.action == 'verify':
        verify(args.label, args.uri)
    elif args.action == 'restore':
        if not args.restore_all and not args.collection:
            p.error("restore needs --collection NAME or --all")
        restore(args.label, args.uri, args.collection, args.restore_all, args.yes)
    return 0


if __name__ == '__main__':
    sys.exit(main())
