# Workspace instructions

This repository combines upstream source references with local AutoData research documents and a private blog.

- Read the nearest AGENTS.md before working inside an upstream repository. Preserve its instructions.
- Cloud tasks can inspect source and build/check the private blog. GPU simulation and training require a separately configured GPU server. Do not report static inspection as runtime validation.
- Keep upstream submodules at their recorded commits unless explicitly asked to update them. Make proposed changes in patches or in this repository's workspace-overlays directory unless the task authorizes editing upstream code.
- Run `npm --prefix private-blog run check` after blog changes; run its build first if sources changed.
- Do not publish the blog or change access control as a side effect of GitHub synchronization.
- Follow `docs/version-management.md` for branches, worktrees and commit boundaries. Run `bash scripts/cloud-check.sh` before committing workspace changes; use `--allow-uninitialized` only for intentionally absent top-level source checkouts.
- Preserve sealed `outputs/` versions and upstream local changes. Root `.gitignore` does not control files inside submodules; never stage their datasets through the parent repository.
