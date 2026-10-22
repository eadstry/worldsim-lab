# 成果索引

下表由 `scripts/build-outputs-index.py` 依据各版本 `manifest.json` 与 `config/outputs-status.json` 生成，请勿手工编辑表格。
“当前版本”指该工件下编号最大的封存版本，不表示已完成运行验证或双端交付；交付状态以各版本 `manifest.json` 为准。

<!-- outputs-index:start -->

| 主题 | 状态 | 版本 | 入口 | 内容与验证范围 | 已记录交付 |
| --- | --- | --- | --- | --- | --- |
| Arena 示例运行与使用说明 | 当前 | v001 · 1 版 · 9 KB | [v001](arena-examples-guide/v001/report.md) | 静态源码说明，运行命令需在适当 GPU 环境验证；保留写作时的环境观察 | 飞书、GPT 均为 blocked_destination |
| Arena RoboLab 配置解耦 | 当前 | v001 · 1 版 · 12 KB | [v001](arena-robolab-config-guide/v001/report.md) | 场景、任务和评估配置说明；未执行仿真或完整 schema 验证 | 飞书、GPT 均为 blocked_destination |
| AutoData / Arena 共用配置 | 当前 | v003 · 3 版 · 449 KB | [v003](autodata-arena-shared-config/v003/report.md) | 用户授权现有原生环境 GPU 验证；环境/动作/成功判据比较通过，Arena 入口短测通过 | 用户要求仅本地保存，未上传 |
| AutoData 域随机化实测 | 当前 | v002 · 2 版 · 7.9 MB | [v002](autodata-domain-randomization/v002/index.html) | 2026-10-16 RTX 5090 实测 OpenArm 左臂 4 环境、256 个 reset 位姿；9 项通过；未评估轨迹生成成功率；视觉结论由 v002 替代 v001 | 本地保存，未上传或发布 |
| AutoData 域随机化方法总览 | 当前 | v001 · 1 版 · 97 KB | [v001](autodata-domain-randomization-catalog/v001/catalog.json) | 45 类方法，附参数、源码入口与接入限制；源码清点和原理示意，未新增 GPU 实验；HTML 为嵌入式片段 | 本地归档并随 Git 同步，未发布站点 |
| AutoData 效率复盘图册 | 当前 | v022 · 1 版 · 15.0 MB | [v022](autodata-efficiency-review/v022/charts.html) | v022 含 51 页图册、项目架构说明与 cuRobo v1/v2 对比；逐页补充方法、意义、结论与术语；本版仅改善阅读，无新增优化实测 | 本地交付并随 Git 同步 |
| AutoData 全流程文章 | 当前 | v003 · 3 版 · 4.6 MB | [v003](autodata-guide/v003/index.html) | 文章及飞书排版快照；没有新增仿真实验 | 飞书记录为 verified；GPT 为 blocked_destination |
| AutoData v1 内部耗时对照 | 当前 | v001 · 1 版 · 491 KB | [v001](autodata-v1-internal-timing/v001/index.html) | 2026-10-15 真实 GPU 配对实验：4 环境、同步与 auto 导出各 8/8 成功，8 组动作序列精确匹配；最终文件吞吐提升 47.2% | 本地保存，未上传或发布 |
| cuRobo v2 升级评估 | 当前 | v001 · 1 版 · 27 KB | [v001](curobo-v2-upgrade-assessment/v001/report.md) | 历史 v1/v2 单环境验证；样本不足以证明总体成功率或性能优劣，v2 保留实验后端 | 本地版本归档，未上传飞书或 ChatGPT |
| 具身数据生产实验总览 | 当前 | v005 · 5 版 · 9.7 MB | [v005](embodied-experiment-portfolio/v005/report.md) | 18 组实验与检查，每组一图；新增 LeRobot v3 转换、相机审计、8 环境隔离导出、24 环境内存准入；正文 192 行 | 本地保存，未发布站点 |
| 具身数据生产实验图册 | 当前 | v001 · 1 版 · 4.7 MB | [v001](experiment-chartbook/v001/index.html) | 19 张图、20 页 PDF 与 157 行指标；复用 14 张原图，另 5 张由已保存记录派生。区分任务、帧与资源快照口径；保留右腕近黑与 24 环境准入阻塞。未新增仿真或训练。 | 本地封存并随 Git 同步，未发布站点 |
| Arena OpenArm 评测示例 | 当前 | v002 · 2 版 · 1.4 MB | [v002](openarm-benchmark/v002/index.html) | v002 含零动作/固定轨迹的 GPU 实测、原生评估视频与主机测试；并行环境判定分开记录 | 本地版本归档，未新增双端交付 |
| cuRobo v2 抓取诊断 | 支撑材料 | v001 · 1 版 · 230 KB | [v001](curobo-v2-grasp-diagnosis/v001/report.md) | v2 抓取失败的定位记录，作为升级评估的佐证 | 本地版本归档，未上传飞书或 ChatGPT |
| cuRobo v2 OpenArm 尝试对照 | 支撑材料 | v001 · 1 版 · 207 KB | [v001](curobo-v2-openarm-mvp/v001/report.md) | 5 次尝试的单环境对照，样本不足以证明总体成功率或性能优劣 | 本地版本归档，未上传飞书或 ChatGPT |
| AutoData 效率优化报告 | 已被取代（→ autodata-efficiency-review） | v001 · 1 版 · 2.6 MB | [v001](autodata-efficiency-report/v001/index.html) | 12 组图表汇总既有实验、内存所有权与并行导出改动；24 条 GPU 对照最终文件吞吐提升约 29.8%，严格终态各 23/24，物理验收未通过 | 本地保存，未上传或发布 |
| 全库 Git 历史差异保留 | 归档 | v001 · 1 版 · 802 KB | [v001](git-worktree-preservation/v001/README.md) | 保存 3 个旧工作树的独有源码与正文，重复成果引用既有归档；缓存和数据留本机，无新增实验 | Git 归档，非运行验证 |

