# worldsim-lab

围绕 AutoData 数据生成、Isaac Lab-Arena 评估与 OpenArm 实验的具身智能研究工作区。

[文档总索引](docs/README.md) · [实验成果](outputs/README.md) · [共享配置](config/README.md) · [版本管理](docs/version-management.md)

## 从这里开始

| 任务 | 入口 |
| --- | --- |
| 阅读 AutoData 原理、数据流和随机化 | [AutoData 资料](docs/autodata/README.md) |
| 阅读完整技术文章 | [全流程可视化讲解](docs/autodata/AutoData-全流程可视化讲解.md) |
| 配置运行环境 | [环境配置](docs/environment-setup.md) |
| 运行 Arena OpenArm 评测示例 | [Arena benchmark](workspace-overlays/openarm-benchmark/README.md) |
| 使用 OpenArm 生成、监控和导出工具 | [生产扩展](workspace-overlays/openarm-production/README.md) |
| 查找报告、附件和历史验证 | [成果索引](outputs/README.md) |
| 查看分支整合、文档迁移和归档记录 | [仓库整理记录](docs/repository-cleanup-20261022.md) |

## 文档固定位置

新增说明、笔记和报告统一放在 `docs/`，按主题放入 `docs/<topic>/`，并更新 `docs/README.md`。正文与配图保存在同一主题目录；不在根目录、运行目录或站点目录维护第二份正文。

`outputs/<artifact-id>/vNNN/` 继续保留已经封存的版本化交付物和验证证据。历史封存内容保持原样。HTML 文档下载后用浏览器打开。

## 获取与检查

```bash
git clone https://github.com/eadstry/worldsim-lab.git
cd worldsim-lab
# 初始化锁定的顶层上游源码并运行主机检查
bash scripts/cloud-setup.sh
# 有意不初始化上游源码的文档/工具检出
bash scripts/cloud-check.sh --allow-uninitialized
```

主机检查需要 Git 和 Python 3，校验上游版本锁、封存成果、文档链接与主机测试。GPU 仿真需要在目标机另外准备 NVIDIA GPU、Isaac Sim、cuRobo、资产与数据；主机检查通过不代表 GPU 或实机验证通过。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `AutoData/`、`IsaacLab-Arena/`、`RLinf/` | 固定提交的上游子模块，见 [版本锁](upstream-lock.json) |
| [docs/](docs/README.md) | 研究笔记、报告、离线可视化、主题索引与过程记录 |
| [outputs/](outputs/README.md) | 已封存的版本化成果和证据 |
| [config/](config/README.md) | AutoData / Arena 共用配置 |
| `workspace-overlays/` | 本地扩展、上游补丁与来源记录 |
| `scripts/` | 初始化、审查、验证与共享队列工具 |
| `skills/` | 可复用的研究交付工具 |

新任务从更新后的 `origin/main` 建分支，通过审查和检查后提交、推送并使用 PR 合并。运行数据、机器环境和未提交文件需单独备份。各上游项目保留原有许可证。
