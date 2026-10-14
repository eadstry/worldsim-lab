# Workspace instructions

This repository combines upstream source references with local AutoData research documents and a private blog.

- Read the nearest AGENTS.md before working inside an upstream repository. Preserve its instructions.
- Cloud tasks can inspect source and build/check the private blog. GPU simulation and training require a separately configured GPU server. Do not report static inspection as runtime validation.
- Keep upstream submodules at their recorded commits unless explicitly asked to update them. Make proposed changes in patches or in this repository's workspace-overlays directory unless the task authorizes editing upstream code.
- Run `npm --prefix private-blog run check` after blog changes; run its build first if sources changed.
- Do not publish the blog or change access control as a side effect of GitHub synchronization.
- On a shared host, submit GPU simulation, training and resource-intensive validation through `scripts/task-queue.py` using the same host-local queue directory across worktrees. Read `docs/task-queue.md`; wait for existing unmanaged GPU tasks to finish before starting the queue. Keep each task's outputs separate and its worktree unchanged while queued or running.

## Automatic GitHub synchronization

- The user has authorized automatic commits and pushes after each task that changes this workspace and passes its required checks. Carry out synchronization without asking for confirmation again, unless the user overrides this instruction for a task.
- Review the diff and commit only changes belonging to the completed task, including intentional generated deliverables. Leave unrelated or unfinished work uncommitted, and keep credentials and machine-local configuration out of Git.
- For blog changes, build first when sources changed, then run `npm --prefix private-blog run check`. Run any other checks required by the affected files. Do not automatically commit or push a task whose required checks fail; report the failure.
- Commit with a descriptive message, then push to the current branch's configured upstream on `origin` (`https://github.com/eadstry/WorldSimReady-Home.git`). For a new branch, push that branch to `origin` with upstream tracking. In a detached worktree, create a `codex/` branch before committing. Do not merge other branches, force-push, rewrite history, or change upstream submodule commits as part of synchronization.
- If authentication, network access, repository permissions, or remote divergence prevents the push, preserve the local commit and report that GitHub synchronization is incomplete. Do not claim success until the push succeeds.
- Report the commit and synchronized branch at task completion. This is a task-completion workflow, not a background file watcher or scheduled service; other machines and cloud tasks must fetch the pushed commits to receive them.

<!-- research-dual-delivery:start -->
## Research dual delivery
For reusable research reports, reproduction plans, data reviews, experiment comparisons, HTML dashboards and weekly reports, read `skills/research-dual-delivery/SKILL.md` first. Package a consistent version, deliver to the user's authorized Feishu and ChatGPT destinations, and record each destination independently. Missing destinations or upload capabilities do not prevent local package preparation. Short chats and intermediate files do not require packaging. Keep machine paths, destinations and authentication in machine-local configuration. This rule does not authorize messaging, automations or public sharing. Current user instructions take precedence.
<!-- research-dual-delivery:end -->
