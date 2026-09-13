"""Move files/dirs to the macOS Trash (reversible), with a safe fallback."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple


class TrashResult(NamedTuple):
    path: str
    ok: bool
    method: str
    error: str | None


def _home_trash() -> Path:
    return Path.home() / ".Trash"


def _finder_delete(path: str, runner) -> None:
    posix = path.replace('"', '\\"')
    script = f'tell application "Finder" to delete POSIX file "{posix}"'
    res = runner(["osascript", "-e", script], capture_output=True, text=True)
    if getattr(res, "returncode", 1) != 0:
        raise RuntimeError(getattr(res, "stderr", "osascript failed"))


def _move_to_trash(path: str) -> None:
    src = Path(path)
    dst = _home_trash() / src.name
    i = 1
    while dst.exists():
        dst = _home_trash() / f"{src.stem} {i}{src.suffix}"
        i += 1
    shutil.move(str(src), str(dst))


def to_trash(path: str, *, runner=subprocess.run) -> TrashResult:
    try:
        _finder_delete(path, runner)
        return TrashResult(path, True, "finder", None)
    except Exception as finder_err:  # noqa: BLE001 - fall back on any failure
        try:
            _move_to_trash(path)
            return TrashResult(path, True, "move", None)
        except Exception as move_err:  # noqa: BLE001
            return TrashResult(path, False, "none",
                               f"{finder_err!s}; {move_err!s}")
