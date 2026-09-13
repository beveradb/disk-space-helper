# disk-space-helper — build & first reclaim — 2026-09-13

**Project:** disk-space-helper   **Branch/commit:** main @ acbbaf4   **Status:** done (v1 shipped; reclaim round 1 complete)

## Summary
Built `disk-space-helper` from scratch — a Claude-Code-driven personal disk-space
reasoning system for macOS — then ran it against Andrew's real disk and reclaimed
**~140 GB** (free space 30.8 GB → 170.6 GB). The repo is public at
https://github.com/beveradb/disk-space-helper. Work went brainstorm → spec → plan →
13 TDD tasks (+review-driven fixes), all committed to `main` (greenfield, with the
user's consent) and pushed.

## What changed

### The tool (shipped, public repo)
Deterministic Python does the factual work; Claude does reasoning/interview/learning.
- `bin/scan.py` — metadata-only scanner → SQLite snapshot. Records **physical** footprint
  (`st_blocks*512`) vs **logical** (`st_size`) so cloud online-only files read as ~0 and
  are never hydrated. Recursive dir rollups + **exact per-file category totals** in `meta`
  (so small-file dirs are visible and totals never double-count). Fault-tolerant iteration;
  excludes `~/Library/CloudStorage`.
- `bin/diff.py` — snapshot-to-snapshot deltas by physical footprint.
- `bin/reclaim.py` — plan JSON → macOS **Trash (never rm)**; dry-run default, `--apply` to act;
  case-insensitive + normpath `NEVER_TOUCH` guard; audit log to `decisions.jsonl`; reports
  `trashed_bytes` (footprint moved) + `df_free_before/after`.
- `bin/dsh_lib/` — paths (data-dir resolution + template bootstrap), sizes (physical/dataless/
  classify), db (sqlite schema/queries; `totals_by_category` reads exact meta), dfree, trash
  (Finder AppleScript w/ backslash-safe escaping → `~/.Trash` fallback), rules (YAML load/match/
  persist, first-match-wins).
- `handlers/` — homebrew, xcode, icloud (`brctl evict`), dropbox (report-only); uniform
  `available()`/`report()`; `run_cmd` degrades on missing binary.
- `.claude/commands/{scan,reclaim}.md` — orchestration; `README.md`.
- 38 tests passing. **All personal state lives in `$DSH_DATA_DIR` (`~/.local/share/disk-space-helper`)** —
  repo ships only `*.example.*` templates; verified nothing personal is tracked.

### The reclaim run (external state changed on Andrew's Mac)
- Scanned `$HOME`: 741 GB across 104,258 entries; 30.8 GB free at start.
- Moved to Trash then emptied: uv cache (35), npm (25), pip (4), HuggingFace (12), Claude VM
  bundle (10), Android AVD+SDK (14), Parallels Debian VM (6.5), orphaned Colima datadisk (55).
- Permanent: `brew cleanup` (0.6 GB); `colima delete` (0 containers) — note it left a 55 GB
  orphaned datadisk that we then trashed.
- Emptying the Trash stalled on `~/.cache/uv` because live `uvx` MCP servers (other Claude
  sessions) run interpreters out of it. Resolved by selectively deleting the **1,101 not-in-use**
  uv envs and keeping in-use ones (Python prune; open-file unlink is safe on macOS).
- **Final: 170.6 GB free (~140 GB reclaimed).** Run report:
  `~/.local/share/disk-space-helper/reports/2026-09-13-run.md`.

### Knowledge base written (self-improvement)
- `rules.yaml`: auto-trash uv/npm/pip/huggingface caches; keep ollama-models, parallels-win11.
- `profile.md`: keep Ollama (offline use); Dropbox root is `~/AB Dropbox` (not `~/Dropbox`) with
  `*Unsynced`/`MediaUnsynced`/`WorkUnsynced` folders that may be **local-only** (confirm before
  evicting/deleting); CloudStorage mounts hang scans.

## Decisions & rationale
- **Claude-Code-native, not a standalone LLM CLI** — no API keys/cost; the knowledge base gives
  cross-run memory and self-improvement.
- **Trash + tiered auto** — reversible by default; a category only auto-trashes after Andrew
  approves it once (writes a rule).
- **Committed directly to `main` of a fresh repo** — greenfield, with explicit user consent (no
  worktree/PR flow for the initial build).
- **Fixed the "every dir" scanner gap mid-build (Task 6b)** rather than ship a scanner blind to
  small-file directories — core to the "see all disk usage" goal.
- **Kept in-use uv envs instead of killing MCP servers** — Andrew has other sessions open.

## Learnings / gotchas
- Iterating `os.scandir` can hang/timeout on network/cloud file-provider mounts (MacDroid,
  CloudStorage); the initial-`scandir` try/except doesn't cover iteration — must guard the loop.
- macOS default APFS is case-insensitive → `NEVER_TOUCH` needs case-folded compare (found in review).
- Finder AppleScript path escaping must escape `\` before `"` (injection/robustness; found in review).
- `df` free space doesn't move until the Trash is emptied (files stay on the same volume) — report
  `trashed_bytes`, not a df delta.
- Emptying Trash stalls on files held open by running processes (uv/uvx interpreters); unlinking
  open files is safe (space frees on process exit), and per-subdir pruning works around it.
- `colima delete` can leave the datadisk orphaned under `~/.colima`.

## Open threads & next steps
- **Tool follow-up:** add an `lsof` in-use check (or a "prune not-in-use subdirs" mode) to
  `reclaim.py` before trashing cache dirs — this session proved it's needed.
- **Reclaim round 2 (best after a Claude restart** so the last ~uv env clears and a fresh scan
  reflects freed space): AB Dropbox online-only (~46 GB; respect `*Unsynced` = possibly local-only),
  miniforge3 (~27 GB conda envs), Downloads + large media (~15 GB), QuiverPhotos (~33 GB, confirm
  backup first).
- **Classifier refinement:** lots landed in `other` (VMs/model caches); `~/AB Dropbox` wasn't tagged
  `cloud-dropbox` (folder name has a space, not literal `/Dropbox/`).

## Related docs
- Spec: `docs/superpowers/specs/2026-09-13-disk-space-helper-design.md`
- Plan: `docs/superpowers/plans/2026-09-13-disk-space-helper.md`
- Run report (private, outside repo): `~/.local/share/disk-space-helper/reports/2026-09-13-run.md`
