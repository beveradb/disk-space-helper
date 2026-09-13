"""Read available disk space via df."""
from __future__ import annotations

import subprocess


def free_bytes(path: str = "/System/Volumes/Data") -> int:
    out = subprocess.run(
        ["df", "-k", path], capture_output=True, text=True, check=True
    ).stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    # Data row is the last line; column index 3 = Available (1024-blocks).
    fields = lines[-1].split()
    return int(fields[3]) * 1024
