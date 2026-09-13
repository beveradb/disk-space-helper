# disk-space-helper — Design Spec

**Date:** 2026-09-13
**Status:** Approved (pending written-spec review)
**Owner:** Andrew (beveradb)

## Problem

Reclaiming disk space on a MacBook is a constant, manual struggle. GUI tools
(DaisyDisk, Disk Usage Analyzer) surface *where* space goes but leave all the
judgement to the user every time: no repeatable patterns, no reasoning, no
memory of what was deleted before or why. There is no way to accumulate
personal context so the system gets easier to use over time.

The data volume is currently ~98% full (~26 GiB free of 926 GiB). Quick-win
cache cleanup helps but is insufficient; the real target is **100–200 GiB**,
which requires tackling subjective, context-heavy decisions (dev-cache
efficiency, Dropbox online-only eviction, large/old media) informed by
Andrew-specific habits.

## Goals

- A **personal disk-space reasoning system**, not just a cache cleaner.
- **Deterministic scripts** do the factual work (scan, diff, move-to-Trash);
  **Claude Code** does the reasoning, interview, and learning. No API keys, no
  per-run cost.
- **Self-improving**: decisions and habits are written back into a knowledge
  base so future runs auto-handle settled categories and only ask about what's
  new or uncertain.
- **Repeatable**: each run diffs against the previous snapshot to focus on what
  changed.
- **Safe**: everything goes to macOS Trash (reversible); nothing is
  auto-deleted until Andrew has approved that category once.
- **Public-repo-safe**: the repository can be public with zero personal data,
  machine-specific learnings, or session data committed.

## Non-Goals

- No standalone LLM/API integration (Claude Code is the runtime).
- No GUI/TUI — it runs inside a Claude Code session via a slash command.
- Not a general cross-platform tool; macOS-only (uses macOS file flags, Trash,
  `brctl`, Homebrew, etc.).
- No fully-supported Dropbox eviction API (none exists publicly); that handler
  is best-effort + reporting + manual fallback.

## Key Technical Insight: physical vs logical size

The scanner records, for every item, both:

- **logical size** — `st_size` (what the file claims to be).
- **physical footprint** — `st_blocks × 512` (actual on-disk bytes).

Online-only Dropbox/iCloud files (and sparse files) have large logical size but
~0 physical footprint. Using physical footprint as the "reclaimable" metric:

1. Lets us scan such files from **metadata only** — never reading contents, so
   we never hydrate/download them.
2. Correctly treats already-online-only files as **already reclaimed**.
3. Reveals exactly how much **local** Dropbox/iCloud data could be evicted to
   online-only (physical > 0 inside those roots).

The scanner also detects the macOS **`dataless`** flag as a secondary signal
for cloud-provider online-only status.

## Architecture

Claude-Code-native: a repo of generic scripts + example templates, plus a
private out-of-repo data directory for all personal state.

```
disk-space-helper/                     (public repo — code + templates only)
├─ .claude/commands/
│  ├─ reclaim.md    # main entry: scan → auto-clean → interview → propose → reclaim → report
│  └─ scan.md       # scan-only quick look
├─ bin/
│  ├─ scan.py       # careful scanner → SQLite snapshot
│  ├─ diff.py       # compare two snapshots
│  ├─ reclaim.py    # apply approved plan → macOS Trash (dry-run capable)
│  └─ dsh_lib/      # shared: paths/data-dir resolution, size accounting, trash, sqlite helpers
├─ handlers/        # domain handlers (see below)
├─ knowledge/
│  ├─ profile.example.md
│  └─ rules.example.yaml
├─ tests/
├─ README.md
├─ .gitignore
└─ docs/superpowers/specs/…

$DSH_DATA_DIR (default ~/.local/share/disk-space-helper/)   (private, never committed)
├─ snapshots/snapshot-<ISO8601>.sqlite  (+ latest symlink)
├─ knowledge/
│  ├─ profile.md      # Andrew-specific facts & habits (self-improving narrative)
│  └─ rules.yaml      # learned classify rules with provenance
├─ decisions.jsonl    # append-only audit log
└─ reports/YYYY-MM-DD-run.md
```

