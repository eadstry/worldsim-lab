# worldsim-lab

围绕 **AutoData 数据生成、Isaac Lab-Arena 评估与 OpenArm 实验**的具身智能研究工作区，统一管理固定版本的上游源码、本地扩展、研究资料、实验报告和博客。

[自动提交与审查](docs/automatic-version-review.md) · [实验版本检查记录](docs/experimental-analysis-20261015.md) · [研究资料](docs/README.md) · [实验成果](outputs/README.md) · [OpenArm 扩展](workspace-overlays/openarm-production/README.md) · [共享配置](config/README.md) · [博客维护](private-blog/README.md)

> 2026-10-14 的本机保存快照已归档到 Release `archive-branches-20261020`，来源、上游补丁和当时的检查记录仍见[快照说明](workspace-overlays/local-frontier-20261014/README.md)；当前实现和验证状态以 main 中的文件为准。

## 从这里开始

| 你想做什么 | 推荐入口 |
| --- | --- |
| 运行 Arena OpenArm 评测示例 | [Arena benchmark](workspace-overlays/openarm-benchmark/README.md) |
| 理解 AutoData 的原理、数据流与随机化 | [AutoData 资料与阅读顺序](docs/autodata/README.md) |
| 阅读完整技术文章 | [AutoData 全流程可视化讲解](private-blog/content/autodata/AutoData-全流程可视化讲解.md) |
| 查找报告、配置示例与历史验证 | [成果索引](outputs/README.md) |
| 查看 OpenArm 生成、监控和并行导出 | [生产扩展说明](workspace-overlays/openarm-production/README.md) |
| 配置 AutoData 生成与 Arena 评估 | [共享配置说明](config/README.md) |
| 在新机器或容器里配置运行环境 | [运行环境配置](docs/environment-setup.md) |
| 修改博客或在本机预览 | [博客维护说明](private-blog/README.md) |
| 管理分支、worktree 和上游修改 | [版本管理约定](docs/version-management.md) · [过程记录](docs/process-log.md) |

HTML 资料在 GitHub 文件页展示源码；下载到本机后用浏览器打开。效率报告也提供可直接下载的 [PDF](outputs/autodata-efficiency-report/v001/AutoData-效率优化报告.pdf)。

## 当前进展与验证范围

以下状态基于 2026-10-14 保存的记录。主机检查、历史 GPU 实验和物理验收分别记录。

| 模块 | 已有内容 | 当前验证范围 |
| --- | --- | --- |
| 研究资料与博客 | AutoData 原理、随机化专题、全流程文章 | 博客构建、正文与资源完整性检查已通过 |
| AutoData / Arena 共享配置 | 公共环境工厂、生成与评估适配器 | 历史 GPU 接口验证已保存；当前仍缺少所需 OpenArm 本地源文件，恢复前 `resolve/run` 会提前失败 |
| OpenArm 生产扩展 | 生成启动器、资源监控、内存受限的并行 HDF5 导出 | 主机测试已通过；最新资源自适应调度尚未重新进行 GPU 吞吐测量 |
| 效率实验 | 同步与 1 / 2 个导出进程的历史 GPU 对照 | 2 个进程的最终文件吞吐提升约 29.8%；严格物理终态检查各为 23/24，整体验收仍未通过 |

实验条件、统计口径与限制见[效率报告](outputs/autodata-efficiency-report/v001/index.html)及[验证证据](workspace-overlays/openarm-production/async-export-validation.json)。前沿快照的[主机检查记录](workspace-overlays/local-frontier-20261014/validation.json)不代表重新执行了 GPU 仿真或训练。

## 快速开始

仅阅读资料时，无需安装仿真环境。克隆仓库后，按对应 PR 选择需要阅读或复现的分支：

```bash
git clone https://github.com/eadstry/worldsim-lab.git
cd worldsim-lab
```

### 源码分析与主机检查

准备 Git、Python 3 和 Node.js 22+，并允许访问 GitHub 与 lock 文件使用的 npm registry。在新的工作区中执行：

```bash
bash scripts/cloud-setup.sh
```

