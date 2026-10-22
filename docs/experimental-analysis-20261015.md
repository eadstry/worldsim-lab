# Codex 分析整合实验版本（2026-10-15）

实验分支：`codex/experimental-analysis-20261015`。此版本整合此前已完成的分析、实验记录和复现源码，保留各版本的证据边界。工作树位于 `.worktrees/experimental-analysis-20261015`；原工作目录及其他 worktree 的未提交改动继续保留。

## 已整合内容

| 来源 | 本版本处理 | 阅读入口 |
| --- | --- | --- |
| `codex/pr-readme-frontier`，`47d2c50` | 分支起点，已含 `bfd5ec8` 导出优化、版本管理修复及历史保存补丁 | [生产扩展](../workspace-overlays/openarm-production/README.md) |
| `main`，`34301dc` | 合并自动同步工作流，保留用户指定的本地研究交付规则及新版本管理约定 | [工作区规则](../AGENTS.md) |
| `codex/shared-validation-queue`，`47723c1` | 合并共享 FIFO 队列与测试 | [验证队列](task-queue.md) |
| `codex/openarm-benchmark-demo`，`81149a6` | 合并已提交的 Arena 示例，保留 v001 交付包 | [Arena benchmark](../workspace-overlays/openarm-benchmark/README.md) |
| 主工作目录，`bfd5ec8` 后的未提交成果 | 精确复制内部耗时 v001、证据和复现工具 | [内部耗时对照](../outputs/autodata-v1-internal-timing/v001/index.html) |
| `5b06` worktree，`e650247` 后的未提交成果 | 精确复制 cuRobo v2 升级评估、最小验证、抓取诊断和 overlay | [v2 对照](../outputs/curobo-v2-openarm-mvp/v001/report.md) · [抓取诊断](../outputs/curobo-v2-grasp-diagnosis/v001/report.md) |
| `e476` worktree，`34301dc` 后的未提交成果 | 保留效率图册 v001–v013，附历史 v2 复现脚本及来源记录 | [43 页图册](https://github.com/eadstry/worldsim-lab/blob/007732134bba64e47b52beb489f0c7363429cc1f/outputs/autodata-efficiency-review/v013/charts.pdf) · [GPU 源码分析](https://github.com/eadstry/worldsim-lab/blob/007732134bba64e47b52beb489f0c7363429cc1f/outputs/autodata-efficiency-review/v013/gpu-analysis.html) |
| `c46d` worktree，`34301dc` 后的未提交源码 | 保存 32 条生产吞吐测试工具，标为实验工具 | [生产吞吐测试](../workspace-overlays/openarm-throughput-benchmark/README.md) |

`codex/local-frontier-20261014` 的历史保存清单与补丁已由起点分支保留，manifest 与该分支逐字节相同。其旧实现已被 `bfd5ec8` 的自适应导出覆盖，因此没有再次合并旧分支；保留当前失败记录，不用历史的 `runtime-check-result.json` 通过状态覆盖它。历史整理分支 `codex/tidy-workspace` 不纳入，避免其删除行为影响封存版本。

两个来源都使用 `workspace-overlays/openarm-benchmark`，用途分别为 Arena 评测和 AutoData 生产吞吐。本版本保留 Arena 示例原路径，将生产吞吐工具放到 `workspace-overlays/openarm-throughput-benchmark`。调整后者 README 中的使用路径；另清理 cuRobo overlay 的 `trajectory.py` 文件末尾一个冗余空行，无逻辑修改。上述两项在来源清单中单独标记。

## 检查结论

27 份成果 manifest 的 1087 个 payload 文件哈希一致。导入来源清单记录 1013 个文件的来源路径、源 HEAD、目标路径和 SHA256；原有封存版本未改写。历史 SVG/CSV 及封存代码自带的空白保持原样；本次维护的源码和文档另行通过差异空白检查。最新效率图册为 43 页，HTML 相对资源链接可解析。

内部耗时报告中的最终文件吞吐倍率 `515.768383 / 350.296877 = 1.472375` 与记录一致；生成全局窗口及 execute 平均阶段计时闭合。这是对既有配对记录的复核。该记录为 4 环境、同步与 auto 各 8 条成功样本；不能外推为任意并行度或长期稳态提速。cuRobo v2 小样本对照仍不足以支持替换生产默认后端。

主机测试通过：生产导出 31 项、cuRobo v2 统计/模型/轨迹 7 项、内部计时 4 项、生产吞吐工具 8 项、Arena 示例 12 项，共 62 项。cuRobo v2 使用原有独立 v2 Python；生产导出中需要源码的测试临时只读引用现有 AutoData 工作树，测试结束后移除链接。使用的源码哈希单独记录。初次用 v1 Python 运行 v2 用例以及缺源码检出的测试失败已在对应条件补齐后消除，未安装或更新依赖。

提交前运行 `bash scripts/cloud-check.sh --allow-uninitialized`，涵盖版本管理、共享队列、共享配置以及博客构建与检查。隔离 worktree 有意不初始化三个顶层上游子模块，因此使用该选项；gitlink、`.gitmodules` 和锁定记录保持一致。

本次没有新增 GPU 仿真、训练或 profiling。Arena 示例的主机通过不代表实际策略评测已完成；GPU 利用率的源码分析也不等于设备时间线证据。

## 保留边界

- `ca7b` worktree 中仍在修改的 Arena 可视化代码不纳入本次快照。
- `c46d` 中未封存、没有实验结果的 `openarm-32-episode-benchmark/v001` 占位包不纳入；测试工具单独保留，不宣称完成 32 条生产对比。
- GPU 环境、`.local/`、缓存、原始 HDF5 和批量运行目录留在来源机器。复现仍需配置运行时和资产。
- 历史 v2 重跑脚本保留当时绝对路径，仅作来源与复现参考，不能在新 worktree 直接执行。
- 研究报告保留本地交付记录；Git 分支同步不发布博客，也不上传飞书或 ChatGPT。

## 审阅与复核

[文件来源清单](integration/analysis-20261015-sources.json)、[离线检查结果](integration/analysis-20261015-verification.json)、[源码依赖检查](integration/analysis-20261015-host-source-check.json)、[完整主机检查记录](integration/analysis-20261015-cloud-check.txt)及[成果索引](../outputs/README.md)提供整合范围和证据。

其他机器获取本版本时检出 `codex/experimental-analysis-20261015`，按上述运行边界配置。当前机器可直接进入独立 worktree 查看，原工作目录无需切换分支。
