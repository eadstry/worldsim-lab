# 成果索引

下表列出当前本地保存的最高版本，便于阅读；“最高版本”不表示已完成运行验证或双端交付。范围与交付状态来自各版本的 `manifest.json`，本次目录整理没有重新验证外部链接或运行仿真。

| 主题 | 当前阅读入口 | 内容与验证范围 | 已记录交付情况 |
| --- | --- | --- | --- |
| AutoData 全流程文章 | [v003 正文](autodata-guide/v003/report.md) · [HTML](autodata-guide/v003/index.html) · [记录](autodata-guide/v003/manifest.json) | 文章及飞书排版快照；没有新增仿真实验 | 飞书记录为 verified；GPT 为 blocked_destination |
| Arena 示例运行与使用说明 | [v001 正文](arena-examples-guide/v001/report.md) · [记录](arena-examples-guide/v001/manifest.json) | 静态源码说明，运行命令需在适当 GPU 环境验证；保留写作时的环境观察 | 飞书、GPT 均为 blocked_destination |
| Arena RoboLab 配置解耦 | [v001 正文](arena-robolab-config-guide/v001/report.md) · [配置](arena-robolab-config-guide/v001/configs/) · [记录](arena-robolab-config-guide/v001/manifest.json) | 场景、任务和评估配置说明；未执行仿真或完整 schema 验证 | 飞书、GPT 均为 blocked_destination |
| AutoData / Arena 共用配置 | [v003 GPU 验证](autodata-arena-shared-config/v003/report.md) · [实际配置说明](../config/README.md) · [记录](autodata-arena-shared-config/v003/manifest.json) | 用户授权现有原生环境 GPU 验证；环境/动作/成功判据比较通过，Arena 入口短测通过 | 用户要求仅本地保存，未上传 |
| AutoData 效率优化报告 | [v001 图文报告](autodata-efficiency-report/v001/index.html) · [PDF](autodata-efficiency-report/v001/AutoData-效率优化报告.pdf) · [证据](autodata-efficiency-report/v001/evidence.json) | 12 组图表汇总既有实验、内存所有权与并行导出改动；24 条 GPU 对照最终文件吞吐提升约 29.8%，严格终态各 23/24，物理验收未通过；本次未新增 GPU 实验 | 本地保存，未上传或发布 |

AutoData 文章历史版本：[v001](autodata-guide/v001/CHANGELOG.md)、[v002](autodata-guide/v002/CHANGELOG.md)。持续编辑文章请使用[博客正文源](../private-blog/content/autodata/AutoData-全流程可视化讲解.md)，不要直接修改这些快照。

当前工作树的复现限制及最新生产失败见[过程记录](../docs/process-log.md)。v003 的历史 GPU 验证不代表当前源文件齐全。OpenArm 生产扩展见[维护入口](../workspace-overlays/openarm-production/README.md)，其 8 环境、100 条目标运行已失败退出，尚未完成数据回读验收。

## 保存约定

- 使用 `outputs/<artifact-id>/<version>/`，同一主题沿用稳定 ID，内容修订新增版本。
- 已封存版本的正文、资源和校验值保持不变；交付状态按双端交付规则独立记录。
- 新增版本后更新本索引，说明验证范围；不要将“已有文件”或“已封存”写成运行成功。
- 环境、原始数据集和批量日志保留在其运行或存储位置，不作为报告附件重复堆放。
- 文件存在不等于已提交 Git。提交前使用 `git status --short` 检查新成果及子模块内的独立变更。
