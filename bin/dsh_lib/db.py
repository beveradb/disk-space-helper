"""SQLite snapshot storage."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS entries (
    path TEXT PRIMARY KEY,
    kind TEXT NOT NULL,          -- 'file' | 'dir'
    category TEXT NOT NULL,
    logical INTEGER NOT NULL,
    physical INTEGER NOT NULL,
    mtime REAL,
    atime REAL,
    dataless INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_physical ON entries(physical DESC);
CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path)))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    if cur.fetchone() is None:
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
        conn.commit()
    return conn


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))


def get_meta(conn, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def insert_entry(conn, entry: dict) -> None:
    conn.execute(
        "INSERT INTO entries(path, kind, category, logical, physical, mtime, "
        "atime, dataless) VALUES(:path, :kind, :category, :logical, :physical, "
        ":mtime, :atime, :dataless) "
        "ON CONFLICT(path) DO UPDATE SET "
        "kind=excluded.kind, category=excluded.category, logical=excluded.logical, "
        "physical=excluded.physical, mtime=excluded.mtime, atime=excluded.atime, "
        "dataless=excluded.dataless",
        entry,
    )


def top_by_physical(conn, limit: int = 50, category: str | None = None):
    if category:
        return conn.execute(
            "SELECT * FROM entries WHERE category=? ORDER BY physical DESC LIMIT ?",
            (category, limit)).fetchall()
    return conn.execute(
        "SELECT * FROM entries ORDER BY physical DESC LIMIT ?", (limit,)).fetchall()


def totals_by_category(conn) -> dict:
    row = conn.execute(
        "SELECT value FROM meta WHERE key='category_totals'").fetchone()
    if row and row["value"]:
        return {k: int(v) for k, v in json.loads(row["value"]).items()}
    rows = conn.execute(
        "SELECT category, SUM(physical) AS total FROM entries GROUP BY category"
    ).fetchall()
    return {r["category"]: int(r["total"]) for r in rows}
