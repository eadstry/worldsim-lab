---
name: research-dual-delivery
description: Package research deliverables for Feishu and ChatGPT with shared versions, evidence links and independently verified delivery states. Use for research reports, data reviews, experiment comparisons and workflow pages intended for reuse or collaboration.
---

# Research dual delivery

Apply the user's standing preference to reusable research deliverables: one versioned source package, delivered to Feishu and ChatGPT. Applies equally on macOS and Linux servers. Inline answers, scratch work and raw bulk data do not automatically require delivery. Explicit task instructions override this default.

## Package and evidence

Create `outputs/<artifact-id>/<version>/` under the current project, or an explicitly configured output root. Use portable ASCII filenames and relative asset paths. Include `report.md`, `CHANGELOG.md`, and `manifest.json`; include `index.html` when visual or interactive presentation helps; include `data.json`/`data.csv` and assets when applicable. Do not invent a chart or empty dataset to satisfy a fixed file count.

Use a stable artifact ID and a new version for each content revision. A released version is immutable; never overwrite it with different content. Record input sources, material cutoff time, limitations and SHA-256 hashes. Distinguish paper claims, static code findings, plans, observed activity and runtime validation. For robot datasets, separately record annotation persistence, conversion completion and dataset readback. HTML is a review interface, not proof that data or labels were saved.

Use `scripts/package.py init PATH --artifact-id ID --version v001` to initialize a package, then write the actual content. Run `scripts/package.py seal PATH` before delivery. Keep the resulting source package on the generating machine or transfer it intact; another machine must verify hashes before continuing. Resolve source locations through configured roots or portable links; do not embed machine-specific absolute paths in shared HTML.

## Dual delivery

Read the machine-local `research-dual-delivery.json` in the active Codex configuration directory when available. It is optional and holds destinations and resource-root mappings, not credentials. Missing destinations are unresolved configuration, not authorization to choose an arbitrary folder, account, chat or public host. Ask for required destination information while continuing package preparation.

For Feishu, prefer lightweight HTML preview in Drive for internal review; use Miaoda when long-term hosting or complex interaction requires it. Use available Feishu skills/tools, with the current task's permissions. Upload the report, applicable presentation and structured supporting data or provide a source-package attachment. Raw videos/datasets remain at their original storage by default; deliver selected previews, metadata and links as needed. Check actual access and resource loading.

For GPT, default to the user's ChatGPT conversation or Project. Upload the same report and relevant supporting files to the explicitly selected target through an available supported tool or UI. A Codex chat, an API Files upload and a ChatGPT upload are different destinations; never substitute one for another. Do not imply automatic Feishu-to-ChatGPT synchronization. If no upload surface exists, provide the package and mark `blocked_capability`. A downloadable file link is not a successful ChatGPT upload.

Record each side independently in `manifest.json`: `pending`, `uploaded`, `verified`, `blocked_destination`, `blocked_auth`, `blocked_capability`, or `failed`; include target, link/receipt, file list, time and error where applicable. `uploaded` requires a real receipt/UI observation; `verified` additionally requires access/readback or equivalent evidence. Partial success is partial delivery. Resume only missing/failed sides after verifying content hashes; inspect existing receipts to prevent duplicate uploads. Stop after one repeat of the same upload failure and retain the reason. Never mark a destination verified based on a local file or generated link.

Do not send messages, create recurring jobs or make content public solely because of this skill. Use explicit existing task authorization for those operations.

## Feedback and machines

Merge Feishu comments and GPT discussion into a common change list, preserving source links and unresolved disagreement. Generate a new package version and deliver that version to both targets. Upload does not imply feedback synchronization or automatic merging.

`install.py` installs identical skill files and a scoped global AGENTS rule; it preserves unrelated rules and machine configuration. Copy this folder to another machine and run `python3 install.py --machine NAME`. Authentication and destination configuration are local to each host. See `MULTI_MACHINE.md` for installation and continuity details. Report package completion, Feishu status and ChatGPT status separately.
