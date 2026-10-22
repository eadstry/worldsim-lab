# Workspace instructions

This repository combines upstream source references with local AutoData research documents.

- Read the nearest AGENTS.md before working inside an upstream repository. Preserve its instructions.
- Keep upstream submodules at their recorded commits unless explicitly asked to update them. Make proposed changes in patches or in this repository's workspace-overlays directory unless the task authorizes editing upstream code.
- Deliver research reports locally by default. Upload to Feishu or ChatGPT only when explicitly requested by the user; ask for a destination only when needed for that requested upload.
- Follow `docs/version-management.md` for branches, worktrees and commit boundaries. Run `bash scripts/cloud-check.sh` before committing workspace changes; use `--allow-uninitialized` only for intentionally absent top-level source checkouts.
- Preserve sealed `outputs/` versions and upstream local changes. Root `.gitignore` does not control files inside submodules; never stage their datasets through the parent repository.

## Documents and reports

- Put every document or report a task produces in `docs/`; keep the repository root, `runs/` and scratch worktrees free of prose. `outputs/` stays for sealed, versioned artifacts, not for notes.
- Name new documents `<topic>-<YYYYMMDD>[-r<NN>].<ext>`: a stable lowercase ASCII topic slug, the creation date, and a revision suffix only when a same-day document supersedes an earlier one. Reuse the slug of an existing problem instead of coining a near-duplicate, so related documents sort together in the order they were written; use `docs/<topic>/` for reference material shared by several documents.
- Register each new document in the index table in `docs/README.md` (and the topic index, when one exists) in the same change, with its creation date and its one-line purpose. Extend the entry for an existing problem instead of adding an alias.
- Leave superseded documents in place and add the newer dated file; do not rewrite an old report's conclusions in place.
- Run `python3 scripts/check-doc-links.py` after renaming or moving a document, and update every link you move.

- Maintain one editable source per document. Preserve existing sealed `outputs/` versions unchanged; their code references point to `workspace-overlays/`.
- This repository has no blog build or deployment pipeline. Documents are read on GitHub or opened offline.

## Automatic version submission and review

- Follow `docs/automatic-version-review.md` and `config/version-policy.json`. Start new implementation tasks from the updated integration branch using `scripts/review-workspace.py start`; read-only historical comparisons may retain their old revision.
- The user authorizes automatic task-scoped commits and pushes after review and required checks pass. An explicit request for local-only work, no commit or no push overrides synchronization. This runs at task completion, not as a background file watcher.
- Before submission, inspect the complete task diff for correctness, regressions, concurrency, data ownership, dependency provenance, test coverage and evidence limitations. Resolve high-severity findings first and record a concrete self-review note. Automated checks and an agent's self-review are not independent reviewer approval.
- Use explicit task paths with `scripts/review-workspace.py finish`, or stage explicitly and run `prepare` before committing. Required checks bind a receipt to the exact parent, branch and staged tree; changes after review require a new receipt. Preserve unrelated work in its original worktree.
- Do not bypass hooks, force-push, rewrite published history, directly submit to `main`/`release/*`, or merge branches as an automatic synchronization side effect. User-requested merges require review of the resulting tree and relevant checks; stable promotion uses a PR and separate approval.
- Never automatically update upstream pins, install simulation dependencies, upload research reports. GPU execution remains separately configured and scheduled. Missing dependencies or failed checks stop automatic submission; report what remains blocked.
- Push only the reviewed current branch to the configured workspace `origin`. A failed push must leave the local commit intact and be reported as incomplete synchronization. Report the commit, branch and actual validation scope at completion.

## Shared host validation

- Submit GPU simulation, training and resource-intensive validation through `scripts/task-queue.py` with the same host-local queue directory. Read `docs/task-queue.md`; keep queued/running code unchanged and preserve independent outputs. Ordinary host unit tests do not require GPU resources.
