#!/usr/bin/env python3
"""Careful metadata-only disk scanner → SQLite snapshot.

Records a browse/drill-down tree in `entries` (large files + recursive
directory rollups) and stores EXACT per-file category totals in `meta`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dsh_lib import db, dfree, paths, sizes

DEFAULT_EXCLUDES = {
    "/System", "/Volumes", "/private/var", "/private/tmp", "/dev", "/net",
    "/.vol", "/cores",
}
NO_DESCEND = ("node_modules", ".git", "DerivedData", ".venv", "venv",
              "__pycache__", "target", ".gradle", ".cargo")

DEFAULT_MIN_FILE_BYTES = 10 * 1024 * 1024
DEFAULT_DIR_MIN_BYTES = 50 * 1024 * 1024


def is_excluded(path: str, excludes) -> bool:
    return any(path == e or path.startswith(e + "/") for e in excludes)


def _dir_footprint(entry_path: str):
    """Recursive (physical, logical, max_mtime) for a NO_DESCEND dir, metadata
    only; records nothing."""
    phys = logi = 0
    latest = 0.0
    for dp, _dn, fn in os.walk(entry_path):
        for name in fn:
            try:
                st = os.lstat(os.path.join(dp, name))
            except OSError:
                continue
            phys += sizes.physical_bytes(st)
            logi += sizes.logical_bytes(st)
            latest = max(latest, st.st_mtime)
    return phys, logi, latest


class _Scanner:
    def __init__(self, conn, min_file_bytes, dir_min_bytes, excludes):
        self.conn = conn
        self.min_file_bytes = min_file_bytes
        self.dir_min_bytes = dir_min_bytes
        self.excludes = excludes
        self.category_totals = defaultdict(int)
        self.total_physical = 0
        self.total_logical = 0

    def _record(self, path, kind, phys, logi, mtime, atime, flags):
        db.insert_entry(self.conn, dict(
            path=path, kind=kind, category=sizes.classify(path),
            logical=logi, physical=phys, mtime=mtime, atime=atime,
            dataless=int(sizes.is_dataless(flags)),
        ))

    def scan_dir(self, path):
        """Recurse into `path`. Record rows; return recursive
        (physical, logical, max_mtime)."""
        tot_p = tot_l = 0
        latest = 0.0
        try:
            it = os.scandir(path)
        except OSError:
            return 0, 0, 0.0
        with it:
            for de in it:
                p = de.path
                if is_excluded(p, self.excludes):
                    continue
                try:
                    st = de.stat(follow_symlinks=False)
                except OSError:
                    continue
                if de.is_symlink():
                    continue
                flags = getattr(st, "st_flags", 0)
                if de.is_dir(follow_symlinks=False):
                    if de.name in NO_DESCEND:
                        phys, logi, lm = _dir_footprint(p)
                        self.category_totals[sizes.classify(p)] += phys
                        self.total_physical += phys
                        self.total_logical += logi
                        self._record(p, "dir", phys, logi, lm, st.st_atime, flags)
                    else:
                        phys, logi, lm = self.scan_dir(p)
                        if phys >= self.dir_min_bytes:
                            self._record(p, "dir", phys, logi, lm,
                                         st.st_atime, flags)
                    tot_p += phys
                    tot_l += logi
                    latest = max(latest, lm)
                else:
                    phys = sizes.physical_bytes(st)
                    logi = sizes.logical_bytes(st)
                    self.category_totals[sizes.classify(p)] += phys
                    self.total_physical += phys
                    self.total_logical += logi
                    tot_p += phys
                    tot_l += logi
                    latest = max(latest, st.st_mtime)
                    if phys >= self.min_file_bytes:
                        self._record(p, "file", phys, logi, st.st_mtime,
                                     st.st_atime, flags)
        return tot_p, tot_l, latest


def scan_tree(roots, conn, *, min_file_bytes=DEFAULT_MIN_FILE_BYTES,
              dir_min_bytes=DEFAULT_DIR_MIN_BYTES, excludes=None):
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    sys.setrecursionlimit(20000)
    scanner = _Scanner(conn, min_file_bytes, dir_min_bytes, excludes)
    for root in roots:
        if is_excluded(root, excludes):
            continue
        phys, logi, lm = scanner.scan_dir(root)
        try:
            st = os.lstat(root)
            atime = st.st_atime
            flags = getattr(st, "st_flags", 0)
        except OSError:
            atime = 0.0
            flags = 0
        scanner._record(root, "dir", phys, logi, lm, atime, flags)
    totals = dict(scanner.category_totals)
    db.set_meta(conn, "category_totals", json.dumps(totals))
    db.set_meta(conn, "total_physical", str(scanner.total_physical))
    n = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
    return {"totals": totals, "entries": int(n),
            "total_physical": scanner.total_physical}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scan disk usage → SQLite snapshot")
    ap.add_argument("--roots", nargs="+", default=[str(Path.home())])
    ap.add_argument("--min-mib", type=int, default=10)
    ap.add_argument("--dir-min-mib", type=int, default=50)
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
                        min_file_bytes=args.min_mib * 1024 * 1024,
                        dir_min_bytes=args.dir_min_mib * 1024 * 1024)
    conn.commit()
    payload = {"df_free": free, "totals": summary["totals"],
               "entries": summary["entries"],
               "total_physical": summary["total_physical"]}
    (out.parent / "summary.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
