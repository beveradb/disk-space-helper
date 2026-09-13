from __future__ import annotations

from pathlib import Path

from handlers import base

NAME = "xcode"


def _roots():
    dev = Path.home() / "Library" / "Developer" / "Xcode"
    return [dev / "DerivedData",
            dev / "iOS DeviceSupport",
            dev / "watchOS DeviceSupport"]


def available(runner=None) -> bool:
    return any(r.exists() for r in _roots())


def report(runner=None) -> dict:
    total = sum(base.dir_physical(r) for r in _roots() if r.exists())
    return {"handler": NAME, "reclaimable_bytes": total,
            "detail": "DerivedData regenerates on build; old DeviceSupport "
                      "only needed for those iOS versions."}
