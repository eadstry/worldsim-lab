# 研究资料

本目录保存工作区维护的说明和独立可视化。先读主题索引，再按问题进入源码；源码阅读须遵守相应目录的 `AGENTS.md`。

## 主题资料

| 主题 | 入口 | 内容 |
| --- | --- | --- |
| AutoData | [资料与阅读顺序](autodata/README.md) | 原理、数据流、随机化可视化及博客正文来源 |
| Arena 与共用配置 | [成果索引](../outputs/README.md) | 示例运行说明、RoboLab 配置、AutoData/Arena 共用配置建议 |
| 运行环境 | [环境配置](environment-setup.md) | 主机、仓库、容器与原生环境、机器本地参数及验收顺序 |
| 主机环境 | [存储挂载记录](host-storage.md) | `/data` 挂载容量及截图中的存储信息 |
| 版本管理与过程记录 | [管理约定](version-management.md) · [问题与改进](process-log.md) | 分支、worktree、锁定检查、快照保护及待解决事项 |
| LeRobot v3 数据格式 | [可视化笔记](lerobot-v3/README.md) | 2026-10-20 的 v3 与 OXE 格式对比、失败模式与异构性说明图 |

## 按创建日期归档的报告

| 创建日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-10-15 | [实验分支整合检查记录](experimental-analysis-20261015.md) | 合并来源、验证范围与未纳入的进行中工作 |
| 2026-10-16 | [根目录归档与忽略边界](git-hygiene-20261016.md) | 未跟踪文件归档、Git 忽略边界与工作树迁移 |
| 2026-10-16 | [全库工作树核对](git-worktrees-20261016.md) | 工作树保留策略与迁移前后状态 |
| 2026-10-19 | [实验讲解重写方案](report-rewrite-plan-20261019.md) | 汇总报告改写思路与底层报告模板统一 |
| 2026-10-20 | [GPU 利用率实验方案](experiment-plan-gpu-utilization-20261020.md) | 实验设计、资源占用与排队安排 |

## 常驻说明

长期维护、随现状更新的文档，不按日期另存版本。

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| [运行环境配置](environment-setup.md) | 从空机到可复验 GPU 环境的配置路径 | v001，2026-10-20 |
| [主机存储挂载](host-storage.md) | `/data` 挂载与容量 | 2026-10-19 记录 |
| [自动版本提交与审查](automatic-version-review.md) | 任务完成后的提交、检查与推送流程 | 现行 |
| [任务队列](task-queue.md) | 同主机 GPU 任务的 FIFO 排队方式 | 现行 |
| [工作区版本管理](version-management.md) | 分支、worktree 与提交边界 | 现行 |
| [问题与改进记录](process-log.md) | 版本管理待解决问题 | 滚动记录 |

## 证据与记录

报告引用的原始证据与机器记录，按事件日期命名。

| 日期 | 路径 | 内容 |
| --- | --- | --- |
| 2026-10-15 | [integration/](integration/) | 分析整合的云端检查输出、来源清单与验证结果 |
| 2026-10-16 | [工作树状态快照](git-worktrees-20261016.json) | 全库工作树、分支与未提交改动 |
| 2026-10-16 | [工作树迁移回执](worktree-migration-receipts-20261016.json) | 恢复点迁移的文件数与校验结果 |
| 2026-10-20 | [GitHub 同步记录](github-sync-20261020.json) | 推送内容与校验 |
| 2026-10-20 | `/data/WorldSimReady-Home/key-evidence-20261020` | 成果证据包（数据与截图，不在 Git 内） |

## 成果

[成果索引](../outputs/README.md) 由 `scripts/build-outputs-index.py` 依据各版本 `manifest.json` 生成，现有 16 个工件、26 个封存版本。版本目录为 `outputs/<artifact-id>/<vNNN>/`，入口通常是 `report.md` 或 `index.html`；新增版本后在根目录重跑脚本并提交生成结果。

## 维护约定

- 新产出的报告、记录和方案一律放在 `docs/`，根目录与 `runs/` 不留文档副本；`outputs/` 只放封版成果。
- 文件名按 `<主题>-<YYYYMMDD>[-rNN].md` 命名：主题用稳定的小写 ASCII 标识，日期取创建当天；同一问题沿用同一主题，使相关文档按创建时间自然排列。多份文档共用的参考资料放 `docs/<主题>/`。
- 每份新文档在 [按创建日期归档的报告](#按创建日期归档的报告) 登记一行（创建日期、链接、一句话用途）；已有条目续写，不为同一问题新增别名。长期维护的说明放 [常驻说明](#常驻说明)，报告引用的证据放 [证据与记录](#证据与记录)。
- 被取代的文档保留原文并追加新的日期版本，不改写旧结论。
- 文章已有明确编辑源时，索引链接到源文件，不复制一份持续维护的正文。
- 旧资料中的“当前代码”和行号属于写作时的上下文；判断现状前需核对锁定提交及本地变更。
- 重命名或移动文档后运行 `python3 scripts/check-doc-links.py`，并更新所有受影响的链接。

## 实验整合版本

[2026-10-15 Codex 分析整合检查记录](experimental-analysis-20261015.md)列出合并来源、验证范围及未纳入的进行中工作。

[自动版本提交与审查](automatic-version-review.md)：任务基线、提交回执、共享钩子和 GitHub 主机检查。

## 2026-10-20 新增准备材料

- [GPU 高负载实验计划](experiment-plan-gpu-utilization-20261020.md)：待执行设计，尚无负载矩阵结果。
- [OpenArm 24 环境资源预检](../workspace-overlays/openarm-capability24/README.md)：资源准入工具，不等于仿真验收。
- [源码与草稿同步清单](github-sync-20261020.json)：原始快照来源及集成适配记录。
- [OpenArm 图像与隔离导出诊断](experiments/openarm-readiness-20261020.md)：历史运行结果及证据边界。
- [实验图册](../outputs/experiment-chartbook/v001/report.md)：19 张图、原始记录、指标索引与 PDF。
- [最新改动集成记录](main-integration-20261020.md)：迁移来源、适配和检查范围。
