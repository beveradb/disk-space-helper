#!/usr/bin/env python3
"""Apply an approved reclaim plan → macOS Trash. Dry-run by default."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dsh_lib import dfree, paths, trash

NEVER_TOUCH = ("/System", "/bin", "/sbin", "/usr", "/Volumes",
               "/private/var", "/Library", "/Applications")


def is_safe(path: str) -> bool:
    if not path.startswith("/"):
        return False
    norm = os.path.normpath(path).lower()
    for p in NEVER_TOUCH:
        pl = p.lower()
        if norm == pl or norm.startswith(pl + "/"):
            return False
    return True


def _log(log_path, record) -> None:
    if not log_path:
        return
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def run_plan(plan, *, apply: bool, trash_fn=trash.to_trash,
             log_path=None, run_id="") -> dict:
    planned, trashed, refused = [], [], []
    for item in plan:
        path = item["path"]
        if not is_safe(path):
            refused.append(path)
            if apply:
                _log(log_path, {"run_id": run_id, "path": path,
                                "action": "refused", "reason": item.get("reason", ""),
                                "rule_id": item.get("rule_id")})
            continue
        planned.append(path)
        if not apply:
            continue
        res = trash_fn(path)
        if res.ok:
            trashed.append(path)
        _log(log_path, {"run_id": run_id, "path": path,
                        "action": "trashed" if res.ok else "failed",
                        "method": res.method, "error": res.error,
                        "reason": item.get("reason", ""),
                        "rule_id": item.get("rule_id")})
    return {"planned": planned, "trashed": trashed, "refused": refused}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply a reclaim plan → Trash")
    ap.add_argument("plan")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    before = dfree.free_bytes()
    res = run_plan(plan, apply=args.apply, log_path=str(paths.decisions_log()))
    after = dfree.free_bytes() if args.apply else before
    res["freed_bytes"] = after - before
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
