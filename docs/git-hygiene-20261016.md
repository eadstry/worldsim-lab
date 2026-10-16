# Git 整理记录（2026-10-16）

本次将未提交的研究交付和维护脚本保存到 `codex/git-hygiene-20261016`，仅完成本地提交。原工作目录为 `/home/tangyuan/WorldSimReady-Home`，任务工作树为其下的 `.worktrees/git-hygiene-20261016/`。

原目录位于旧分支 `codex/episode-export-workers`，起点为 `bfd5ec8`。共享提交钩子要求更新的集成祖先、审查策略及干净的上游检出，因此本任务从本机已有集成提交 `e5f361139f19b87ae003558a85b957b907046310` 创建隔离工作树，逐文件比对后复制本次成果，保留集成分支的历史内容。没有切换、合并或清理原工作树。

## 需要提交的文件

| 路径 | 提交内容及理由 |
| --- | --- |
| `.gitignore` | 补充 `*.py[cod]`，覆盖缓存目录之外的 Python 编译缓存 |
| `docs/git-hygiene-20261016.md`、`docs/version-management.md` | 本次归档清单、忽略边界和版本管理入口 |
| `outputs/README.md` | 增加域随机化入口，更新效率复盘图册入口；保留集成分支其他主题 |
| `outputs/autodata-domain-randomization/v001/`、`v002/` | 报告、渲染图片、统计结果、少量位姿样本 `samples.npz` 及封存 manifest；保留 v001 的已知渲染限制 |
| `outputs/autodata-efficiency-review/README.md`、`v014/`、`v015/`、`v017/`–`v021/` | 完整版本交付：正文、图表、构建源码、证据摘要、PDF、DOCX、ZIP、校验记录和 manifest |
| `workspace-overlays/autodata-domain-randomization/` | 运行脚本、报告生成器与使用说明，共 4 个文件 |
| `workspace-overlays/openarm-v1-timing/extend_review_charts.py`、`review_timing_figures.py` | 补充图表和说明的维护源码 |

原目录中的 `outputs/autodata-v1-internal-timing/v001/` 与 `workspace-overlays/openarm-v1-timing/` 其余 7 个文件已与集成基线逐字节一致，在该基线已有提交，不重复制造变更。原目录未检出的效率图册 v001–v013 由集成基线保留；版本编号的缺口不补造。

封存交付中的图片、PDF、DOCX、ZIP 和少量 NPZ 样本是报告的一部分，不能仅因是二进制或生成物而忽略。必须与 manifest 一并保存并校验，不能编辑封存字节以消除生成文件的空白。上述待归档内容约 101 MiB，最大单文件约 7.2 MiB，无需为此次归档引入 Git LFS。

## 需要忽略的文件

| 路径或模式 | 用途及保存方式 |
| --- | --- |
| `/runs/`、`*.log`、`*.telemetry.jsonl`、`*.resources.jsonl` | 原始实验运行、控制台日志和逐条遥测；本地保留，另行备份 |
| `workspace-overlays/openarm-production/runtime/` | 准备后的仿真源码副本、资产及输入；由该扩展的 `.gitignore` 排除 |
| `*.h5`、`*.hdf5`、`*.pt`、`*.pth`、`*.ckpt`、`*.safetensors` | 数据集、模型与检查点；不纳入根仓库 |
| `node_modules/`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`*.py[cod]` | 可重建依赖、环境与缓存 |
| `/.worktrees/` | 独立工作树；其中源码由各自分支提交，不能再次作为父目录文件归档 |
| `/config/.local/`、`.env`、`.env.*`（保留 `.env.example`）、`.aws/`、`.openai/`、`*.pem`、`*.key` | 机器配置、凭据与私钥；不提交 |
| `.codex/`、`.agents/`、`.sites-runtime/`、`.DS_Store` | 本机工具状态、临时运行目录和系统文件 |
| `/workspace-overlays/arena-deliveries/`、`/workspace-overlays/dev-state-snapshot-20261013/`、`/framework-dev/` | 既有本地交付包、恢复快照和退役目录；保持现有排除规则 |

