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
macOS, Python 3.11+, PyYAML. Optional, for the bundled handlers: Homebrew
(cache cleanup), Xcode (DerivedData / DeviceSupport), Dropbox and/or iCloud
Drive (online-only eviction reporting).

## Usage (inside Claude Code)
- `/scan` — scan and summarize where space is going.
- `/reclaim` — full run: scan → learn → interview → reclaim to Trash → report.

## Manual usage
macOS's system Python is "externally managed" (PEP 668), so create a
virtualenv first:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 bin/scan.py                 # writes a snapshot + summary.json
python3 bin/diff.py OLD.sqlite NEW.sqlite
python3 bin/reclaim.py plan.json    # dry-run; add --apply to act
```

## Development
```bash
source .venv/bin/activate
pip install -e . pytest && pytest -q
```
