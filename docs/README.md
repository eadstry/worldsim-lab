# 研究资料

本目录保存工作区维护的说明和独立可视化。先读主题索引，再按问题进入源码；源码阅读须遵守相应目录的 `AGENTS.md`。

| 主题 | 入口 | 内容 |
| --- | --- | --- |
| AutoData | [资料与阅读顺序](autodata/README.md) · [Ray 直接导出](autodata/autodata-ray-20261022.md) · [生产实验](autodata/autodata-ray-20261022-r02.md) · [PDF](autodata/autodata-ray-20261022-r02.pdf) · [图解版](autodata/autodata-ray-20261022-r03.md) · [图解 PDF](autodata/autodata-ray-20261022-r03.pdf) | 原理、数据流与可视化；2026-10-22：Ray 并行 LeRobot v3 直接导出、容量与生产效率实验 |
| Arena 与共用配置 | [成果索引](../outputs/README.md) | 示例运行说明、RoboLab 配置、AutoData/Arena 共用配置建议 |
| 运行环境 | [环境配置](environment-setup.md) | 主机、仓库、容器与原生环境、机器本地参数及验收顺序 |
| 主机环境 | [存储挂载记录](host-storage.md) | `/data` 挂载容量及截图中的存储信息 |
| 版本管理与过程记录 | [管理约定](version-management.md) · [问题与改进](process-log.md) | 分支、worktree、锁定检查、快照保护及待解决事项 |

维护约定：

- 新增独立资料放到 `docs/<主题>/`，并更新主题索引及本页；目录名优先使用稳定的 ASCII 标识。
- 文章已有明确编辑源时，索引链接到源文件，不复制一份持续维护的正文。
- 旧资料中的“当前代码”和行号属于写作时的上下文；判断现状前需核对锁定提交及本地变更。

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

## 2026-10-22 整合资料

| 创建日期 | 资料 | 用途 |
| --- | --- | --- |
| 2026-10-22 | [实验图册清晰度修订](experiment-portfolio/experiment-chartbook-20261022.md) | 全部 19 图矢量重绘、大字号 PDF、300 dpi PNG 与来源校验 |
| 历史资料迁入 | [AutoData-全流程可视化讲解](autodata/AutoData-全流程可视化讲解.html) | 离线阅读版 |
| 历史资料迁入 | [AutoData-全流程可视化讲解](autodata/AutoData-全流程可视化讲解.md) | 报告或说明，验证范围见正文 |
| 历史资料迁入 | [AutoData-原理与数据流总览](autodata/AutoData-原理与数据流总览.md) | 报告或说明，验证范围见正文 |
| 历史资料迁入 | [AutoData-数据生成随机化可视化](autodata/AutoData-数据生成随机化可视化.html) | 离线阅读版 |
| 20261022 | [autodata-full-pipeline-20261022](autodata/autodata-full-pipeline-20261022.html) | 离线阅读版 |
| 20261022 | [autodata-multirobot-v3-20261022](autodata/autodata-multirobot-v3-20261022.md) | 报告或说明，验证范围见正文 |
| 20261022 | [autodata-multirobot-v3-gallery-20261022](autodata/autodata-multirobot-v3-gallery-20261022.html) | 离线阅读版 |
| 20261022 | [autodata-arena-benchmark-20261022](autodata-arena-benchmark-20261022.md) | 报告或说明，验证范围见正文 |
| 20261021 | [autodata-interview-media-20261021](autodata-interview-media-20261021.md) | 报告或说明，验证范围见正文 |
| 20261020 | [report-20261020](experiment-portfolio/report-20261020.md) | 报告或说明，验证范围见正文 |
| 历史资料迁入 | [lerobot-v3-oxe-visual](lerobot-v3/lerobot-v3-oxe-visual.html) | 离线阅读版 |
| 20261021 | [open-source-parameter-survey-20261021](openarm-task-error/open-source-parameter-survey-20261021.pdf) | 报告或说明，验证范围见正文 |
| 20261021 | [openarm-task-error-20261021-r02](openarm-task-error-20261021-r02.html) | 离线阅读版 |
| 20261021 | [openarm-task-error-20261021-r02](openarm-task-error-20261021-r02.md) | 报告或说明，验证范围见正文 |
| 20261021 | [openarm-task-error-20261021-r02](openarm-task-error-20261021-r02.pdf) | 报告或说明，验证范围见正文 |
| 20261019 | [report-rewrite-plan-20261019](report-rewrite-plan-20261019.md) | 报告或说明，验证范围见正文 |
| 20261022 | [repository-cleanup-20261022](repository-cleanup-20261022.md) | 报告或说明，验证范围见正文 |
| 20261022 | [server-shutdown-recovery-20261022-r01](server-shutdown-recovery-20261022-r01.md) | 报告或说明，验证范围见正文 |
| 20261022 | [server-shutdown-recovery-20261022](server-shutdown-recovery-20261022.md) | 报告或说明，验证范围见正文 |

[分支来源清单](integration/branches-20261022.json) · [作品集资料](experiment-portfolio/README.md) · [LeRobot v3 格式](lerobot-v3/README.md) · [OpenArm 误差分析](openarm-task-error/README.md)
## action–state 差值资料归档

| 创建日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-10-22 | [实验与报告汇总](action-state-causality-20261022.md) | 两轮差值实验、历史报告与原始数据的本地压缩包说明；附[文件清单](action-state-causality-20261022-manifest.json)和[完整性校验](action-state-causality-20261022-verification.json)。 |

## 2026-10-23 配置与验证

| 创建日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-10-23 | [OpenArm GS 配置检查与渲染](openarm-gs-render-20261023.md) | 新配置归档、185 项哈希检查和 Isaac Sim 高斯场景 RGB 样例；不含任务动力学验证 |

## 2026-10-23 GS 生产验证

| 创建日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-10-23 | [OpenArm GS 预设任务生产与视频](openarm-gs-production-20261023.md) | 原配置 SkillGen 生成 1 条成功轨迹、三路 RGB、独立物理回放及约 88 秒视频 |

## 2026-10-23 GS 视频视角

| 创建日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-10-23 | [OpenArm GS 生产视频 r02](openarm-gs-production-20261023-r02.md) | 同一条预设任务的左右腕部原始 RGB 视频、外部视角入口、完整解码检查及右腕黑画面限制 |
