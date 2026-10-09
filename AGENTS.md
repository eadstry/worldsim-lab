# Workspace instructions

This repository combines upstream source references with local AutoData research documents and a private blog.

- Read the nearest AGENTS.md before working inside an upstream repository. Preserve its instructions.
- Cloud tasks can inspect source and build/check the private blog. GPU simulation and training require a separately configured GPU server. Do not report static inspection as runtime validation.
- Keep upstream submodules at their recorded commits unless explicitly asked to update them. Make proposed changes in patches or in this repository's workspace-overlays directory unless the task authorizes editing upstream code.
- Run `npm --prefix private-blog run check` after blog changes; run its build first if sources changed.
- Do not publish the blog or change access control as a side effect of GitHub synchronization.

<!-- research-dual-delivery:start -->
## Research dual delivery
For reusable research reports, reproduction plans, data reviews, experiment comparisons, HTML dashboards and weekly reports, read `skills/research-dual-delivery/SKILL.md` first. Package a consistent version, deliver to the user's authorized Feishu and ChatGPT destinations, and record each destination independently. Missing destinations or upload capabilities do not prevent local package preparation. Short chats and intermediate files do not require packaging. Keep machine paths, destinations and authentication in machine-local configuration. This rule does not authorize messaging, automations or public sharing. Current user instructions take precedence.
<!-- research-dual-delivery:end -->
