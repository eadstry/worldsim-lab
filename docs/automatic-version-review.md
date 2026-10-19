# 自动版本提交与审查

默认在每个实现任务完成后，审阅本次差异、运行检查、提交并推送当前任务分支。由执行任务的代理调用命令，Git 钩子负责阻止未经检查的提交和推送，GitHub Actions 在远端再次运行主机检查。不会监听文件变化后立即提交，也不会自动合并到 main。

用户明确要求仅本地、不提交或不推送时，停止对应自动同步。研究平台上传、博客发布、上游版本更新、GPU 执行均不随 Git 同步发生。

## 新任务的基线

版本策略保存在 `config/version-policy.json`。默认起点为 `origin/main`，最低祖先是 2026-10-20 的分支收敛提交 `7420954`（该提交把此前各研究分支合并为一次快照导入，旧分支链已归档到 Release `archive-branches-20261020`）。起点同时必须包含自动审查策略。先 fetch，再创建任务：

```bash
git fetch origin
python3 scripts/review-workspace.py start camera-profile
cd .worktrees/camera-profile
```

命令解析起点的具体 commit 后创建 `codex/camera-profile`，不会复制未提交文件或机器环境。输出记录具体基线 SHA。`--base REF` 可显式选取包含策略的更新基线。

历史对照和只读分析可以保留原 revision。旧基线工作树的自动提交会被拒绝：保留原目录和未提交内容，将本次源码差异审阅后迁移到新任务分支。正在运行的目录不切换、不 rebase、不清理。

## 审查与任务结束

代理先审阅完整差异，具体检查功能行为、边界和错误处理、并发与数据所有权、依赖来源、测试是否覆盖风险，以及报告是否超出证据。高严重性问题未解决时不提交。审查说明应写具体内容；这是差异自审记录，不是独立人工或第二个 AI 的批准。

推荐任务结束命令，显式列出本次文件或目录：

```bash
python3 scripts/review-workspace.py finish \
  --message "Improve camera profiling" \
  --review-note "已检查计时窗口、异常恢复及异步回执语义，未发现未解决的高严重性问题" \
  --allow-uninitialized \
  workspace-overlays/camera-profile docs/camera-profile.md
```

该命令拒绝已有暂存内容、根目录整体暂存和机器数据路径。依次暂存显式路径、检查、生成回执、提交、推送。失败时保留文件和暂存状态；推送失败保留本地提交。单独运行时需配置本机真实 Git 提交身份，脚本不代猜身份。

已有暂存内容或需要分步处理时：

```bash
git diff --cached --stat
git diff --cached
python3 scripts/review-workspace.py prepare \
  --allow-uninitialized --review-note "具体差异审查结论与剩余限制"
git commit -m "Describe the reviewed change"
git push -u origin "$(git branch --show-current)"
```

检查在当前工作树运行，因此暂存之外不得有未暂存的跟踪修改或未忽略的新文件；存在无关修改时，应使用独立 worktree，不自动暂存无关内容。博客构建如改变了未暂存的 dist，需审阅并显式暂存生成物后重新 prepare。

超过 100 个变更文件默认阻止提交，优先拆分。确需导入完整封存成果时，使用 `--large-change-reason` 记录原因；这不会跳过哈希或测试。封存 outputs 保持原生成字节，行尾空白检查作用于其他维护文件。

## 自动检查范围

| 环节 | 门槛 |
| --- | --- |
| 分支 | `codex/`，包含最低整合祖先及策略文件；拒绝 detached HEAD、main、release 分支 |
| 暂存范围 | 拒绝运行数据、模型、凭据文件名、`.local/`、runtime、整体根目录和上游 pin 更新 |
| 版本完整性 | 上游 URL/gitlink/锁定一致、已初始化上游干净、封存文件哈希正确、历史版本未删除或重封 |
| 基础检查 | `cloud-check.sh`：版本管理、成果索引与文档链接一致性、审查门禁和共享队列测试、共享配置测试、博客构建及完整性检查 |
| 相关模块 | 对修改 Python 的 production、cuRobo v2、内部计时、生产吞吐、Arena benchmark 自动运行对应主机测试 |
| 内容一致 | 审查前后 HEAD、分支、Git 暂存树一致；提交和推送时再次匹配 |
| 推送 | 仅当前已审查分支、指定 origin；拒绝其他目标、远端删除及非 fast-forward 历史 |

`--allow-uninitialized` 只用于有意不检出的上游，且会写入回执。依赖源码的测试仍可能失败，不能用该选项代替源码或 GPU 环境。已初始化但有本地修改的上游会阻止正式自动提交；不要为通过检查清理原工作树，应另建隔离检出。

主机测试需要现有兼容 Python。可在机器本地设置 `WORLDSIM_REVIEW_PYTHON` 和 `WORLDSIM_V2_REVIEW_PYTHON` 为绝对解释器路径；不把机器路径提交到策略文件，不自动安装或更新仿真依赖。代码路径过滤不能替代凭据内容审查。

回执保存在每个 worktree 的 Git 元数据 `workspace-review.json`，记录审查说明、父提交、暂存树、分支、检查命令、时间与范围。修改暂存内容、切换分支或更换父提交后必须重新 prepare。它不会被打包到源码，也不代表 GPU 仿真通过。

## 共享钩子与 GitHub

从包含策略的任务或实验整合分支安装：

```bash
python3 scripts/review-workspace.py install
```

安装器把门禁代码放到本机共享 Git 元数据的 `workspace-hooks/`，将 `core.hooksPath` 设置为绝对路径。因此同一仓库的旧 worktree 也会执行门禁，缺少策略或基线过旧时给出迁移错误。安装器同时设置仓库级 `pull.ff=only`、`push.default=simple` 和 `fetch.prune=true`，不改全局 Git 配置。每台机器分别安装；共享门禁代码升级后重新安装。

远端工作流 `.github/workflows/workspace-review.yml` 在 codex 分支推送和 PR 时运行。只使用读权限，不准备 GPU、上传研究报告或发布站点。它检查差异边界、封存历史及基础主机测试；依赖本机仿真环境的模块测试和 GPU 验证仍由本地对应流程负责。工作流采用官方 [checkout v6](https://github.com/actions/checkout/tree/v6) 和 [setup-node v6](https://github.com/actions/setup-node/tree/v6)。

Git 钩子是本机合作约定，可以被人为绕过；增加工作流也不等于已经开启 GitHub 分支保护。main 的远端强制门槛应在仓库设置中另行要求 `Workspace review / host-review` 成功、PR 审阅通过，并禁止强推。当前 main 尚未接入本整合版本，不能声称这些远端保护已经生效。

合并功能分支时，先保存各来源提交，再审查合并结果，运行同一套检查并提交 merge commit。报告快照另作提交以便审阅和回退。冲突解决后不沿用合并前的回执。main 的稳定晋升保留单独的 PR/批准流程。