规则只控制未跟踪文件，不会移除已经跟踪的文件，也不会控制子模块内部。不要使用 `git add .` 或强制暂存运行目录；按上表显式暂存。

## 子模块与原目录的保留状态

原目录的 AutoData 包含 `AGENTS.md` 修改、7 个已跟踪 HDF5 的本地删除、未跟踪的 `datasets/` 运行结果，以及嵌套 Arena 的本地修改。根目录 Arena 包含 `AGENTS.md` 修改和嵌套 IsaacLab 的本地修改。这些均不属于本次根仓库提交：不恢复删除、不删除数据、不提交子模块、不改变其忽略设置或 gitlink。

根仓库忽略 `*.hdf5` 不会隐藏 AutoData 内的数据。子模块中已经跟踪的 HDF5 删除也不能通过 `.gitignore` 消除；后续应在明确授权的上游维护任务中处理。根目录的 `git status` 仍会显示这些子模块修改，以及在旧基线下尚未跟踪的成果副本，这不表示新任务分支遗漏归档。原目录副本保留以免影响其他正在使用该目录的任务。

本任务工作树有意不初始化三个上游检出，使用 `--allow-uninitialized`；所有上游锁定引用保持不变。复用本机已有博客依赖的副本，依赖目录保持忽略。提交前运行完整 `cloud-check.sh`、内部计时主机测试和精确暂存树审查。检查覆盖版本完整性、封存 SHA256、主机逻辑及博客构建，不代表重新运行 GPU 实验，也不验证历史外部链接。常见凭据模式扫描未发现匹配，不等于完整秘密检测。

## 后续：整个项目整理与 GitHub 同步

用户随后明确要求同时整理整个项目和推送 GitHub。本节更新前文“仅本地提交、原目录保持旧分支”的交付范围；既有归档提交为 `4a623cd`。

递归上游状态保存在 [20261016 清单](../workspace-overlays/upstream-patches/snapshots/20261016/inventory.json)。18 个顶层及嵌套依赖中，12 个已初始化、6 个未初始化。5 个仓库的已修改文本生成的补丁 SHA256 与既有补丁完全一致，清单引用历史补丁，不重复生成；AutoData 中未跟踪运行结果和各仓库已跟踪文件的本地删除仅记录路径，不作为源码变更提交，也不恢复或隐藏。

原目录迁移步骤为：逐字节核对所有根仓库未跟踪文件均已归档；将列明的成果和脚本路径连同旧成果索引保存到标注为 `before-root-git-migration-20261016` 的 Git stash；在独立工作树完成检查和推送后，释放任务分支并由原目录切换到 `codex/git-hygiene-20261016`。使用正常分支切换，不强制覆盖、不重写历史、不合并其他工作分支。该 stash 是旧工作树的额外恢复点，保留而不自动应用；可通过 `git stash list` 找到它。

切换不递归操作子模块，三个顶层 gitlink 与旧基线完全相同。根仓库预计只保留 AutoData 和 Arena 的子模块脏状态；这两个状态明确保留，不用忽略设置掩盖。后续修改应继续在干净的任务 worktree 中审查和提交。

GitHub 同步范围为 `origin` 上的 `codex/git-hygiene-20261016`，包括集成基线历史、本次完整报告归档和状态清单。其他聊天的独立工作分支不强制合并或推送，`main` 保持原状。GPU 数据、依赖与恢复目录仍需单独备份；Git 推送不代表这些机器数据已上传，不发布博客或改变权限。

迁移前检测到另一个聊天在原目录编写域随机化方法总览，因此等待该轮任务结束后再切换分支。其完成的 `workspace-overlays/autodata-domain-randomization/catalog.py` 和 `outputs/autodata-domain-randomization-catalog/v001/` 也纳入归档；后者包含目录 JSON、交互 HTML 片段、源码版本、验证记录和封存 manifest。该成果是 45 类方法的源码清点与示意，29 个引用源码文件的 SHA256 已核对一致，没有新增 GPU 验证。等待期间恢复原目录的旧成果副本，原恢复 stash 保留；最终迁移另建同名前缀的恢复点，包含此批新文件。
