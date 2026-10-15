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

## Automatic version submission and review

- Follow `docs/automatic-version-review.md` and `config/version-policy.json`. Start new implementation tasks from the updated integration branch using `scripts/review-workspace.py start`; read-only historical comparisons may retain their old revision.
- The user authorizes automatic task-scoped commits and pushes after review and required checks pass. An explicit request for local-only work, no commit or no push overrides synchronization. This runs at task completion, not as a background file watcher.
- Before submission, inspect the complete task diff for correctness, regressions, concurrency, data ownership, dependency provenance, test coverage and evidence limitations. Resolve high-severity findings first and record a concrete self-review note. Automated checks and an agent's self-review are not independent reviewer approval.
- Use explicit task paths with `scripts/review-workspace.py finish`, or stage explicitly and run `prepare` before committing. Required checks bind a receipt to the exact parent, branch and staged tree; changes after review require a new receipt. Preserve unrelated work in its original worktree.
- Do not bypass hooks, force-push, rewrite published history, directly submit to `main`/`release/*`, or merge branches as an automatic synchronization side effect. User-requested merges require review of the resulting tree and relevant checks; stable promotion uses a PR and separate approval.
- Never automatically update upstream pins, install simulation dependencies, publish the blog or upload research reports. GPU execution remains separately configured and scheduled. Missing dependencies or failed checks stop automatic submission; report what remains blocked.
- Push only the reviewed current branch to the configured workspace `origin`. A failed push must leave the local commit intact and be reported as incomplete synchronization. Report the commit, branch and actual validation scope at completion.

## Shared host validation

- Submit GPU simulation, training and resource-intensive validation through `scripts/task-queue.py` with the same host-local queue directory. Read `docs/task-queue.md`; keep queued/running code unchanged and preserve independent outputs. Ordinary host unit tests do not require GPU resources.
