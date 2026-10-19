# Independent framework development checkouts

This directory is local and ignored by the workspace Git repository. The top-level `AutoData/`, `IsaacLab-Arena/`, and `RLinf/` integration references remain governed by `.gitmodules` and `upstream-lock.json`.

- `AutoData/` is on `codex/openarm-development`, based on the previous working commit `945806e`. Its modified and untracked files were copied from the integration checkout and verified against the recovery snapshot.
- `IsaacLab-Arena/` is on `eadstry/feature/arena-development`, based on the root pinned commit `9886659`.
- `AutoData-Arena/` is on `eadstry/feature/autodata-arena-development`, based on the distinct Arena commit `8b82dca` used by the AutoData branch.
- `AutoData-Arena-IsaacLab/` is on `eadstry/feature/autodata-isaaclab-development`, based on commit `ffff603e`; its two modified setup files were restored from the snapshot.
- `AutoData-GR00T/` is on `codex/autodata-gr00t-development`, based on commit `e29d8fc`. Its nested dependency changes are documented in the snapshot manifest; those large dependency checkouts remain uninitialized here. `AutoData-Arena/` also leaves its IsaacLab and GR00T submodule directories uninitialized, so Git reports those gitlinks as absent until initialized. The nested Arena, IsaacLab and GR00T working directories use separate branches and indexes, with Git object alternates pointing to the original local repositories because some promised objects are not available offline. Keep the original checkouts until those commits are safely published; run `git repack -a` in a development clone later if a standalone object store is needed.
- `RLinf/` awaits initialization because no local source checkout is present.

Make and commit framework changes in these directories. For integration, publish commits to an accessible remote, validate the complete dependency combination, then update the root submodule pointer and matching `upstream-lock.json` entry together. Keep the recovery snapshot local; it includes large runtime data and logs.
