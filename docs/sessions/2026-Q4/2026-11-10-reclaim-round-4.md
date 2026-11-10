# disk-space-helper — reclaim round 4 — 2026-11-10

**Project:** disk-space-helper   **Branch/commit:** main @ 6b9d567 (no code changes)   **Status:** done (reclaim complete; tool bugs found, not yet fixed)

## Summary
Ran `/reclaim`. Free space went from **38 GiB to 160 GiB** (measured by `df` after emptying the
Trash, about +122 GiB). No repo code changed. All personal detail (rules, profile, decisions,
run report) is in `$DSH_DATA_DIR`. The full private report is
`$DSH_DATA_DIR/reports/2026-11-10-run.md`. While doing this, I found the root cause of the
"stale scan data" open thread from round 3 (see the first item under Learnings).

## What changed (on Andrew's Mac, not in the repo)
- **Approved auto-trash rules (15.8 GB):** uv (2 in-use `archive-v0` envs skipped via `lsof`),
  npm, pip, go-build, and old Pulumi plugin versions.
- **iOS (52.5 GB):** all of Xcode DerivedData, plus simulator app-install staging under
  `CoreSimulator/Devices/*/data/Containers/Data/InternalDaemon/*/tmp/Attachments`. One simulator
  alone had about 19 GB of staging copies. The simulators and their installed apps were left intact.
- **Docker in Colima (about 22 GB real):** containers were running, so I didn't delete the VM.
  Ran `docker image prune -a` + `docker builder prune -a` + `colima ssh -- sudo fstrim -av`.
  The host datadisk shrank from 29 to 7 GB.
- **Two merged worktrees** trashed + `git worktree prune` (about 14 GB by `du`).
- **Android (16.7 GB):** `~/.gradle/caches` and one NDK version unused since January.
- **pnpm store + Go module cache (11.3 GB).** Only `~/Library/pnpm/store` was trashed; the
  `bin`, `global` and `package-manager-store` dirs next to it were kept.
- **Installer DMGs in Downloads (0.9 GB).** DMGs still mounted (per `hdiutil info`) were skipped.
- **Dropbox online-only:** 60 SMS-backup XML files (17 GB → 5 MB local) via
  `$DSH_DATA_DIR/scripts/online_only.applescript`. Only files that the consuming project has
  already merged *and* that are older than 24 h (Andrew's condition).
- **Emptied the Trash** (about 104 GB) with Andrew's explicit yes.
- **Knowledge base:** new auto-trash rules for `sim-install-staging`, `gradle-caches`,
  `pnpm-store` and `go-mod-cache`. `xcode-derived-data` changed from ask to auto-trash (only when
  no build is running). New ask rule `android-ndk-old`. A Dropbox keep-local rule was replaced by
  a "merged + >24 h → online-only" rule. The colima rule gained the prune + fstrim path.
  `times_applied` was bumped on the rules used.
- `decisions.jsonl` got manual entries for the actions `reclaim.py` doesn't log: the Docker prune,
  the online-only run and the Trash empty.

## Decisions & rationale
- **Colima VM not deleted, even though the `colima-orphan-datadisk` rule matched:** 2 long-lived
  containers were running. Pruning plus `fstrim` reclaimed most of the space and kept them up.
- **Detached-HEAD worktree treated as merged** only after confirming that every file its HEAD
  commit touched is byte-identical on `origin/main`. It also had no dirty files and no stashes.
- **The keep-local rule for SMS backups was retired** after reading the consuming project's
  docs: it merges each file once into an archive and never re-reads it. The archive's `files`
  list was checked before evicting anything.
- **Old Downloads (>60 days) skipped:** only 0.3 GB. Work load-test results were also kept
  because they're active work.

## Learnings / gotchas
- **`scan.py` bug:** it upserts into the existing `snapshot-latest.sqlite` and never deletes
  rows, so removed paths persist forever. That produced a phantom 85.6 GB `.Trash`, trashed
  worktrees still listed, and online-only Dropbox folders showing their old size. It's also why
  `diff.py` reported `disappeared: 0`, and it explains round 3's open thread #6. Until it's fixed,
  check that each path exists before acting on scan rows.
- **Hard links inflate sizes:** walking a tree and summing `st_blocks` counts hard-linked files
  more than once. The tool reported 26.6 GB for a node_modules-heavy worktree that `du` put at
  about 14 GB. Use `du -sk` for plan `physical` values or dedupe by `(st_dev, st_ino)`.
- **`gh pr list --head "$(git branch --show-current)"` on a detached HEAD** passes an empty
  branch name and returns an unrelated PR. Worktree safety checks need a detached-HEAD path.
- **The Colima datadisk only shrinks after `fstrim`** inside the VM. Pruning images alone leaves
  the sparse disk file the same size.
- **Simulator `InternalDaemon/*/tmp/Attachments`** collects copies of app bundles from
  `simctl install` (dev-client installs) and isn't cleaned up. It's a large, silent growth source
  for mobile workflows.
- **The Finder UI-scripting online-only approach hangs in long batches** (`AppleEvent timed out
  (-1712)`; even `count windows` hung). Fix: `killall Finder`, then run one file per `osascript`
  call under `timeout 60`, with a health check that relaunches Finder on failure. That ran 27/27 OK.
- Finder `empty trash` handled about 104 GB, including read-only Go module files and a few files
  held open by other processes, with no stall this time.
- zsh `nomatch` aborts an entire compound command when one glob has no match (for example
  `ls a/*.dmg b/*.zip`). Use `find` or `setopt nullglob` in survey one-liners.

## Open threads & next steps
- **Tool fixes (worktree + PR):**
  1. `scan.py`: write a fresh timestamped snapshot (copy to `-latest`) or clear `entries` at scan
     start, so deleted paths drop out and `diff.py` reports disappearances. Highest priority.
  2. Hard-link-aware sizing: dedupe inodes in the scanner rollups and in any plan sizing helper.
  3. Worktree check helper that handles a detached HEAD (compare touched files with the default
     branch) instead of `gh pr list --head`.
  4. Move the Dropbox online-only loop (one file per call + timeout + Finder relaunch) into
     `handlers/dropbox.py` as an opt-in action.
  5. Carry-overs from round 3: `lsof` in-use skip in `reclaim.py`, APFS clone detection, and
     path-segment-aware rule globbing instead of `fnmatch`.
- **Next reclaim run:** active work load-test results (about 13.5 GB across 3 copies); an
  old-repos clone folder (17 GB); a data-heavy hobby project (about 10 GB); Music (10 GB);
  transcription-app media cache (5 GB); Spotify cache (4.4 GB); aerial wallpaper videos (4.6 GB);
  photo working set (re-ask culling status).

## Related docs
- Previous: `docs/sessions/2026-Q4/2026-10-20-reclaim-round-3.md`
- Private run report: `$DSH_DATA_DIR/reports/2026-11-10-run.md`
- Spec/plan: `docs/superpowers/specs/2026-09-13-disk-space-helper-design.md`,
  `docs/superpowers/plans/2026-09-13-disk-space-helper.md`
