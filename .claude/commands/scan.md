---
description: Scan disk usage into a fresh snapshot and summarize the biggest consumers
---

Run a metadata-only disk scan and report where space is going.

1. Ensure the data dir + templates exist (run from the repo root):
   `PYTHONPATH=bin:. python3 -c "from dsh_lib import paths; paths.bootstrap()"`
   (or rely on `/reclaim`, which bootstraps too).
2. Run the scan (home dir by default):
   `python3 bin/scan.py`
   Add `--roots ~/Library ~/Dropbox` etc. to narrow, `--min-mib N` to change the
   per-file threshold, `--dir-min-mib N` for the directory-rollup threshold, and
   `--out PATH` to control where the snapshot is written (defaults under
   `$DSH_DATA_DIR/snapshots/`).
3. Read `summary.json` (written next to the snapshot) and present:
   - `totals` — EXACT per-category physical-byte totals,
   - `df_free` and `total_physical` for context,
   - top 30 consumers via
     `sqlite3 <snapshot> "SELECT path, physical, category, dataless FROM entries ORDER BY physical DESC LIMIT 30"`
     (rows are files above `--min-mib` and directories above `--dir-min-mib`,
     `kind` distinguishes them).
   - note any `dataless=1` items are ALREADY online-only (not reclaimable).
4. Do NOT delete anything in this command — scanning only.
