# WorldSimReady-Home

Private workspace for embodied AI source exploration, AutoData research documents and a private blog.

## Contents

| Path | Contents |
| --- | --- |
| `AutoData/`, `IsaacLab-Arena/`, `RLinf/` | Upstream Git submodules pinned to the commits in `upstream-lock.json` |
| `AutoData-*.md`, `AutoData-*.html` | Local AutoData explanations and visualizations |
| `workspace-overlays/AutoData/agentic_design/` | Preserved local AutoData design document; setup copies it into the source checkout |
| `private-blog/` | Blog sources, build scripts and existing generated site; no hosting credentials/configuration |
| `outputs/` | Existing versioned research deliverables, preserved as saved |
| `skills/research-dual-delivery/` | Portable research delivery instructions and package tool |

The upstream repositories retain their own licenses and instructions. A private GitHub repository does not establish access control for a deployed website.

## Codex Cloud setup

Select `eadstry/WorldSimReady-Home`, branch `main`, when creating a cloud environment. Keep environment access private. Use a Node.js runtime compatible with `private-blog/package-lock.json` (Node 22 or later) and Git. Allow GitHub and npm registry access during setup.

Install/setup command:

```bash
bash scripts/cloud-setup.sh
```

Verification command:

```bash
bash scripts/cloud-check.sh
```

Setup fetches top-level upstream source without Git LFS assets and without recursively initializing simulation dependencies. This supports source analysis and blog development. It does not provision NVIDIA GPUs, Isaac Sim, cuRobo, training data or server credentials. Follow each upstream project's own installation guide in a suitable GPU environment for simulation or training.

After setup succeeds, publish the environment and verify the branch/commit and check output in the cloud. GitHub upload alone is not proof of cloud environment publication.

## Clone

```bash
git clone https://github.com/eadstry/WorldSimReady-Home.git
cd WorldSimReady-Home
bash scripts/cloud-setup.sh
```

For later synchronization, commit and push workspace changes. Changes made inside a submodule must be saved separately to a reachable repository/commit or as a workspace overlay; a parent repository only stores the submodule commit reference. Cloud tasks and local work do not continuously mirror each other's uncommitted files.