**Data-dir resolution:** `DSH_DATA_DIR` env var if set, else
`$XDG_DATA_HOME/disk-space-helper`, else `~/.local/share/disk-space-helper`.
Created on first run. The repo ships `*.example.*` templates; on first run the
scripts copy templates into the data dir if the real files are absent.

## Components

### `bin/scan.py` — scanner
- Walks configured roots (home dir + selected system cache paths) with
  `os.scandir` for speed.
- **Records:** directory rollups (aggregate physical + logical size) for every
  directory, and individual files above a size threshold (default 10 MiB
  physical). Captures: path, logical size, physical size, mtime, atime,
  `dataless` flag, is-symlink, and a coarse `category` (dev-cache, downloads,
  media, app-support, cloud-dropbox, cloud-icloud, system-cache, other).
- **Never reads file contents** — metadata (`os.lstat`) only.
- **Excludes:** `/System`, `/Volumes/*` (external), `/private/var` system areas,
  `.Trash`, and anything on the read-only system volume. Does not follow
  symlinks across mounts.
- **Does not descend** into known bulk dirs (e.g. `node_modules`, `.git`) beyond
  recording their aggregate size — the point is the rollup, not per-file detail.
- Writes a **SQLite** snapshot (queryable via `sqlite3` for flexible analysis)
  plus a `summary.json` (top-N by physical size, totals per category, counts).
- Emits progress; bounded runtime target: a few minutes on ~9.5M inodes.
- Records `df` free space at scan time into the snapshot metadata.

### `bin/diff.py` — snapshot diff
- Given two snapshots (default: latest two), reports per-path and per-category
  deltas: what grew, shrank, appeared, disappeared. Feeds the "what changed
  since last run" step and lets us verify reclaim.

### `bin/reclaim.py` — reclaim executor
- Input: an approved **plan** (list of paths + intended action) as JSON.
- Default action: **move to macOS Trash** via `osascript`/Finder so items keep
  "Put Back"; fallback to moving into `~/.Trash` if Finder is unavailable.
- **Dry-run by default**: prints exactly what would happen; `--apply` performs it.
- Records `df` before/after and writes each item's outcome to `decisions.jsonl`.
- Refuses to act on the hard never-touch list (system paths, external volumes).

### `bin/dsh_lib/` — shared library
- Data-dir resolution, size accounting (physical/logical helpers), category
  classification, SQLite open/schema, trash abstraction (mockable for tests),
  `df` reader.

### `handlers/` — domain handlers
Each handler exposes: **report** (how much is reclaimable + which items) and,
where safe, **propose actions**. Handlers:
- **dropbox** — identify local (physical>0) Dropbox data; report evictable
  bytes; best-effort online-only eviction (experimental) + manual-instructions
  fallback. No destructive default.
- **icloud** — evict to online-only via supported `brctl evict <path>`.
- **xcode** — DerivedData, old iOS DeviceSupport, unavailable simulators
  (`xcrun simctl delete unavailable`), old archives.
- **docker** — `docker system df`; propose `docker system prune` scoped options.
- **homebrew** — `brew cleanup -n` report → `brew cleanup`.
- **pkg-caches** — npm/pnpm/yarn/pip/cargo cache report + clean commands.

Handlers wrap external commands behind functions so tests can mock them.

## Run Lifecycle (`/reclaim`)

1. **Scan** → new SQLite snapshot; **diff** vs previous.
2. **Auto-classify** snapshot through `rules.yaml`: `auto-trash` rules queue
   items for reclaim; `keep` rules filter items out; remainder is candidate for
   the interview.
3. **Quick wins** — show a summary of known-safe categories, then reclaim them
   to Trash (auto-tier for already-approved rules).
4. **Interview** — for the biggest/most-uncertain uncovered consumers, ask
   **one question at a time, multi-choice + "other/notes"**, about the real
   scanned data. Capture answers into `profile.md` / `rules.yaml`.
