# 研究资料

本目录保存工作区维护的说明和独立可视化。先读主题索引，再按问题进入源码；源码阅读须遵守相应目录的 `AGENTS.md`。

| 主题 | 入口 | 内容 |
| --- | --- | --- |
| AutoData | [资料与阅读顺序](autodata/README.md) | 原理、数据流、随机化可视化及博客正文来源 |
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
