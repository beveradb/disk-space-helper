from __future__ import annotations

import re
import subprocess

from handlers import base

NAME = "homebrew"
_FREE = re.compile(r"free approximately ([\d.]+)\s*([KMGT]?B)", re.I)
_UNIT = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}


def available(runner=subprocess.run) -> bool:
    rc, _, _ = base.run_cmd(["brew", "--version"], runner=runner)
    return rc == 0


def report(runner=subprocess.run) -> dict:
    _rc, out, _err = base.run_cmd(["brew", "cleanup", "-n"], runner=runner)
    m = _FREE.search(out)
    n = int(float(m.group(1)) * _UNIT[m.group(2).upper()]) if m else 0
    return {"handler": NAME, "reclaimable_bytes": n,
            "detail": "Run `brew cleanup` to reclaim.", "raw": out}