**已归档版本**（移出主树，原文与校验值保存在单独归档中，位置见仓库整理记录）：

- `autodata-efficiency-review` v001–v021 → [autodata-review-v001-v021.zip](https://github.com/eadstry/worldsim-lab/blob/main/docs/repository-cleanup-20261022.md)

<!-- outputs-index:end -->

AutoData 文章历史版本：[v001](autodata-guide/v001/CHANGELOG.md)、[v002](autodata-guide/v002/CHANGELOG.md)。持续编辑文章请使用[博客正文源](../docs/autodata/AutoData-全流程可视化讲解.md)，不要直接修改这些快照。

当前工作树的复现限制及最新生产失败见[过程记录](../docs/process-log.md)。v003 的历史 GPU 验证不代表当前源文件齐全。OpenArm 生产扩展见[维护入口](../workspace-overlays/openarm-production/README.md)，其 8 环境、100 条目标运行已失败退出，尚未完成数据回读验收。

## 保存约定

- 使用 `outputs/<artifact-id>/<version>/`，同一主题沿用稳定 ID，内容修订新增版本。
- 已封存版本的正文、资源和校验值保持不变；交付状态按双端交付规则独立记录。
- 新增工件或版本后运行 `python3 scripts/build-outputs-index.py` 并提交生成结果；CI 会校验索引是否最新。
- 新增工件需在 `config/outputs-status.json` 登记状态、标题与验证范围；不要将“已有文件”或“已封存”写成运行成功。
- 交付包不复制 `workspace-overlays/` 的源码；用 `code-ref.json` 指向 overlay，需要可分发包时放 zip 附件。
- 环境、原始数据集和批量日志保留在其运行或存储位置，不作为报告附件重复堆放。
- 文件存在不等于已提交 Git。提交前使用 `git status --short` 检查新成果及子模块内的独立变更。
