# 已完成任务的工作树整合（2026-10-23）

本次从 `origin/main` 的 `f64adf2` 建立 `codex/worktree-integration-20261023`，核对 53 个本地任务分支。新完成成果使用 merge commit 合入整合分支；已由前次快照导入的内容逐项登记，不再次合入旧基线。主目录原 `main` 为 `d2f3796`，已快进 65 个提交到上述远端基线。

本次交付为整合分支及面向 main 的 PR。main 晋升仍需单独批准；主机检查和本代理自审不算独立审阅批准。未强推、删除分支、更新上游 pin、安装仿真依赖、发布网站或重新执行 GPU 仿真。

## 本次合入的成果

| 来源分支 | 来源提交 | 内容与边界 |
| --- | --- | --- |
| `codex/openarm-gs-render` | `53522f4` | OpenArm 的 `desk.yaml` / `gs_table.yaml`、27 项配置来源哈希及高斯 RGB 渲染示例 |
| `codex/openarm-gs-production` | `f2421cd` | 已完成的单条 GS SkillGen 生产、独立物理回放及外部机位视频；不是成功率基准 |
| `codex/openarm-gs-wrist-video` | `8e7203f` | 同一轨迹的左右腕原始 RGB 视频，保留右腕近黑及采样时序限制 |
| `codex/autodata-ray` | `95930ab`、`13d6c2e`、`df0d693` | 有界 Ray actors、官方 LeRobot v3 直接导出、资源/生产对照及 PDF；HDF5 仍是默认路径 |
| `codex/experiment-chartbook-vector-20261022` | `f051c4e` | 新增封存图册 v002，19 图矢量重绘；v001 和已有实验数据保持原字节 |
| `codex/openarm-gs-head-video` | `2b1fe90` | 机器人机身固定的虚拟头部预览相机、同轨迹回放与完整视频解码；不是原有标定传感器 |

头部视频任务在本次开始时仍处于运行中。本次保持其原目录不动，等待原任务结束并提交后，再合入该提交。其他合并冲突集中在 `docs/README.md`，保留各方条目；腕部与头部报告的跨 worktree 绝对链接已改为整合目录内的相对链接，原报告结论、图片和视频不改写。

两套 OpenArm 场景的版本管理入口现位于 [普通桌面布局](../workspace-overlays/openarm-gs-render/configs/openarm_autodata/tasks/pick_place/configs/scenes/desk.yaml) 与 [高斯桌面布局](../workspace-overlays/openarm-gs-render/configs/openarm_autodata/tasks/pick_place/configs/scenes/gs_table.yaml)。它们由任务自己的 `scene_layout.py` 加载，不是 AutoData 通用 `EnvironmentProfile` 的新增字段。这里的 configs 是来源参考快照；运行依赖仍按 [GS 生产记录](openarm-gs-production-20261023.md)准备，不能只加 PYTHONPATH 就视为完整安装。

## 已收录的旧分支

此前 [2026-10-22 分支清单](integration/branches-20261022.json) 已登记的快照沿用原收录状态。对 Git 祖先关系仍显示未合并的其他分支，另核对内容：

- `experiment-chartbook-20261020`：图册工具和 v001 已在 PR #16 原字节导入。
- `openarm-next-experiments-20261020`：7 个相机与导出诊断文件已在 PR #16 原字节导入。
- `github-sync-20261020`：成果已在 PR #14/#19 适配导入；不恢复旧版本策略、旧计划结论或已退役网站。
- `recovered-codex-session-index`：两份会话文本已存在，现行版本仅清除了失效本机和 plugin 链接。

全部本地任务分支的 SHA 与处理分类见 [逐工作树和分支清单](integration/git-worktrees-20261023.json)。仅凭 `git branch --merged` 不能判定早期快照导入遗漏。

## 主目录与本地数据保存

主目录的原暂存文档、AGENTS 文档规则及报告移动，先保存为 Git stash 和二进制差异补丁。LeRobot 文档、3 张图和移动后的报告与最新 main 相同；本次不重复提交。原索引中独有的历史文档入口在新索引保留，原 AGENTS 的文档命名、注册与修订规则迁入当前版本，并保留 main 的单一编辑源及不部署网站约定。

- stash SHA、补丁目录和原始状态记录在清单的 `preservation` 中；恢复点不自动删除。
- 开始时 59 个 worktree HEAD 保存为本机 `refs/archive/worktree-integration-20261023/*`。它们是本机恢复引用，不宣称已远端备份。
- 主目录 AutoData 的 7 个数据文件变化及嵌套子模块变化保持原位，不暂存、不清理。主目录仍会显示子模块本地变化，这是保留状态，不是整合失败。
- `runs/`、`runtime/`、原始资产 ZIP、虚拟环境和数据集不加入本次 Git 提交；已有 GPU 结果只是合入其历史证据，不算重新验证。

## 安全清理

共移除 29 个旧 worktree，保留 30 个（含主目录和本次整合目录）。移除前重新检查实时 Git 状态：9 个目录本来就没有未跟踪或忽略内容；另 20 个目录仅含 `node_modules`、`__pycache__` 等可重建缓存，先清理这些缓存，再通过普通 `git worktree remove` 移除。符号链接只移除链接，不删除其目标。

未使用 `--force` 或 `git clean`，未删除任何分支。保留的旧 worktree 含资产、运行结果、机器配置、环境或已初始化子模块；为保全这些本地内容，本次不强制移除。合并 Git 提交不会转移或备份这些内容。

## 审查和验证

- 各 merge commit 提交前均生成与其父提交、分支和暂存树绑定的审查回执；最终整合记录另作提交。
- `bash scripts/cloud-check.sh --allow-uninitialized`：42 项脚本测试、8 项共享配置测试，以及版本、封存哈希、成果索引和文档链接检查。
- production 主机套件：53 项全部通过，包含官方 LeRobot 写出、数值和视频回读；未用缺少依赖的系统 Python 跳过测试。
- 使用机器已有 `runs/lerobot-v3-conversion-env/bin/python`，显式设置既有 FFmpeg 库路径，并通过 `WORLDSIM_SOURCE_ROOT` 只读引用主目录源码；没有安装或更新环境。初次检查因 Python/源码/动态库路径缺失失败，修正路径后重新生成回执。
- 27 项 GS 配置 SHA256 与来源清单一致。27 个封存 manifest、547 个 payload 文件通过仓库完整性检查；旧版本不改写。
- 隔离整合目录有意不初始化三个顶层上游，故使用 `--allow-uninitialized`；这不代表依赖运行已通过。审查覆盖源码、并发与数据所有权、依赖来源、测试和证据边界，不是独立 reviewer 批准。
