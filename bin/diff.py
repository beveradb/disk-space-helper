#!/usr/bin/env python3
"""Diff two disk snapshots by physical footprint."""
from __future__ import annotations

import argparse
import json

from dsh_lib import db


def _physical_map(conn) -> dict:
    return {r["path"]: int(r["physical"])
            for r in conn.execute("SELECT path, physical FROM entries").fetchall()}


def diff_snapshots(old_conn, new_conn) -> dict:
    old = _physical_map(old_conn)
    new = _physical_map(new_conn)
    grew, shrank, appeared, disappeared = [], [], [], []
    for path in set(old) | set(new):
        o = old.get(path, 0)
        n = new.get(path, 0)
        if o and not n:
            disappeared.append({"path": path, "old": o, "new": 0, "delta": -o})
        elif n and not o:
            appeared.append({"path": path, "old": 0, "new": n, "delta": n})
        elif n > o:
            grew.append({"path": path, "old": o, "new": n, "delta": n - o})
        elif n < o:
            shrank.append({"path": path, "old": o, "new": n, "delta": n - o})
    for lst in (grew, shrank, appeared, disappeared):
        lst.sort(key=lambda e: abs(e["delta"]), reverse=True)
    return {"grew": grew, "shrank": shrank,
            "appeared": appeared, "disappeared": disappeared}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diff two snapshots")
    ap.add_argument("old")
    ap.add_argument("new")
    args = ap.parse_args(argv)
    d = diff_snapshots(db.connect(args.old), db.connect(args.new))
    print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
