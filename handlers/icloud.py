from __future__ import annotations

import subprocess
from pathlib import Path

from handlers import base

NAME = "icloud"


def _icloud_root() -> Path:
    return Path.home() / "Library" / "Mobile Documents"


def available(runner=subprocess.run) -> bool:
    if not _icloud_root().exists():
        return False
    rc, _out, _err = base.run_cmd(["brctl", "quota"], runner=runner)
    return rc == 0


def report(runner=None) -> dict:
    root = _icloud_root()
    total = base.dir_physical(root) if root.exists() else 0
    return {"handler": NAME, "reclaimable_bytes": total,
            "detail": "Evict local iCloud Drive files to online-only with "
                      "`brctl evict <path>` (supported). Files stay in the cloud."}


def evict(path: str, runner=subprocess.run) -> bool:
    rc, _out, _err = base.run_cmd(["brctl", "evict", path], runner=runner)
    return rc == 0
