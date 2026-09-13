#!/usr/bin/env python3
"""Careful metadata-only disk scanner → SQLite snapshot."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dsh_lib import db, dfree, paths, sizes

DEFAULT_EXCLUDES = {
    "/System", "/Volumes", "/private/var", "/private/tmp", "/dev", "/net",
    "/.vol", "/cores",
}
NO_DESCEND = ("node_modules", ".git", "DerivedData", ".venv", "venv",
              "__pycache__", "target", ".gradle", ".cargo")


def is_excluded(path: str, excludes) -> bool:
    return any(path == e or path.startswith(e + "/") for e in excludes)


def _dir_footprint(entry_path: str):
    """Return (physical, logical, max_mtime) by walking a no-descend dir,
    metadata only."""
    phys = logi = 0
    latest = 0.0
    for dp, dn, fn in os.walk(entry_path, topdown=True):
        for name in fn:
            try:
                st = os.lstat(os.path.join(dp, name))
            except OSError:
                continue
            phys += sizes.physical_bytes(st)
            logi += sizes.logical_bytes(st)
            latest = max(latest, st.st_mtime)
    return phys, logi, latest


def scan_tree(roots, conn, *, min_file_bytes=10 * 1024 * 1024, excludes=None):
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    for root in roots:
        _scan_one(root, conn, min_file_bytes, excludes)
    totals = db.totals_by_category(conn)
    n = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
    return {"totals": totals, "entries": int(n)}


def _scan_one(root, conn, min_file_bytes, excludes):
    stack = [root]
    while stack:
        cur = stack.pop()
        if is_excluded(cur, excludes):
            continue
        try:
            with os.scandir(cur) as it:
                dir_phys = dir_logi = 0
                dir_latest = 0.0
                for de in it:
                    p = de.path
                    try:
                        st = de.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if de.is_symlink():
                        continue
                    if de.is_dir(follow_symlinks=False):
                        if de.name in NO_DESCEND:
                            phys, logi, latest = _dir_footprint(p)
                            db.insert_entry(conn, dict(
                                path=p, kind="dir",
                                category=sizes.classify(p),
                                logical=logi, physical=phys,
                                mtime=latest, atime=st.st_atime,
                                dataless=int(sizes.is_dataless(getattr(st, "st_flags", 0))),
                            ))
                            dir_phys += phys
                            dir_logi += logi
                        elif not is_excluded(p, excludes):
                            stack.append(p)
                    else:
                        phys = sizes.physical_bytes(st)
                        dir_phys += phys
                        dir_logi += sizes.logical_bytes(st)
                        dir_latest = max(dir_latest, st.st_mtime)
                        if phys >= min_file_bytes:
                            db.insert_entry(conn, dict(
                                path=p, kind="file",
                                category=sizes.classify(p),
                                logical=sizes.logical_bytes(st), physical=phys,
                                mtime=st.st_mtime, atime=st.st_atime,
                                dataless=int(sizes.is_dataless(getattr(st, "st_flags", 0))),
                            ))
        except OSError:
            continue


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scan disk usage → SQLite snapshot")
    ap.add_argument("--roots", nargs="+", default=[str(Path.home())])
    ap.add_argument("--min-mib", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else \
        paths.snapshots_dir() / "snapshot-latest.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(out)
    free = dfree.free_bytes()
    db.set_meta(conn, "df_free", str(free))
    db.set_meta(conn, "roots", json.dumps(args.roots))
    summary = scan_tree(args.roots, conn,
                        min_file_bytes=args.min_mib * 1024 * 1024)
    conn.commit()
    payload = {"df_free": free, "totals": summary["totals"],
               "entries": summary["entries"]}
    (out.parent / "summary.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
