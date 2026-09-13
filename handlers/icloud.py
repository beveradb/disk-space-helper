from __future__ import annotations

import subprocess

from handlers import base

NAME = "icloud"


def evict(path: str, runner=subprocess.run) -> bool:
    rc, _out, _err = base.run_cmd(["brctl", "evict", path], runner=runner)
    return rc == 0