该脚本初始化三个顶层上游子模块，跳过 Git LFS 大型资产和嵌套仿真依赖，安装博客依赖及版本检查提交钩子，最后运行完整主机检查。已有上游工作树包含本地修改或版本偏移时，脚本会停止，先按[版本管理约定](docs/version-management.md)处理。

后续修改完成后执行：

```bash
bash scripts/cloud-check.sh
```

检查包含上游版本锁定、封存成果校验、版本管理与共享配置测试，以及博客构建和完整性检查。若当前 worktree 有意不初始化上游源码，可使用 `--allow-uninitialized`；它仅允许缺少源码检出，不表示运行依赖已经就绪。

### 博客本机预览

完成上述依赖安装后：

For validation shared by multiple worktrees on one host, use the [task queue](docs/task-queue.md). Submit resource-intensive commands with `python3 scripts/task-queue.py submit --name validation -- <command>`; tasks run serially with separate logs and exit status.

```bash
npm --prefix private-blog run build
npm --prefix private-blog run check
python3 -m http.server 8765 --bind 127.0.0.1 --directory private-blog/dist
```

打开 `http://127.0.0.1:8765`。正文从 Markdown 构建，编辑入口和资源约定见[博客维护说明](private-blog/README.md)。

### GPU 仿真与数据生成

GPU 实验需要另外配置 NVIDIA GPU、Isaac Sim、cuRobo、任务资产和输入数据。按[OpenArm 扩展说明](workspace-overlays/openarm-production/README.md)准备运行环境，再选择生成与监控入口；共享配置的恢复要求见[配置说明](config/README.md)。

运行环境、原始数据集、HDF5 导出和批量日志在运行机器上单独保存与备份，克隆仓库不会恢复这些内容。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `AutoData/`、`IsaacLab-Arena/`、`RLinf/` | 上游 Git 子模块，提交固定在 [`upstream-lock.json`](upstream-lock.json) |
| [`docs/`](docs/README.md) | 研究笔记、可视化、主题索引及维护记录 |
| [`config/`](config/README.md) | AutoData / Arena 共用的 OpenArm 配置 |
| [`workspace-overlays/openarm-production/`](workspace-overlays/openarm-production/README.md) | OpenArm 生成、监控、导出实现及测试 |
| `workspace-overlays/shared_config/` | 公共环境工厂与框架适配器 |
| `workspace-overlays/AutoData/agentic_design/` | 工作区维护的 AutoData 设计资料 |
| [`workspace-overlays/local-frontier-20261014/`](workspace-overlays/local-frontier-20261014/README.md) | 本机版本保存清单、上游补丁与主机检查记录 |
| [`outputs/`](outputs/README.md) | 按主题和版本封存的报告、附件与验证记录 |
| [`private-blog/`](private-blog/README.md) | 博客正文、资源、构建脚本和已有站点文件 |
| `scripts/` | 初始化、共享配置启动及工作区检查脚本 |

## 维护约定

- **上游版本固定**：阅读或修改前遵守最近的 `AGENTS.md`；本地扩展优先放在 `workspace-overlays/`，上游改动保存为补丁。父仓库只记录子模块提交引用。
- **正文来源明确**：AutoData 全流程文章以 `private-blog/content/autodata/AutoData-全流程可视化讲解.md` 为唯一正文源；`docs/autodata/` 中的同名 HTML 保留为历史参考。
- **成果按版本封存**：使用 `outputs/<artifact-id>/<version>/`，修订时新增版本。正文、资源和校验值保持一致，交付状态以各版本 `manifest.json` 为准；成果索引与生命周期见 [`outputs/index.json`](outputs/index.json) 和 `config/outputs-status.json`。
- **站点文件按维护规则保留**：`private-blog/dist/` 包含手工维护的首页，`backups/` 被检查脚本引用，不能作为缓存整体清空。
- **同步以提交为单位**：通过必要检查后提交并推送；其他机器需获取已推送提交，未提交文件不会自动镜像。VS Code 排除设置仅影响编辑器显示与搜索。

各上游项目保留其原有许可证。GitHub 同步不发布博客，也不修改网站访问权限；网站权限需单独管理。
