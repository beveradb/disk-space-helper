from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dsh_lib import sizes


def run_cmd(cmd, runner=subprocess.run):
    try:
        res = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return (127, "", "")
    return (getattr(res, "returncode", 1),
            getattr(res, "stdout", "") or "",
            getattr(res, "stderr", "") or "")


def dir_physical(path) -> int:
    total = 0
    for dp, _dn, fn in os.walk(path):
        for name in fn:
            try:
                st = os.lstat(os.path.join(dp, name))
            except OSError:
                continue
            total += sizes.physical_bytes(st)
    return total
