from __future__ import annotations

from pathlib import Path

from handlers import base

NAME = "dropbox"
_MANUAL = ("Dropbox online-only has no supported CLI on macOS. Manual: select "
           "folders in Finder → right-click → 'Make Online Only'. This handler "
           "only reports; it never mutates Dropbox.")


def _dropbox_root() -> Path:
    return Path.home() / "Dropbox"


def available(runner=None) -> bool:
    return _dropbox_root().exists()


def report(runner=None) -> dict:
    root = _dropbox_root()
    total = base.dir_physical(root) if root.exists() else 0
    return {"handler": NAME, "reclaimable_bytes": total, "experimental": True,
            "detail": _MANUAL}
