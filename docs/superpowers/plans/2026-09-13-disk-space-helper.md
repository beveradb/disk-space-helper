# disk-space-helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude-Code-native personal disk-space reasoning system for macOS: deterministic Python scripts scan/diff/reclaim disk usage while Claude Code reasons, interviews the user, and learns across runs via a private out-of-repo knowledge base.

**Architecture:** Python 3 stdlib-first scripts under `bin/` (scanner → SQLite snapshot, diff, reclaim-to-Trash) plus a small shared `dsh_lib/` package and pluggable `handlers/`. All personal state lives in `$DSH_DATA_DIR` (default `~/.local/share/disk-space-helper`) so the repo can be public. Two `.claude/commands/` files orchestrate Claude's reasoning/interview loop.

**Tech Stack:** Python 3.14 (stdlib: `os`, `sqlite3`, `json`, `subprocess`, `shutil`), PyYAML for rules, pytest for tests. macOS-only.

## Global Constraints

- Platform: **macOS only** (uses `st_flags`, `st_blocks`, `osascript`, `brctl`, `df`, Homebrew).
- Python **3.11+** (target 3.14); stdlib-first, only third-party dep is **PyYAML**.
- **No personal data in the repo.** All real state under `$DSH_DATA_DIR`; repo ships `*.example.*` templates only.
- Deletions go to **macOS Trash, never `rm`**; reclaim is **dry-run by default**, `--apply` to act.
- Scanner reads **metadata only** (`os.lstat`), never file contents — must never hydrate online-only files.
- **Reclaimable size = physical footprint** (`st_blocks × 512`); logical size (`st_size`) tracked separately.
- Data-dir resolution precedence: `DSH_DATA_DIR` → `$XDG_DATA_HOME/disk-space-helper` → `~/.local/share/disk-space-helper`.
- TDD: write failing test → confirm fail → implement → confirm pass → commit.

---

## File Structure

```
bin/
  scan.py            # CLI: walk roots → SQLite snapshot + summary.json
  diff.py            # CLI: compare two snapshots
  reclaim.py         # CLI: apply approved plan JSON → Trash (dry-run default)
  dsh_lib/
    __init__.py
    paths.py         # data-dir resolution + template bootstrap
    sizes.py         # physical/logical helpers, dataless flag, category classification
    db.py            # sqlite schema, insert, queries
    dfree.py         # df reader
    trash.py         # move-to-Trash abstraction (mockable)
    rules.py         # load rules.yaml + classify entries
handlers/
  __init__.py
  base.py            # Handler protocol + helpers
  homebrew.py docker.py xcode.py pkgcaches.py icloud.py dropbox.py
knowledge/
  profile.example.md
  rules.example.yaml
.claude/commands/
  scan.md
  reclaim.md
tests/
  conftest.py
  test_paths.py test_sizes.py test_db.py test_dfree.py
  test_scan.py test_diff.py test_trash.py test_rules.py test_reclaim.py
  test_handlers.py
pyproject.toml
README.md
```

---

### Task 1: Project scaffold & pytest

**Files:**
- Create: `pyproject.toml`
- Create: `bin/dsh_lib/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: importable package `dsh_lib`; `pytest` runs from repo root.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "disk-space-helper"
version = "0.1.0"
description = "Personal disk-space reasoning system for macOS, driven by Claude Code"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0"]

[tool.pytest.ini_options]
pythonpath = ["bin"]
testpaths = ["tests"]

[tool.setuptools]
packages = ["dsh_lib"]
package-dir = {"" = "bin"}
```

- [ ] **Step 2: Create package + test files**

`bin/dsh_lib/__init__.py`:
```python
"""disk-space-helper shared library."""
__all__ = []
```

`tests/__init__.py`: (empty file)

`tests/test_smoke.py`:
```python
def test_import_dsh_lib():
    import dsh_lib  # noqa: F401
```

- [ ] **Step 3: Install deps and run**

