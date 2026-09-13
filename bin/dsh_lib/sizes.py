"""Size accounting and path classification."""
from __future__ import annotations

import os
import re

SF_DATALESS = 0x40000000  # macOS dataless (cloud online-only) file flag


def physical_bytes(st: os.stat_result) -> int:
    return int(getattr(st, "st_blocks", 0)) * 512


def logical_bytes(st: os.stat_result) -> int:
    return int(st.st_size)


def is_dataless(st_flags: int) -> bool:
    return bool(st_flags & SF_DATALESS)


_DEV_CACHE = re.compile(
    r"/(node_modules|\.venv|venv|__pycache__|target|\.gradle|\.cargo|"
    r"DerivedData|\.npm|\.pnpm-store|\.yarn|Library/Caches/(pip|Homebrew|"
    r"com\.apple\.dt\.Xcode|typescript))(/|$)"
)
_MEDIA_EXT = re.compile(r"\.(mov|mp4|m4v|avi|mkv|wav|aiff|flac|mp3|"
                        r"psd|tiff|raw|arw|cr2|nef|dng)$", re.I)


def classify(path: str) -> str:
    home = os.path.expanduser("~")
    p = path
    if p.startswith(f"{home}/Dropbox") or "/Dropbox/" in p:
        return "cloud-dropbox"
    if "/Library/Mobile Documents/" in p:
        return "cloud-icloud"
    if _DEV_CACHE.search(p):
        return "dev-cache"
    if p.startswith(f"{home}/Downloads"):
        return "downloads"
    if "/Library/Caches/" in p or "/Library/Logs/" in p:
        return "system-cache"
    if "/Library/Application Support/" in p:
        return "app-support"
    if _MEDIA_EXT.search(p) or p.startswith(f"{home}/Movies"):
        return "media"
    return "other"
