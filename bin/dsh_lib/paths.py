"""Resolve the private data directory and bootstrap templates."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def repo_root() -> Path:
    # bin/dsh_lib/paths.py -> repo root is two parents up from dsh_lib.
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    env = os.environ.get("DSH_DATA_DIR")
    if env:
        base = Path(env).expanduser()
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg).expanduser() / "disk-space-helper") if xdg \
            else Path.home() / ".local" / "share" / "disk-space-helper"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def snapshots_dir() -> Path:
    return _sub("snapshots")


def reports_dir() -> Path:
    return _sub("reports")


def knowledge_dir() -> Path:
    return _sub("knowledge")


def decisions_log() -> Path:
    return data_dir() / "decisions.jsonl"


def profile_path() -> Path:
    return knowledge_dir() / "profile.md"


def rules_path() -> Path:
    return knowledge_dir() / "rules.yaml"


def bootstrap(repo: Path | None = None) -> None:
    repo = repo or repo_root()
    pairs = [
        (repo / "knowledge" / "profile.example.md", profile_path()),
        (repo / "knowledge" / "rules.example.yaml", rules_path()),
    ]
    for src, dst in pairs:
        if not dst.exists() and src.exists():
            shutil.copyfile(src, dst)
