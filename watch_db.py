#!/usr/bin/env python3
"""
Watch BoltLock SQLite DB to confirm it's receiving/writing data.

- Prints counts + latest rows from:
    events, state_history, devices
- Optional follow mode: poll for new rows and print as they arrive

Default DB location matches config/settings.py:
  ~/.local/share/boltlock/boltlock.db
or override via:
  --db /path/to/boltlock.db
  or env BOLTLOCK_DB_PATH=/path/to/boltlock.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple


DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "boltlock" / "boltlock.db"


def resolve_db_path(cli_db: Optional[str]) -> Path:
    if cli_db:
        return Path(cli_db).expanduser().resolve()

    env_db = os.environ.get("BOLTLOCK_DB_PATH", "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve()

    # Match the backend default (DB_DIR / "boltlock.db")
    return DEFAULT_DB_PATH


def connect(db_path: Path) -> sqlite3.Connection:
    # timeout helps if the backend is writing while we read
    con = sqlite3.connect(str(db_path), timeout=5)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def scalar_int(con: sqlite3.Connection, sql: str, params: Tuple = ()) -> int:
    row = con.execute(sql, params).fetchone()
    if not row:
        return 0
    # Works for both row[0] and named columns
    val = row[0]
    return int(val) if val is not None else 0


def print_rows(rows: Iterable[sqlite3.Row], columns: list[str]) -> None:
    rows = list(rows)
    if not rows:
        print("  (no rows)")
        return

    # basic fixed-width formatting
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in columns}
    header = "  " + " | ".join(c.ljust(widths[c]) for c in columns)
    sep = "  " + "-+-".join("-" * widths[c] for c in columns)
    print(header)
    print(sep)
    for r in rows:
        print("  " + " | ".join(str(r[c]).ljust(widths[c]) for c in columns))


@dataclass
class LastSeen:
    events_id: int = 0
    state_id: int = 0


def snapshot(con: sqlite3.Connection, limit: int) -> LastSeen:
    print("\nDB snapshot")

    # events
    if table_exists(con, "events"):
        events_count = scalar_int(con, "SELECT COUNT(*) FROM events")
        events_max_id = scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM events")
        print(f"\nTable: events (rows={events_count}, max_id={events_max_id})")
        rows = con.execute(
            "SELECT id, timestamp, event_type, description, device_id "
            "FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        print_rows(rows, ["id", "timestamp", "event_type", "description", "device_id"])
    else:
        print("\nTable: events (missing)")

    # state_history
    if table_exists(con, "state_history"):
        state_count = scalar_int(con, "SELECT COUNT(*) FROM state_history")
        state_max_id = scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM state_history")
        print(f"\nTable: state_history (rows={state_count}, max_id={state_max_id})")
        rows = con.execute(
            "SELECT id, timestamp, device_id, lock_state, door_state "
            "FROM state_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        print_rows(rows, ["id", "timestamp", "device_id", "lock_state", "door_state"])
    else:
        print("\nTable: state_history (missing)")

    # devices
    if table_exists(con, "devices"):
        devices_count = scalar_int(con, "SELECT COUNT(*) FROM devices")
        print(f"\nTable: devices (rows={devices_count})")
        rows = con.execute(
            "SELECT id, name, registered_at, last_seen "
            "FROM devices "
            "ORDER BY COALESCE(last_seen, registered_at) DESC "
            "LIMIT ?",
            (limit,),
        ).fetchall()
        print_rows(rows, ["id", "name", "registered_at", "last_seen"])
    else:
        print("\nTable: devices (missing)")

    return LastSeen(
        events_id=scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM events") if table_exists(con, "events") else 0,
        state_id=scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM state_history") if table_exists(con, "state_history") else 0,
    )


def follow(con: sqlite3.Connection, limit: int, interval: float) -> None:
    last = snapshot(con, limit=limit)

    print("\nFollow mode: watching for new rows (Ctrl+C to stop)\n")

    while True:
        changed = False

        if table_exists(con, "events"):
            new_max = scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM events")
            if new_max > last.events_id:
                changed = True
                rows = con.execute(
                    "SELECT id, timestamp, event_type, description, device_id "
                    "FROM events WHERE id > ? ORDER BY id ASC",
                    (last.events_id,),
                ).fetchall()
                print(f"\nNew events: {len(rows)}")
                print_rows(rows, ["id", "timestamp", "event_type", "description", "device_id"])
                last.events_id = new_max

        if table_exists(con, "state_history"):
            new_max = scalar_int(con, "SELECT COALESCE(MAX(id), 0) FROM state_history")
            if new_max > last.state_id:
                changed = True
                rows = con.execute(
                    "SELECT id, timestamp, device_id, lock_state, door_state "
                    "FROM state_history WHERE id > ? ORDER BY id ASC",
                    (last.state_id,),
                ).fetchall()
                print(f"\nNew state_history rows: {len(rows)}")
                print_rows(rows, ["id", "timestamp", "device_id", "lock_state", "door_state"])
                last.state_id = new_max

        if changed:
            sys.stdout.flush()

        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch BoltLock SQLite DB for new rows.")
    parser.add_argument("--db", help="Path to boltlock.db (overrides default).")
    parser.add_argument("--limit", type=int, default=10, help="Rows to show per table (default: 10).")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval seconds in follow mode (default: 2.0).")
    parser.add_argument("--follow", action="store_true", help="Poll continuously and print new rows as they appear.")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)

    if not db_path.exists():
        print(f"DB file not found: {db_path}")
        print("If your backend has not created it yet, start your backend first (run.py) so init_db() runs.")
        return 2

    print(f"Using DB: {db_path}")

    try:
        con = connect(db_path)
    except Exception as e:
        print(f"Failed to open DB: {e}")
        return 3

    try:
        if args.follow:
            follow(con, limit=args.limit, interval=args.interval)
        else:
            snapshot(con, limit=args.limit)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
