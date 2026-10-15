# Workspace instructions

This repository combines upstream source references with local AutoData research documents and a private blog.

- Read the nearest AGENTS.md before working inside an upstream repository. Preserve its instructions.
- Cloud tasks can inspect source and build/check the private blog. GPU simulation and training require a separately configured GPU server. Do not report static inspection as runtime validation.
- Keep upstream submodules at their recorded commits unless explicitly asked to update them. Make proposed changes in patches or in this repository's workspace-overlays directory unless the task authorizes editing upstream code.
- Run `npm --prefix private-blog run check` after blog changes; run its build first if sources changed.
- Do not publish the blog or change access control as a side effect of GitHub synchronization.
- Deliver research reports locally by default. Upload to Feishu or ChatGPT only when explicitly requested by the user; ask for a destination only when needed for that requested upload.
- Follow `docs/version-management.md` for branches, worktrees and commit boundaries. Run `bash scripts/cloud-check.sh` before committing workspace changes; use `--allow-uninitialized` only for intentionally absent top-level source checkouts.
- Preserve sealed `outputs/` versions and upstream local changes. Root `.gitignore` does not control files inside submodules; never stage their datasets through the parent repository.

## Automatic GitHub synchronization

- The user has authorized automatic commits and pushes after each task that changes this workspace and passes its required checks. Carry out synchronization without asking for confirmation again, unless the user overrides this instruction for a task.
- Review the diff and commit only changes belonging to the completed task, including intentional generated deliverables. Leave unrelated or unfinished work uncommitted, and keep credentials and machine-local configuration out of Git.
- For blog changes, build first when sources changed, then run `npm --prefix private-blog run check`. Run any other checks required by the affected files. Do not automatically commit or push a task whose required checks fail; report the failure.
- Commit with a descriptive message, then push to the current branch's configured upstream on `origin` (`https://github.com/eadstry/WorldSimReady-Home.git`). For a new branch, push that branch to `origin` with upstream tracking. In a detached worktree, create a `codex/` branch before committing. Do not merge other branches, force-push, rewrite history, or change upstream submodule commits as part of synchronization.
- If authentication, network access, repository permissions, or remote divergence prevents the push, preserve the local commit and report that GitHub synchronization is incomplete. Do not claim success until the push succeeds.
- Report the commit and synchronized branch at task completion. This is a task-completion workflow, not a background file watcher or scheduled service; other machines and cloud tasks must fetch the pushed commits to receive them.

