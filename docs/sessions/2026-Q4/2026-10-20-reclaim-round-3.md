# disk-space-helper — reclaim round 3 — 2026-10-20

**Project:** disk-space-helper   **Branch/commit:** main @ 30b61c5 (no code changes)   **Status:** done (reclaim run complete; tool follow-ups open)

## Summary
Ran `/reclaim` (session spanned 2026-10-19 → 10-20). Free space went **~88 GB → 188 GB**
(real, measured by `df` after emptying Trash). No repo code changed. Everything personal
(rules, profile, decisions, run report) lives in `$DSH_DATA_DIR`
(`~/.local/share/disk-space-helper`). Full private detail:
`$DSH_DATA_DIR/reports/2026-10-19-run.md`.

## What changed (on Andrew's Mac, not in the repo)
- **Approved auto-trash rules applied (23.8 GB):** uv, npm, pip, go-build caches, Chrome
  on-device model, old Pulumi plugin versions. uv: ran `lsof +D ~/.cache/uv` first and
  skipped the 3 in-use `archive-v0` envs (avoids the September empty-Trash stall).
- **Interview-approved trash:** a merged+clean git worktree (24.7 GB, + `git worktree prune`);
  42 `.terraform/` dirs under a work projects folder (29.7 GB) + created `~/.terraformrc`
  with `plugin_cache_dir`; 2 orphaned worktrees under `~/.config/superpowers/worktrees`
  whose parent repo was deleted (6.9 GB); 11 untracked rebuildable dirs (build/, Pods,
  node_modules, venvs) in an old-repos archive folder (6.1 GB).
- **Dropbox online-only automated for the first time** (~40 GB of folders) via Finder UI
  scripting (see Learnings). Script saved privately at
  `$DSH_DATA_DIR/scripts/online_only.applescript`.
- **WhatsApp orphaned media:** a chat folder held ~378k files that no message referenced
  (`ChatStorage.sqlite` `ZWAMEDIAITEM` paths: 46 referenced). Quit WhatsApp, moved
  unreferenced files to Trash, Andrew verified in-app, emptied. **Freed only ~0.3 GB** —
  they were APFS clones (see Learnings).
- Trash emptied three times with Andrew's explicit yes each time.
- Knowledge base: new rules `merged-clean-worktree` (ask), `terraform-dotdir` (auto-trash),
  two Dropbox keep-local rules, `whatsapp-orphan-media` (ask, low confidence); several
  `times_applied` bumps; many profile facts.

## Decisions & rationale
- **Colima datadisk (14.7 GB) NOT trashed** despite the approved `colima-orphan-datadisk`
  rule: it was attached to the live `default` profile and written 2 days earlier; the rule
  assumes 0 containers, which couldn't be verified (VM wouldn't start).
- **Dropbox folders read in place by another project kept local** — that project silently
  skips online-only placeholders, so eviction would cause silent data loss in its pipeline.
  Grep its `config.toml` before evicting anything in those areas.
- **Over-scope trash disclosed:** quoted 13.8 GB for `.terraform` (one repo) but trashed
  29.7 GB (all repos in the folder); told Andrew, offered restore from Trash; he kept it.
- **`models/` dirs are data, not build output** — excluded from "rebuildable" sweeps.

## Learnings / gotchas
- **Dropbox legacy Smart Sync CAN be driven from the CLI:** the Finder toolbar has an
  `AXMenuButton` with description "Dropbox"; `click` it via System Events, then
  `click menu item "Make online-only"`. Right-click `AXShowMenu` does **not** work (the
  context menu never appears in the AX tree). AppleScript gotcha: don't name a variable
  `target` inside a Finder `tell` (collides with a Finder property).
- **Evicted Dropbox data lands in `~/AB Dropbox/.dropbox.cache` first**, so `df` doesn't
  improve until Dropbox purges it (hours to days); free space then jumps.
- **APFS clones fool `st_blocks`/`du`:** hundreds of thousands of byte-identical files
  reported 22 GB "physical" but freed ~0.3 GB. Many duplicates ≠ real disk use. Verify with
  `df` before promising savings.
- **`fnmatch` `*` matches `/`** — `dsh_lib.rules.match_action` patterns like `~/Projects/*/*`
  match every descendant and (first-match-wins) shadow later rules. Keep patterns narrow.
- `df` free swung by 10–30 GB mid-run from parallel Claude sessions doing iOS/Android
  builds + Dropbox cache churn. Re-scan + `diff.py` instead of chasing transient drops.
- `colima start` fails with "failed to run attach disk colima, in use by instance colima"
  when a stale `~/.colima/_lima/_disks/colima/in_use_by` symlink is left behind.
- `scan.py` overwrites `snapshot-latest.sqlite`; copy it aside before scanning to diff.
- Dropbox folders named `*Unsynced` are still cloud-backed (thousands of placeholders) —
  "Unsynced" means "not offline by default", not selective-sync-excluded.

## Open threads & next steps
- **Tool follow-ups (worktree + PR):**
  1. Add opt-in Dropbox eviction to `handlers/dropbox.py` using the Finder-toolbar approach.
  2. Add an `lsof` in-use skip to `reclaim.py` (done ad hoc twice now).
  3. Detect APFS clones / heavy duplication in the scanner so "physical" isn't overstated.
  4. `rules.match_action`: document or switch from `fnmatch` to path-segment-aware globbing.
  5. `scan.py`: keep timestamped snapshots (not just `snapshot-latest`) so diffs are automatic.
  6. Investigate: first scan reported some paths (already-trashed ISO, conda pkgs) that no
     longer existed moments later — possible stale/partial data.
- **Next reclaim run:** Colima stale lock (fix + decide on 14.7 GB datadisk); Android SDK/AVD
  + Gradle + Xcode DerivedData (~36 GB, only when no mobile build is running); a large
  photo working set (re-ask culling status); remaining `models/` and dataset dirs in the
  old-repos archive; screen-recording folder.

## Related docs
- Previous: `docs/sessions/2026-Q3/2026-09-13-build-and-first-reclaim.md`
- Private run report: `$DSH_DATA_DIR/reports/2026-10-19-run.md`
- Spec/plan: `docs/superpowers/specs/2026-09-13-disk-space-helper-design.md`,
  `docs/superpowers/plans/2026-09-13-disk-space-helper.md`