5. **Reason & propose** — a personalized plan for the tough/subjective items
   (dev-cache efficiency, Dropbox/iCloud eviction, large/old media), using
   handlers where they apply.
6. **Execute** approved actions (Trash or handler-specific). Log everything to
   `decisions.jsonl`.
7. **Report** — reclaimed bytes (verified via before/after `df`), decisions,
   and follow-ups → `reports/YYYY-MM-DD-run.md`.

## Self-Improvement Model

- A category becomes **auto-trash only after Andrew approves it once** in an
  interview; that approval writes a rule to `rules.yaml` with rationale,
  `learned_on`, and `times_applied` (incremented each run it fires).
- `profile.md` accumulates durable Andrew-facts (e.g. "keeps Xcode
  DeviceSupport for last 2 iOS versions only"; "Dropbox `/Photos` is archive —
  keep online-only").
- `decisions.jsonl` is the full audit trail and raw material for spotting
  patterns.
- The diff step means each run focuses on **what changed**, not settled ground.

### `rules.yaml` shape (example)
```yaml
rules:
  - id: xcode-derived-data
    pattern: "~/Library/Developer/Xcode/DerivedData/*"
    action: auto-trash        # keep | auto-trash | ask
    confidence: high
    rationale: "Regenerated on next build; safe to remove."
    learned_on: 2026-09-13
    times_applied: 0
```

## Safety & Error Handling

- **Trash, never `rm`** by default.
- **First-time = always confirm**; auto-tier only for already-approved rules.
- **Hard never-touch list**: system paths, external volumes, running-app live
  data, anything flagged `keep`.
- Scanner reads **metadata only** → never hydrates online-only files.
- Permission/unreadable errors are skipped and logged, not fatal.
- Disk-free measured before & after to verify actual reclaim.
- Dropbox eviction is best-effort/experimental with a safe manual fallback.

## Public-Repo Safety

- **No personal data in the repo.** All personal state (real profile, rules,
  decisions, snapshots, reports) lives in `$DSH_DATA_DIR` outside the repo.
- Repo ships `knowledge/*.example.*` templates only.
- `.gitignore` blocks `snapshots/`, `reports/`, `knowledge/profile.md`,
  `knowledge/rules.yaml`, `*.sqlite`, `decisions.jsonl`, and any stray data-dir
  paths as defense-in-depth.
- README documents the data-dir separation so contributors understand it.

## Testing

- **Scanner**: fixture tree incl. a simulated sparse/dataless file; assert
  physical-vs-logical accounting, threshold behavior, exclusions, category
  tagging.
- **Rules engine**: given snapshot + `rules.yaml`, assert correct
  classification (auto-trash / keep / ask).
- **Reclaim engine**: dry-run produces the correct plan; trash operation tested
  in a temp dir with the trash abstraction mocked; never-touch list enforced.
- **Diff**: two snapshots → correct growth/shrink/appear/disappear report.
- **Handlers**: list/report logic unit-tested with external commands mocked.
- **Data-dir resolution**: env/XDG/default precedence + template bootstrap.

## Repo & Delivery

- New **public** GitHub repo `beveradb/disk-space-helper` (gh authed as
  beveradb, `repo` scope confirmed).
- Language: **Python 3** (3.14 available) for scanner/diff/reclaim/handlers;
  stdlib-first (`os`, `sqlite3`, `json`), PyYAML for rules. Node available but
  not required.
- macOS-only.

## Open Questions / Risks

- **Dropbox online-only automation**: no clean public API on macOS; needs
  research at implementation time. Mitigation: reliable reporting + experimental
  attempt + manual instructions; never destructive.
- **Scan performance** at ~9.5M inodes: mitigate with `os.scandir`, size
  thresholds for per-file records, and not descending into bulk dirs.
- **Trash of very large items**: Finder Trash on huge dirs can be slow; report
  progress and allow batching.
