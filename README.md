# WorldSimReady-Home

具身智能研究工作区：固定版本的上游源码、AutoData 研究资料、版本化交付成果和博客。

## 从这里开始

- 理解 AutoData 原理：阅读[研究资料索引](docs/README.md)，再按主题进入源码。
- 查找报告、配置示例和交付记录：阅读[成果索引](outputs/README.md)。
- 修改博客文章：阅读[博客维护说明](private-blog/README.md)，编辑 `private-blog/content/` 中的正文。
- AutoData / Arena 共用配置：从 [`config/README.md`](config/README.md) 开始，编辑 `config/openarm/experiment.json`，通过 `scripts/shared-config.py` 校验、解析和启动。
- 查看本地上游扩展：进入 `workspace-overlays/`；上游版本由 `upstream-lock.json` 和 Git 子模块记录。
- 管理分支、worktree 和提交：阅读[版本管理约定](docs/version-management.md)及[过程记录](docs/process-log.md)。

分析前先读本文件、相关主题索引和目标目录最近的 `AGENTS.md`，再检索相关源码。环境目录、日志、构建产物和旧交付版本不作为默认分析入口。

## Contents

| Path | Contents |
| --- | --- |
| `AutoData/`, `IsaacLab-Arena/`, `RLinf/` | Upstream Git submodules pinned to the commits in `upstream-lock.json` |
| [`docs/`](docs/README.md) | Local explanations, visualizations and topic navigation |
| `workspace-overlays/AutoData/agentic_design/` | Workspace-owned AutoData design documents; read directly without copying into upstream |
| `private-blog/` | Blog sources, build scripts and existing generated site; no hosting credentials/configuration |
| [`outputs/`](outputs/README.md) | Versioned research deliverables and their validation/delivery records |
| [`config/`](config/README.md) | Shared AutoData / Arena configuration and usage |
| `workspace-overlays/shared_config/` | Workspace-owned environment factory and adapters; no Arena source edits |
| `scripts/` | Workspace setup, shared-config launcher and verification commands |
| `.vscode/settings.json` | Explorer/search exclusions for local environments and generated files |

## 内容维护边界

- `docs/` 保存工作区说明和独立资料；每个主题索引说明正文来源及维护方式。
- 博客 AutoData 全流程文章以 `private-blog/content/autodata/AutoData-全流程可视化讲解.md` 为唯一正文编辑源；`docs/autodata/` 中的同名 HTML 是历史参考版。
- `outputs/<artifact-id>/<version>/` 是交付快照。修订内容时新增版本，不覆盖已有版本；各端交付情况以该版本 `manifest.json` 为准。
- 上游子模块保持现有路径和锁定提交。本地扩展优先放入 `workspace-overlays/`，遵守目标仓库的规则。
- `.venv/`、依赖、日志属于机器环境或运行产物，不作为资料入口。编辑器隐藏不等于删除，也不改变 Git 跟踪规则。
- `private-blog/dist/` 目前包含手工维护的首页，`backups/` 仍被检查脚本引用。不要按可再生缓存清空它们。

根目录原有三个 `AutoData-*` 资料已统一移到 `docs/autodata/`，文件名保留。

VS Code 默认隐藏虚拟环境、依赖、博客输出和备份；搜索另排除日志、嵌套上游子模块及文章旧交付版本。上游顶层源码和当前报告仍可搜索。需要核对被排除文件时，可关闭搜索面板的“使用排除设置和忽略文件”，或显式指定命令行路径；这些设置不会改变命令行 `rg` 的范围。

The upstream repositories retain their own licenses and instructions. A private GitHub repository does not establish access control for a deployed website.

## Codex Cloud setup

Select `eadstry/WorldSimReady-Home`, branch `main`, when creating a cloud environment. Keep environment access private. Use a Node.js runtime compatible with `private-blog/package-lock.json` (Node 22 or later) and Git. Allow GitHub and npm registry access during setup.

Install/setup command:

```bash
bash scripts/cloud-setup.sh
```

Verification command (also builds the blog and runs host-only tests):

```bash
bash scripts/cloud-check.sh
```

Setup fetches top-level upstream source without Git LFS assets and without recursively initializing simulation dependencies. This supports source analysis and blog development. It does not provision NVIDIA GPUs, Isaac Sim, cuRobo, training data or server credentials. Follow each upstream project's own installation guide in a suitable GPU environment for simulation or training.

Setup requires Python 3 in addition to Node and Git, refuses dirty or divergent existing upstream checkouts, and installs the root repository's version-check pre-commit hook. For a source-only local checkout intentionally missing RLinf, use `bash scripts/cloud-check.sh --allow-uninitialized`. Upstream local changes are reported; use `--require-clean-upstream` for a clean-source audit. The shared OpenArm runtime currently has a missing local source dependency; see the version management guide before running it.

After setup succeeds, publish the environment and verify the branch/commit and check output in the cloud. GitHub upload alone is not proof of cloud environment publication.

## Clone

```bash
git clone https://github.com/eadstry/WorldSimReady-Home.git
cd WorldSimReady-Home
bash scripts/cloud-setup.sh
```

For later synchronization, commit and push workspace changes. Changes made inside a submodule must be saved separately to a reachable repository/commit or as a workspace overlay; a parent repository only stores the submodule commit reference. Cloud tasks and local work do not continuously mirror each other's uncommitted files.
