"""Consistent SQLite backup (works while the app is running), compressed, with retention.

Usage:  python scripts/backup_db.py [--db PATH] [--out DIR] [--keep N] [--loop]
Env defaults: DATABASE_PATH, BACKUP_DIR (default ./backups), BACKUP_KEEP (14), BACKUP_HOUR_UTC (21).
--loop runs forever: one backup every night at BACKUP_HOUR_UTC.
Restore:  python scripts/backup_db.py --restore BACKUP.db.gz [--db PATH]   (stop the app first; see OPERATIONS.md)
"""
import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PREFIX = "shop_concierge-"


def backup(db_path, out_dir, keep=14, now=None):
    db_path, out_dir = Path(db_path), Path(out_dir)
    if not db_path.exists():
        raise FileNotFoundError("database not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{PREFIX}{stamp}.db.gz"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.db"
        src = sqlite3.connect(str(db_path), timeout=30)
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)                      # SQLite online backup API: consistent snapshot
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup failed the integrity check")
        finally:
            dst.close()
            src.close()
        partial = target.with_suffix(".partial")
        with open(copy, "rb") as f_in, open(partial, "wb") as raw:
            os.fchmod(raw.fileno(), 0o600)
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f_out:
                shutil.copyfileobj(f_in, f_out)
        partial.rename(target)                   # a half-written file never looks like a backup
    old = sorted(out_dir.glob(f"{PREFIX}*.db.gz"))[:-keep] if keep > 0 else []
    for path in old:
        path.unlink()
    return target


def restore(backup_path, db_path):
    """Replace the database with a backup. The old database is kept as <db>.before-restore."""
    backup_path, db_path = Path(backup_path), Path(db_path)
    if not backup_path.exists():
        raise FileNotFoundError("backup file not found")
    with tempfile.TemporaryDirectory(dir=db_path.parent if db_path.parent.exists() else None) as tmp:
        candidate = Path(tmp) / "restored.db"
        with gzip.open(backup_path, "rb") as f_in, open(candidate, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        check = sqlite3.connect(str(candidate))
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup failed the integrity check; nothing was changed")
            check.execute("SELECT COUNT(*) FROM shops").fetchone()      # must look like our database
        finally:
            check.close()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            shutil.copy2(db_path, db_path.with_name(db_path.name + ".before-restore"))
        for suffix in ("-wal", "-shm"):                                   # stale journal files would corrupt it
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        shutil.move(str(candidate), str(db_path))
    return db_path


def seconds_until(hour_utc, now=None):
    now = now or datetime.now(timezone.utc)
    nxt = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_PATH", "data/shop_concierge.db"))
    ap.add_argument("--out", default=os.environ.get("BACKUP_DIR", "backups"))
    ap.add_argument("--keep", type=int, default=int(os.environ.get("BACKUP_KEEP", "14")))
    ap.add_argument("--hour-utc", type=int, default=int(os.environ.get("BACKUP_HOUR_UTC", "21")))
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--restore", metavar="BACKUP.db.gz", help="restore this backup over --db (stop the app first)")
    args = ap.parse_args(argv)
    if args.restore:
        try:
            print(f"restored {restore(args.restore, args.db)}; previous database kept as .before-restore")
            return 0
        except Exception as exc:                 # noqa: BLE001
            print(f"RESTORE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    while True:
        if args.loop:
            time.sleep(seconds_until(args.hour_utc))
        try:
            print(f"backup written: {backup(args.db, args.out, args.keep)}", flush=True)
        except Exception as exc:                 # noqa: BLE001
            print(f"BACKUP FAILED: {type(exc).__name__}", file=sys.stderr, flush=True)
            if not args.loop:
                return 1
        if not args.loop:
            return 0


if __name__ == "__main__":
    sys.exit(main())