Run: `python3 -m pip install -e . pytest && python3 -m pytest -q`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml bin/dsh_lib/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold project and pytest"
```

---

### Task 2: Data-dir resolution & template bootstrap

**Files:**
- Create: `bin/dsh_lib/paths.py`
- Create: `knowledge/profile.example.md`
- Create: `knowledge/rules.example.yaml`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `data_dir() -> pathlib.Path` — resolved base data dir (created).
  - `snapshots_dir() -> Path`, `reports_dir() -> Path`, `knowledge_dir() -> Path`.
  - `decisions_log() -> Path` — path to `decisions.jsonl`.
  - `profile_path() -> Path`, `rules_path() -> Path`.
  - `repo_root() -> Path` — the repo root (parent of `bin/`).
  - `bootstrap(repo_root: Path | None = None) -> None` — copies `knowledge/*.example.*` into the data dir as real files if absent.

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:
```python
import importlib
import pytest


@pytest.fixture
def fresh_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DSH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    import dsh_lib.paths as paths
    importlib.reload(paths)
    return paths


def test_data_dir_uses_env_and_is_created(fresh_paths, tmp_path):
    d = fresh_paths.data_dir()
    assert d == tmp_path / "data"
    assert d.is_dir()


def test_xdg_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("DSH_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    import dsh_lib.paths as paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path / "xdg" / "disk-space-helper"


def test_subdirs_and_files(fresh_paths):
    assert fresh_paths.snapshots_dir().is_dir()
    assert fresh_paths.reports_dir().is_dir()
    assert fresh_paths.knowledge_dir().is_dir()
    assert fresh_paths.decisions_log().name == "decisions.jsonl"


def test_bootstrap_copies_examples(fresh_paths):
    fresh_paths.bootstrap()
    assert fresh_paths.profile_path().exists()
    assert fresh_paths.rules_path().exists()
    # Second call must not raise or overwrite.
    fresh_paths.profile_path().write_text("EDITED")
    fresh_paths.bootstrap()
    assert fresh_paths.profile_path().read_text() == "EDITED"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.paths`).

- [ ] **Step 3: Implement `bin/dsh_lib/paths.py`**

```python
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
```

- [ ] **Step 4: Create example templates**

`knowledge/profile.example.md`:
```markdown
# Disk-Space Profile — <your name>

Durable, machine-specific facts about how I use this Mac. Claude appends to this
during interview sessions. Examples:

- Role: (e.g. developer — Node/Python/iOS)
- Xcode: keep DeviceSupport for the last N iOS versions only
- Dropbox: `/Photos` is archive — safe to keep online-only
- Downloads: safe to clear anything older than N days
```

`knowledge/rules.example.yaml`:
```yaml
# Learned classification rules. Each rule is applied to scanned paths.
# action: keep | auto-trash | ask
rules:
  - id: xcode-derived-data
    pattern: "~/Library/Developer/Xcode/DerivedData/*"
    action: ask
    confidence: medium
    rationale: "Regenerated on next build; usually safe to remove."
    learned_on: 2026-09-13
    times_applied: 0
```

- [ ] **Step 5: Run to verify pass**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add bin/dsh_lib/paths.py knowledge/profile.example.md knowledge/rules.example.yaml tests/test_paths.py
git commit -m "feat: data-dir resolution and template bootstrap"
```

---

### Task 3: Size accounting, dataless flag, category classification

**Files:**
- Create: `bin/dsh_lib/sizes.py`
- Test: `tests/test_sizes.py`

**Interfaces:**
- Produces:
  - `SF_DATALESS = 0x40000000`
  - `physical_bytes(st: os.stat_result) -> int` — `st_blocks * 512`.
  - `logical_bytes(st: os.stat_result) -> int` — `st_size`.
  - `is_dataless(st_flags: int) -> bool`
  - `classify(path: str) -> str` — returns one of: `dev-cache`, `downloads`, `media`, `app-support`, `cloud-dropbox`, `cloud-icloud`, `system-cache`, `other`.

- [ ] **Step 1: Write the failing test**

`tests/test_sizes.py`:
```python
import os
from dsh_lib import sizes


def test_physical_vs_logical_on_sparse(tmp_path):
    f = tmp_path / "sparse.bin"
    with open(f, "wb") as fh:
        fh.truncate(50 * 1024 * 1024)  # 50 MiB logical, ~0 physical
    st = os.lstat(f)
    assert sizes.logical_bytes(st) == 50 * 1024 * 1024
    assert sizes.physical_bytes(st) < sizes.logical_bytes(st)


def test_is_dataless():
    assert sizes.is_dataless(sizes.SF_DATALESS) is True
    assert sizes.is_dataless(0) is False
    assert sizes.is_dataless(sizes.SF_DATALESS | 0x1) is True


def test_classify():
    home = os.path.expanduser("~")
    assert sizes.classify(f"{home}/Library/Caches/foo") == "system-cache"
    assert sizes.classify(f"{home}/Downloads/big.dmg") == "downloads"
    assert sizes.classify(f"{home}/Dropbox/x") == "cloud-dropbox"
    assert sizes.classify(f"{home}/Library/Mobile Documents/x") == "cloud-icloud"
    assert sizes.classify(f"{home}/proj/node_modules/x") == "dev-cache"
    assert sizes.classify(f"{home}/Movies/clip.mov") == "media"
    assert sizes.classify(f"{home}/Library/Application Support/x") == "app-support"
    assert sizes.classify(f"{home}/random/thing.txt") == "other"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_sizes.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.sizes`).

- [ ] **Step 3: Implement `bin/dsh_lib/sizes.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_sizes.py -q`
Expected: 3 passed.

Note: if APFS does not create a sparse file on `truncate`, the assertion
`physical < logical` still holds because an all-zero 50 MiB region is stored
sparsely on APFS. If the environment ever fails this, keep the test but skip via
`pytest.importorskip`-style guard is NOT needed; APFS is the macOS default.

- [ ] **Step 5: Commit**

```bash
git add bin/dsh_lib/sizes.py tests/test_sizes.py
git commit -m "feat: size accounting, dataless flag, path classification"
```

---

### Task 4: SQLite snapshot schema & queries

**Files:**
- Create: `bin/dsh_lib/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION = 1`
  - `connect(path) -> sqlite3.Connection` — opens/creates DB, applies schema.
  - `set_meta(conn, key, value)` / `get_meta(conn, key) -> str | None`
  - `insert_entry(conn, entry: dict)` — keys: `path, kind, category, logical, physical, mtime, atime, dataless`.
  - `top_by_physical(conn, limit=50, category=None) -> list[sqlite3.Row]`
  - `totals_by_category(conn) -> dict[str, int]` — physical bytes per category.

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
from dsh_lib import db


def _entry(path, physical, category="other", kind="file"):
    return dict(path=path, kind=kind, category=category, logical=physical,
                physical=physical, mtime=1.0, atime=1.0, dataless=0)


def test_insert_and_query(tmp_path):
    conn = db.connect(tmp_path / "s.sqlite")
    db.set_meta(conn, "df_free", "123")
    assert db.get_meta(conn, "df_free") == "123"
    db.insert_entry(conn, _entry("/a", 100, "dev-cache"))
    db.insert_entry(conn, _entry("/b", 300, "media"))
    db.insert_entry(conn, _entry("/c", 50, "dev-cache"))
    conn.commit()

    top = db.top_by_physical(conn, limit=2)
    assert [r["path"] for r in top] == ["/b", "/a"]

    top_dev = db.top_by_physical(conn, category="dev-cache")
    assert [r["path"] for r in top_dev] == ["/a", "/c"]

    totals = db.totals_by_category(conn)
    assert totals["dev-cache"] == 150
    assert totals["media"] == 300
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.db`).

- [ ] **Step 3: Implement `bin/dsh_lib/db.py`**

```python
"""SQLite snapshot storage."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS entries (
    path TEXT PRIMARY KEY,
    kind TEXT NOT NULL,          -- 'file' | 'dir'
    category TEXT NOT NULL,
    logical INTEGER NOT NULL,
    physical INTEGER NOT NULL,
    mtime REAL,
    atime REAL,
    dataless INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_physical ON entries(physical DESC);
CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path)))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    if cur.fetchone() is None:
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                     (str(SCHEMA_VERSION),))
        conn.commit()
    return conn


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))


def get_meta(conn, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def insert_entry(conn, entry: dict) -> None:
    conn.execute(
        "INSERT INTO entries(path, kind, category, logical, physical, mtime, "
        "atime, dataless) VALUES(:path, :kind, :category, :logical, :physical, "
        ":mtime, :atime, :dataless) "
        "ON CONFLICT(path) DO UPDATE SET "
        "kind=excluded.kind, category=excluded.category, logical=excluded.logical, "
        "physical=excluded.physical, mtime=excluded.mtime, atime=excluded.atime, "
        "dataless=excluded.dataless",
        entry,
    )


def top_by_physical(conn, limit: int = 50, category: str | None = None):
    if category:
        return conn.execute(
            "SELECT * FROM entries WHERE category=? ORDER BY physical DESC LIMIT ?",
            (category, limit)).fetchall()
    return conn.execute(
        "SELECT * FROM entries ORDER BY physical DESC LIMIT ?", (limit,)).fetchall()


def totals_by_category(conn) -> dict:
    rows = conn.execute(
        "SELECT category, SUM(physical) AS total FROM entries GROUP BY category"
    ).fetchall()
    return {r["category"]: int(r["total"]) for r in rows}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/dsh_lib/db.py tests/test_db.py
git commit -m "feat: sqlite snapshot schema and queries"
```

---

### Task 5: df reader

**Files:**
- Create: `bin/dsh_lib/dfree.py`
- Test: `tests/test_dfree.py`

**Interfaces:**
- Produces: `free_bytes(path: str = "/System/Volumes/Data") -> int` — parses
  `df -k <path>` output (4th column = available 1K-blocks) → bytes. Uses
  `subprocess.run`.

- [ ] **Step 1: Write the failing test**

`tests/test_dfree.py`:
```python
from unittest import mock
from dsh_lib import dfree

SAMPLE = (
    "Filesystem 1024-blocks      Used Available Capacity iused ifree %iused  Mounted on\n"
    "/dev/disk3s5 970662016 895000000  27000000      98%  9500000 260000000 3% /System/Volumes/Data\n"
)


def test_free_bytes_parses_available():
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(stdout=SAMPLE, returncode=0)
        assert dfree.free_bytes("/System/Volumes/Data") == 27000000 * 1024
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_dfree.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.dfree`).

- [ ] **Step 3: Implement `bin/dsh_lib/dfree.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_dfree.py -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/dsh_lib/dfree.py tests/test_dfree.py
git commit -m "feat: df free-space reader"
```

---

### Task 6: Scanner (`bin/scan.py`)

**Files:**
- Create: `bin/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `dsh_lib.paths`, `dsh_lib.sizes`, `dsh_lib.db`, `dsh_lib.dfree`.
- Produces:
  - `DEFAULT_EXCLUDES: set[str]` and `is_excluded(path, excludes) -> bool`.
  - `NO_DESCEND: tuple[str, ...]` (dir basenames to roll up but not descend, e.g. `node_modules`, `.git`).
  - `scan_tree(roots: list[str], conn, *, min_file_bytes=10*1024*1024, excludes=None) -> dict` — walks roots, inserts dir rollups (every dir) and files ≥ `min_file_bytes` physical; returns summary dict `{"totals": {...}, "entries": int}`.
  - `main(argv=None) -> int` — CLI: `scan.py [--roots ...] [--min-mib N] [--out PATH]`; writes snapshot + `summary.json`, records `df_free` meta, prints summary.

- [ ] **Step 1: Write the failing test**

`tests/test_scan.py`:
```python
import os
import json
import scan
from dsh_lib import db


def _make_tree(root):
    (root / "proj" / "node_modules" / "pkg").mkdir(parents=True)
    (root / "proj" / "node_modules" / "pkg" / "big.js").write_bytes(b"x" * (12 * 1024 * 1024))
    (root / "Downloads").mkdir()
    (root / "Downloads" / "small.txt").write_bytes(b"y" * 1024)  # below threshold
    (root / "Downloads" / "movie.mov").write_bytes(b"z" * (20 * 1024 * 1024))


def test_is_excluded():
    assert scan.is_excluded("/System/foo", scan.DEFAULT_EXCLUDES) is True
    assert scan.is_excluded("/Users/a/x", scan.DEFAULT_EXCLUDES) is False


def test_scan_records_rollups_and_large_files(tmp_path):
    _make_tree(tmp_path)
    conn = db.connect(tmp_path / "snap.sqlite")
    summary = scan.scan_tree([str(tmp_path)], conn, min_file_bytes=10 * 1024 * 1024,
                             excludes=set())
    conn.commit()

    paths = {r["path"]: r for r in conn.execute("SELECT * FROM entries").fetchall()}
    # node_modules recorded as a dir rollup, its inner big.js NOT individually listed
    nm = str(tmp_path / "proj" / "node_modules")
    assert nm in paths and paths[nm]["kind"] == "dir"
    assert str(tmp_path / "proj" / "node_modules" / "pkg" / "big.js") not in paths
    # large movie file individually recorded; small.txt not
    assert str(tmp_path / "Downloads" / "movie.mov") in paths
    assert str(tmp_path / "Downloads" / "small.txt") not in paths
    assert summary["entries"] >= 1


def test_main_writes_summary_json(tmp_path, monkeypatch, capsys):
    _make_tree(tmp_path)
    out = tmp_path / "snap.sqlite"
    monkeypatch.setattr(scan.dfree, "free_bytes", lambda *a, **k: 42)
    rc = scan.main(["--roots", str(tmp_path), "--min-mib", "10", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    summ = json.loads((out.parent / "summary.json").read_text())
    assert "totals" in summ and summ["df_free"] == 42
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_scan.py -q`
Expected: FAIL (`ModuleNotFoundError: scan`).

- [ ] **Step 3: Implement `bin/scan.py`**

```python
#!/usr/bin/env python3
"""Careful metadata-only disk scanner → SQLite snapshot."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dsh_lib import db, dfree, paths, sizes

DEFAULT_EXCLUDES = {
    "/System", "/Volumes", "/private/var", "/private/tmp", "/dev", "/net",
    "/.vol", "/cores",
}
NO_DESCEND = ("node_modules", ".git", "DerivedData", ".venv", "venv",
              "__pycache__", "target", ".gradle", ".cargo")


def is_excluded(path: str, excludes) -> bool:
    return any(path == e or path.startswith(e + "/") for e in excludes)


def _dir_footprint(entry_path: str):
    """Return (physical, logical, max_mtime) by walking a no-descend dir,
    metadata only."""
    phys = logi = 0
    latest = 0.0
    for dp, dn, fn in os.walk(entry_path, topdown=True):
        for name in fn:
            try:
                st = os.lstat(os.path.join(dp, name))
            except OSError:
                continue
            phys += sizes.physical_bytes(st)
            logi += sizes.logical_bytes(st)
            latest = max(latest, st.st_mtime)
    return phys, logi, latest


def scan_tree(roots, conn, *, min_file_bytes=10 * 1024 * 1024, excludes=None):
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    for root in roots:
        _scan_one(root, conn, min_file_bytes, excludes)
    totals = db.totals_by_category(conn)
    n = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
    return {"totals": totals, "entries": int(n)}


def _scan_one(root, conn, min_file_bytes, excludes):
    stack = [root]
    while stack:
        cur = stack.pop()
        if is_excluded(cur, excludes):
            continue
        try:
            with os.scandir(cur) as it:
                dir_phys = dir_logi = 0
                dir_latest = 0.0
                for de in it:
                    p = de.path
                    try:
                        st = de.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if de.is_symlink():
                        continue
                    if de.is_dir(follow_symlinks=False):
                        if de.name in NO_DESCEND:
                            phys, logi, latest = _dir_footprint(p)
                            db.insert_entry(conn, dict(
                                path=p, kind="dir",
                                category=sizes.classify(p),
                                logical=logi, physical=phys,
                                mtime=latest, atime=st.st_atime,
                                dataless=int(sizes.is_dataless(getattr(st, "st_flags", 0))),
                            ))
                            dir_phys += phys
                            dir_logi += logi
                        elif not is_excluded(p, excludes):
                            stack.append(p)
                    else:
                        phys = sizes.physical_bytes(st)
                        dir_phys += phys
                        dir_logi += sizes.logical_bytes(st)
                        dir_latest = max(dir_latest, st.st_mtime)
                        if phys >= min_file_bytes:
                            db.insert_entry(conn, dict(
                                path=p, kind="file",
                                category=sizes.classify(p),
                                logical=sizes.logical_bytes(st), physical=phys,
                                mtime=st.st_mtime, atime=st.st_atime,
                                dataless=int(sizes.is_dataless(getattr(st, "st_flags", 0))),
                            ))
        except OSError:
            continue


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scan disk usage → SQLite snapshot")
    ap.add_argument("--roots", nargs="+", default=[str(Path.home())])
    ap.add_argument("--min-mib", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    out = Path(args.out) if args.out else \
        paths.snapshots_dir() / "snapshot-latest.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(out)
    free = dfree.free_bytes()
    db.set_meta(conn, "df_free", str(free))
    db.set_meta(conn, "roots", json.dumps(args.roots))
    summary = scan_tree(args.roots, conn,
                        min_file_bytes=args.min_mib * 1024 * 1024)
    conn.commit()
    payload = {"df_free": free, "totals": summary["totals"],
               "entries": summary["entries"]}
    (out.parent / "summary.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_scan.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/scan.py tests/test_scan.py
git commit -m "feat: metadata-only scanner writing sqlite snapshot"
```

---

### Task 7: Snapshot diff (`bin/diff.py`)

**Files:**
- Create: `bin/diff.py`
- Test: `tests/test_diff.py`

**Interfaces:**
- Consumes: `dsh_lib.db`.
- Produces:
  - `diff_snapshots(old_conn, new_conn) -> dict` with keys `grew`, `shrank`,
    `appeared`, `disappeared` — each a list of `{"path", "old", "new", "delta"}`
    (physical bytes), sorted by `abs(delta)` desc.
  - `main(argv=None) -> int` — CLI `diff.py OLD.sqlite NEW.sqlite`, prints JSON.

- [ ] **Step 1: Write the failing test**

`tests/test_diff.py`:
```python
import diff
from dsh_lib import db


def _seed(path, rows):
    conn = db.connect(path)
    for p, phys in rows:
        db.insert_entry(conn, dict(path=p, kind="file", category="other",
                                   logical=phys, physical=phys, mtime=1.0,
                                   atime=1.0, dataless=0))
    conn.commit()
    return conn


def test_diff(tmp_path):
    old = _seed(tmp_path / "o.sqlite", [("/a", 100), ("/b", 500), ("/gone", 300)])
    new = _seed(tmp_path / "n.sqlite", [("/a", 400), ("/b", 200), ("/new", 250)])
    d = diff.diff_snapshots(old, new)
    assert {"path": "/a", "old": 100, "new": 400, "delta": 300} in d["grew"]
    assert {"path": "/b", "old": 500, "new": 200, "delta": -300} in d["shrank"]
    assert {"path": "/new", "old": 0, "new": 250, "delta": 250} in d["appeared"]
    assert {"path": "/gone", "old": 300, "new": 0, "delta": -300} in d["disappeared"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_diff.py -q`
Expected: FAIL (`ModuleNotFoundError: diff`).

- [ ] **Step 3: Implement `bin/diff.py`**

```python
#!/usr/bin/env python3
"""Diff two disk snapshots by physical footprint."""
from __future__ import annotations

import argparse
import json

from dsh_lib import db


def _physical_map(conn) -> dict:
    return {r["path"]: int(r["physical"])
            for r in conn.execute("SELECT path, physical FROM entries").fetchall()}


def diff_snapshots(old_conn, new_conn) -> dict:
    old = _physical_map(old_conn)
    new = _physical_map(new_conn)
    grew, shrank, appeared, disappeared = [], [], [], []
    for path in set(old) | set(new):
        o = old.get(path, 0)
        n = new.get(path, 0)
        if o and not n:
            disappeared.append({"path": path, "old": o, "new": 0, "delta": -o})
        elif n and not o:
            appeared.append({"path": path, "old": 0, "new": n, "delta": n})
        elif n > o:
            grew.append({"path": path, "old": o, "new": n, "delta": n - o})
        elif n < o:
            shrank.append({"path": path, "old": o, "new": n, "delta": n - o})
    for lst in (grew, shrank, appeared, disappeared):
        lst.sort(key=lambda e: abs(e["delta"]), reverse=True)
    return {"grew": grew, "shrank": shrank,
            "appeared": appeared, "disappeared": disappeared}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diff two snapshots")
    ap.add_argument("old")
    ap.add_argument("new")
    args = ap.parse_args(argv)
    d = diff_snapshots(db.connect(args.old), db.connect(args.new))
    print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_diff.py -q`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/diff.py tests/test_diff.py
git commit -m "feat: snapshot diff by physical footprint"
```

---

### Task 8: Trash abstraction (`bin/dsh_lib/trash.py`)

**Files:**
- Create: `bin/dsh_lib/trash.py`
- Test: `tests/test_trash.py`

**Interfaces:**
- Produces:
  - `class TrashResult(NamedTuple): path: str; ok: bool; method: str; error: str | None`
  - `to_trash(path: str, *, runner=subprocess.run) -> TrashResult` — tries
    Finder via `osascript`; on failure falls back to moving into `~/.Trash`.
    `runner` is injectable for tests.

- [ ] **Step 1: Write the failing test**

`tests/test_trash.py`:
```python
from unittest import mock
from dsh_lib import trash


def test_to_trash_uses_finder_first(tmp_path):
    f = tmp_path / "junk.bin"
    f.write_text("x")
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stderr=""))
    res = trash.to_trash(str(f), runner=runner)
    assert res.ok and res.method == "finder"
    runner.assert_called_once()
    assert runner.call_args.args[0][0] == "osascript"


def test_to_trash_falls_back_to_move(tmp_path, monkeypatch):
    f = tmp_path / "junk.bin"
    f.write_text("x")
    fake_trash = tmp_path / "Trash"
    fake_trash.mkdir()
    monkeypatch.setattr(trash, "_home_trash", lambda: fake_trash)

    def boom(*a, **k):
        raise RuntimeError("no finder")
    res = trash.to_trash(str(f), runner=boom)
    assert res.ok and res.method == "move"
    assert (fake_trash / "junk.bin").exists()
    assert not f.exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_trash.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.trash`).

- [ ] **Step 3: Implement `bin/dsh_lib/trash.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_trash.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/dsh_lib/trash.py tests/test_trash.py
git commit -m "feat: macOS Trash abstraction with move fallback"
```

---

### Task 9: Rules engine (`bin/dsh_lib/rules.py`)

**Files:**
- Create: `bin/dsh_lib/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: PyYAML.
- Produces:
  - `load_rules(path) -> list[dict]` — reads YAML, returns `rules` list (empty if
    file missing).
  - `match_action(path: str, rules: list[dict]) -> tuple[str, dict | None]` —
    returns `(action, rule)` where action ∈ `keep|auto-trash|ask`; first matching
    rule wins; `("ask", None)` if none match. Patterns use `~` expansion and
    `fnmatch` glob semantics.
  - `bump_applied(rules: list[dict], rule_id: str) -> None` — increments
    `times_applied` in-place.
  - `save_rules(path, rules) -> None` — writes YAML `{"rules": rules}`.

- [ ] **Step 1: Write the failing test**

`tests/test_rules.py`:
```python
import os
from dsh_lib import rules


RULESET = [
    {"id": "dd", "pattern": "~/Library/Developer/Xcode/DerivedData/*",
     "action": "auto-trash", "times_applied": 0},
    {"id": "keepphotos", "pattern": "~/Dropbox/Photos/*", "action": "keep"},
]


def test_match_action(monkeypatch):
    home = os.path.expanduser("~")
    a, rule = rules.match_action(f"{home}/Library/Developer/Xcode/DerivedData/App", RULESET)
    assert a == "auto-trash" and rule["id"] == "dd"
    a, rule = rules.match_action(f"{home}/Dropbox/Photos/2020", RULESET)
    assert a == "keep"
    a, rule = rules.match_action(f"{home}/random", RULESET)
    assert a == "ask" and rule is None


def test_bump_and_roundtrip(tmp_path):
    import copy
    rs = copy.deepcopy(RULESET)
    rules.bump_applied(rs, "dd")
    assert rs[0]["times_applied"] == 1
    p = tmp_path / "rules.yaml"
    rules.save_rules(p, rs)
    loaded = rules.load_rules(p)
    assert loaded[0]["id"] == "dd" and loaded[0]["times_applied"] == 1


def test_load_missing_returns_empty(tmp_path):
    assert rules.load_rules(tmp_path / "nope.yaml") == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_rules.py -q`
Expected: FAIL (`ModuleNotFoundError: dsh_lib.rules`).

- [ ] **Step 3: Implement `bin/dsh_lib/rules.py`**

```python
"""Load and apply learned classification rules."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

import yaml

VALID_ACTIONS = {"keep", "auto-trash", "ask"}


def load_rules(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return list(data.get("rules", []))


def match_action(path: str, rules: list):
    for rule in rules:
        pattern = os.path.expanduser(str(rule.get("pattern", "")))
        if pattern and fnmatch.fnmatch(path, pattern):
            action = rule.get("action", "ask")
            return (action if action in VALID_ACTIONS else "ask"), rule
    return "ask", None


def bump_applied(rules: list, rule_id: str) -> None:
    for rule in rules:
        if rule.get("id") == rule_id:
            rule["times_applied"] = int(rule.get("times_applied", 0)) + 1
            return


def save_rules(path, rules: list) -> None:
    Path(path).write_text(yaml.safe_dump({"rules": rules}, sort_keys=False))
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_rules.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bin/dsh_lib/rules.py tests/test_rules.py
git commit -m "feat: rules engine load/match/persist"
```

---

### Task 10: Reclaim executor (`bin/reclaim.py`)

**Files:**
- Create: `bin/reclaim.py`
- Test: `tests/test_reclaim.py`

**Interfaces:**
- Consumes: `dsh_lib.trash`, `dsh_lib.paths`, `dsh_lib.dfree`.
- Produces:
  - `NEVER_TOUCH: tuple[str, ...]` — absolute prefixes that are always refused
    (`/System`, `/bin`, `/usr`, `/Volumes`, `/private/var`, `/Library`).
  - `is_safe(path: str) -> bool` — False if under any NEVER_TOUCH prefix or not
    absolute.
  - `run_plan(plan: list[dict], *, apply: bool, trash_fn=trash.to_trash, log_path=None, run_id="") -> dict`
    — each plan item `{"path", "reason", "rule_id"?}`; when `apply` is False,
    reports intended actions without acting; when True, trashes safe items and
    appends one JSON line per item to `log_path`. Returns
    `{"planned": [...], "trashed": [...], "refused": [...]}`.
  - `main(argv=None) -> int` — CLI `reclaim.py PLAN.json [--apply]`.

- [ ] **Step 1: Write the failing test**

`tests/test_reclaim.py`:
```python
import json
from unittest import mock
import reclaim


def test_is_safe():
    assert reclaim.is_safe("/System/x") is False
    assert reclaim.is_safe("/Library/x") is False
    assert reclaim.is_safe("relative/x") is False
    import os
    assert reclaim.is_safe(os.path.expanduser("~/Downloads/x")) is True


def test_dry_run_does_not_trash(tmp_path):
    plan = [{"path": str(tmp_path / "a"), "reason": "test"}]
    fn = mock.Mock()
    res = reclaim.run_plan(plan, apply=False, trash_fn=fn)
    fn.assert_not_called()
    assert res["planned"] and not res["trashed"]


def test_apply_trashes_and_logs(tmp_path):
    import os
    target = os.path.expanduser("~/dsh-test-junk")  # safe (under home)
    log = tmp_path / "decisions.jsonl"
    plan = [{"path": target, "reason": "test", "rule_id": "r1"},
            {"path": "/System/nope", "reason": "bad"}]
    fn = mock.Mock(return_value=mock.Mock(ok=True, method="finder", error=None))
    res = reclaim.run_plan(plan, apply=True, trash_fn=fn, log_path=log, run_id="R1")
    assert res["trashed"] == [target]
    assert res["refused"] == ["/System/nope"]
    fn.assert_called_once_with(target)
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert lines[0]["path"] == target and lines[0]["run_id"] == "R1"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_reclaim.py -q`
Expected: FAIL (`ModuleNotFoundError: reclaim`).

- [ ] **Step 3: Implement `bin/reclaim.py`**

```python
#!/usr/bin/env python3
"""Apply an approved reclaim plan → macOS Trash. Dry-run by default."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dsh_lib import dfree, paths, trash

NEVER_TOUCH = ("/System", "/bin", "/sbin", "/usr", "/Volumes",
               "/private/var", "/Library", "/Applications")


def is_safe(path: str) -> bool:
    if not path.startswith("/"):
        return False
    return not any(path == p or path.startswith(p + "/") for p in NEVER_TOUCH)


def _log(log_path, record) -> None:
    if not log_path:
        return
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def run_plan(plan, *, apply: bool, trash_fn=trash.to_trash,
             log_path=None, run_id="") -> dict:
    planned, trashed, refused = [], [], []
    for item in plan:
        path = item["path"]
        if not is_safe(path):
            refused.append(path)
            _log(log_path, {"run_id": run_id, "path": path,
                            "action": "refused", "reason": item.get("reason", ""),
                            "rule_id": item.get("rule_id")})
            continue
        planned.append(path)
        if not apply:
            continue
        res = trash_fn(path)
        if res.ok:
            trashed.append(path)
        _log(log_path, {"run_id": run_id, "path": path,
                        "action": "trashed" if res.ok else "failed",
                        "method": res.method, "error": res.error,
                        "reason": item.get("reason", ""),
                        "rule_id": item.get("rule_id")})
    return {"planned": planned, "trashed": trashed, "refused": refused}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply a reclaim plan → Trash")
    ap.add_argument("plan")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    before = dfree.free_bytes()
    res = run_plan(plan, apply=args.apply, log_path=str(paths.decisions_log()))
    after = dfree.free_bytes() if args.apply else before
    res["freed_bytes"] = after - before
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_reclaim.py -q`
Expected: 3 passed. (Note: `test_apply_trashes_and_logs` uses a mock trash_fn,
so nothing real is deleted; the `~/dsh-test-junk` path need not exist because
`is_safe` only checks the prefix and `trash_fn` is mocked.)

- [ ] **Step 5: Commit**

```bash
git add bin/reclaim.py tests/test_reclaim.py
git commit -m "feat: reclaim executor with never-touch guard and audit log"
```

---

### Task 11: Domain handlers

**Files:**
- Create: `handlers/__init__.py`
- Create: `handlers/base.py`
- Create: `handlers/homebrew.py`
- Create: `handlers/xcode.py`
- Create: `handlers/icloud.py`
- Create: `handlers/dropbox.py`
- Test: `tests/test_handlers.py`

**Interfaces:**
- Produces (in `handlers/base.py`):
  - `def run_cmd(cmd: list[str], runner=subprocess.run) -> tuple[int, str, str]`
    — returns `(returncode, stdout, stderr)`; never raises on non-zero.
- Produces (each handler module):
  - `NAME: str`, `available(runner=subprocess.run) -> bool`,
    `report(runner=subprocess.run) -> dict` with at least
    `{"handler", "reclaimable_bytes", "detail"}`.
  - `homebrew.report` parses `brew cleanup -n`.
  - `xcode.report` sums physical size of `~/Library/Developer/Xcode/DerivedData`
    and `.../iOS DeviceSupport` via `os.walk` (metadata only).
  - `icloud.evict(path, runner=subprocess.run)` wraps `brctl evict`.
  - `dropbox.report` sums local (physical>0) bytes under `~/Dropbox`; returns
    `experimental=True` and a manual-instructions string; never mutates.

- [ ] **Step 1: Write the failing test**

`tests/test_handlers.py`:
```python
from unittest import mock
from handlers import base, homebrew, xcode, icloud, dropbox


def test_run_cmd_no_raise():
    rc, out, err = base.run_cmd(["/bin/sh", "-c", "exit 3"])
    assert rc == 3


def test_homebrew_report_parses(tmp_path):
    sample = "Would remove: /Users/a/Library/Caches/Homebrew/foo (1.2GB)\n" \
             "==> This operation would free approximately 3.5GB of disk space.\n"
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout=sample, stderr=""))
    rep = homebrew.report(runner=runner)
    assert rep["handler"] == "homebrew"
    assert rep["reclaimable_bytes"] == int(3.5 * 1000 ** 3)


def test_xcode_report_sums(tmp_path, monkeypatch):
    dd = tmp_path / "DerivedData" / "App"
    dd.mkdir(parents=True)
    (dd / "big").write_bytes(b"x" * (5 * 1024 * 1024))
    monkeypatch.setattr(xcode, "_roots", lambda: [tmp_path / "DerivedData"])
    rep = xcode.report()
    assert rep["reclaimable_bytes"] >= 5 * 1024 * 1024


def test_icloud_evict_invokes_brctl():
    runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout="", stderr=""))
    ok = icloud.evict("/Users/a/Library/Mobile Documents/x", runner=runner)
    assert ok is True
    assert runner.call_args.args[0][:2] == ["brctl", "evict"]


def test_dropbox_report_is_nondestructive(tmp_path, monkeypatch):
    d = tmp_path / "Dropbox"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "local.bin").write_bytes(b"z" * (2 * 1024 * 1024))
    monkeypatch.setattr(dropbox, "_dropbox_root", lambda: d)
    rep = dropbox.report()
    assert rep["experimental"] is True
    assert rep["reclaimable_bytes"] >= 2 * 1024 * 1024
    assert "manual" in rep["detail"].lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_handlers.py -q`
Expected: FAIL (`ModuleNotFoundError: handlers`).

- [ ] **Step 3: Implement the handler modules**

`handlers/__init__.py`:
```python
"""Domain-specific disk-space handlers."""
```

`handlers/base.py`:
```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dsh_lib import sizes


def run_cmd(cmd, runner=subprocess.run):
    res = runner(cmd, capture_output=True, text=True)
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
```

`handlers/homebrew.py`:
```python
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
```

`handlers/xcode.py`:
```python
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
```

`handlers/icloud.py`:
```python
from __future__ import annotations

import subprocess

from handlers import base

NAME = "icloud"


def evict(path: str, runner=subprocess.run) -> bool:
    rc, _out, _err = base.run_cmd(["brctl", "evict", path], runner=runner)
    return rc == 0
```

`handlers/dropbox.py`:
```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_handlers.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add handlers tests/test_handlers.py
git commit -m "feat: domain handlers (homebrew, xcode, icloud, dropbox)"
```

---

### Task 12: Slash commands + README

**Files:**
- Create: `.claude/commands/scan.md`
- Create: `.claude/commands/reclaim.md`
- Create: `README.md`

**Interfaces:** Documentation/orchestration only — no automated tests. These
files tell Claude Code how to drive the scripts and run the interview.

- [ ] **Step 1: Write `.claude/commands/scan.md`**

```markdown
---
description: Scan disk usage into a fresh snapshot and summarize the biggest consumers
---

Run a metadata-only disk scan and report where space is going.

1. Ensure the data dir + templates exist:
   `python3 bin/scan.py --help >/dev/null` then run
   `python3 -c "from dsh_lib import paths; paths.bootstrap()"` from `bin/`'s parent
   (or rely on `/reclaim` which bootstraps).
2. Run the scan (home dir by default):
   `python3 bin/scan.py`
   Add `--roots ~/Library ~/Dropbox` etc. to narrow, `--min-mib N` to change the
   per-file threshold.
3. Read `summary.json` next to the snapshot and present:
   - total reclaimable by category (physical bytes),
   - top 30 consumers (`sqlite3 <snapshot> "SELECT path, physical, category,
     dataless FROM entries ORDER BY physical DESC LIMIT 30"`),
   - note any `dataless=1` items are ALREADY online-only (not reclaimable).
4. Do NOT delete anything in this command — scanning only.
```

- [ ] **Step 2: Write `.claude/commands/reclaim.md`**

```markdown
---
description: Full disk-space reclaim run — scan, learn, interview, and reclaim to Trash
---

You are Andrew's disk-space reasoning partner. Personal state lives in
`$DSH_DATA_DIR` (default `~/.local/share/disk-space-helper`) and must never be
committed. Work the lifecycle below. NEVER use `rm`; reclaim goes to Trash via
`bin/reclaim.py`. Only auto-trash categories Andrew has already approved (rules
with `action: auto-trash`).

## Lifecycle

1. **Bootstrap + scan.** From the repo root:
   `python3 -c "import sys; sys.path.insert(0,'bin'); from dsh_lib import paths; paths.bootstrap()"`
   then `python3 bin/scan.py`. If a previous snapshot exists, run `bin/diff.py`
   against it and summarize what grew.
2. **Load knowledge.** Read `knowledge/profile.md` and `knowledge/rules.yaml`
   from the data dir. Summarize known facts back to Andrew.
3. **Auto-classify.** For each top consumer, use `dsh_lib.rules.match_action`.
   Group into: auto-trash (approved), keep (skip), ask (needs interview).
4. **Quick wins.** Run applicable handlers (`handlers/homebrew.py`,
   `xcode.py`, `dropbox.py` report, `icloud.py`). Show reclaimable bytes.
   Build a plan JSON for approved auto-trash items and run
   `python3 bin/reclaim.py plan.json` (dry-run) → show → `--apply` on approval.
5. **Interview.** For the biggest `ask` items, ask ONE question at a time,
   multiple-choice + an "other / notes" option, about Andrew's actual data.
   After each answer:
   - append durable facts to `knowledge/profile.md`,
   - if a repeatable decision, add/update a rule in `knowledge/rules.yaml`
     (`action`, `rationale`, `learned_on`, `confidence`) via
     `dsh_lib.rules.save_rules`.
6. **Reason & propose.** Present a personalized plan for subjective items
   (dev-cache trimming, Dropbox/iCloud eviction, large/old media). For iCloud,
   offer `handlers/icloud.evict`. For Dropbox, present the report + manual
   steps (experimental — never auto-mutate).
7. **Execute** approved actions via `bin/reclaim.py --apply`. Everything is
   logged to `decisions.jsonl`.
8. **Report.** Write `reports/YYYY-MM-DD-run.md` in the data dir: reclaimed
   bytes (before/after df), decisions, new rules/facts, and follow-ups.

## Rules of engagement
- One question at a time during the interview.
- Never delete without an explicit yes for that batch (unless an approved
  auto-trash rule already covers it).
- Prefer Trash + online-only eviction over permanent deletion.
- Treat `dataless=1` entries as already reclaimed.
```

- [ ] **Step 3: Write `README.md`**

```markdown
# disk-space-helper

A personal disk-space reasoning system for macOS, driven by Claude Code.

Deterministic Python scripts scan, diff, and reclaim disk usage; Claude Code
reasons about the results, interviews you about your habits, and learns across
runs. It gets easier to use over time.

## Why it's different
- **Reasoning + memory**, not just a size chart: it remembers what you deleted
  and why, and auto-handles categories you've already approved.
- **Physical-footprint aware**: correctly treats Dropbox/iCloud online-only
  files as already reclaimed, and never hydrates them (metadata-only scan).
- **Safe**: everything goes to the macOS Trash; nothing auto-deletes until you
  approve that category once.

## Privacy / public-repo safety
No personal data lives in this repo. All snapshots, learned rules, profile
facts, decision logs, and reports live in a private data directory outside the
repo: `$DSH_DATA_DIR` (default `~/.local/share/disk-space-helper`). The repo
ships only `knowledge/*.example.*` templates.

## Requirements
macOS, Python 3.11+, PyYAML. Optional: Homebrew, Xcode, Docker for those
handlers.

## Usage (inside Claude Code)
- `/scan` — scan and summarize where space is going.
- `/reclaim` — full run: scan → learn → interview → reclaim to Trash → report.

## Manual usage
```bash
pip install -e .
python3 bin/scan.py                 # writes a snapshot + summary.json
python3 bin/diff.py OLD.sqlite NEW.sqlite
python3 bin/reclaim.py plan.json    # dry-run; add --apply to act
```

## Development
`pip install -e . pytest && pytest -q`
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/scan.md .claude/commands/reclaim.md README.md
git commit -m "docs: slash commands and README"
```

---

### Task 13: Publish public GitHub repo

**Files:** none (repo operations).

- [ ] **Step 1: Full test run**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Verify no personal data is tracked**

Run: `git ls-files | grep -Ev '^(bin/|handlers/|tests/|knowledge/.*\.example\.|\.claude/|docs/|README|pyproject|\.gitignore)' || echo "clean"`
Expected: `clean` (only generic code/templates tracked).

- [ ] **Step 3: Create the public repo and push**

```bash
gh repo create beveradb/disk-space-helper --public --source=. --remote=origin \
  --description "Personal disk-space reasoning system for macOS, driven by Claude Code" --push
```

- [ ] **Step 4: Verify**

Run: `gh repo view beveradb/disk-space-helper --json visibility,url -q '.visibility+" "+.url'`
Expected: `PUBLIC https://github.com/beveradb/disk-space-helper`

---

## Self-Review

**Spec coverage:**
- Physical-vs-logical + dataless → Task 3 (`sizes.py`), used in Task 6. ✓
- Data-dir outside repo + template bootstrap + public-repo safety → Task 2, Task 12 (README), Task 13 (verify no personal data). ✓
- SQLite snapshot + summary.json → Task 4, Task 6. ✓
- Diff → Task 7. ✓
- Trash (never rm) + dry-run + never-touch + audit log → Task 8, Task 10. ✓
- Rules engine + self-improvement (auto-trash only after approval) → Task 9, Task 12 (reclaim.md lifecycle). ✓
- Handlers (homebrew, xcode, icloud, dropbox) → Task 11. (docker/pkg-caches noted in spec as future handlers; homebrew/xcode/icloud/dropbox cover the primary levers — docker/pkgcaches can be added later following the same `report()` pattern.) ✓ (partial by design)
- Interview loop, one question at a time → Task 12 (`reclaim.md`). ✓
- Testing across scanner/rules/reclaim/diff/handlers/paths → Tasks 2–11. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `TrashResult` fields (`ok`, `method`, `error`) used
consistently in Task 8 and Task 10. `report()` dict keys (`handler`,
`reclaimable_bytes`, `detail`) consistent across handlers and tests. `run_plan`
return keys (`planned`, `trashed`, `refused`) match tests. ✓

**Note on scope:** `docker` and `pkgcaches` handlers from the spec are
deliberately deferred — they follow the exact `report()` pattern of Task 11 and
add no new architecture. If desired, add them as a follow-up task mirroring
`homebrew.py`.
