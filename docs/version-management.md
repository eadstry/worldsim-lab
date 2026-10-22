# 工作区版本管理

本仓库管理上游版本引用、本地扩展、研究资料和交付快照。Git 提交保存可迁移的源码与记录；GPU 环境、资产准备目录和数据集另行保存。并行修改使用根仓库的分支和 worktree。

## 内容归属

| 内容 | 维护位置 | 保存方式 |
| --- | --- | --- |
| 上游代码 | `AutoData/`、`IsaacLab-Arena/`、`RLinf/` | 子模块 gitlink、`.gitmodules`、`upstream-lock.json` 三者一致 |
| 本地实现 | `workspace-overlays/`、`scripts/`、`config/` | 根仓库提交；不在上游工作树中保存新增实现 |
| 上游已有修改 | `workspace-overlays/upstream-patches/` | 补丁、原提交和 SHA256；不自动应用 |
| 研究说明 | `docs/` | 根仓库提交，主题索引提供入口 |
| 交付成果 | `outputs/<artifact-id>/vNNN/` | 新版本新增目录；已封存内容和来源不改写，交付回执可独立更新。确需控制仓库体积时，旧版本整体移出主树，单独备份归档文件并在该 artifact 的 `ARCHIVE.md` 登记 |
| 成果索引 | `outputs/index.json`、`outputs/README.md` 的表格、`config/outputs-status.json` | 前两者由 `scripts/build-outputs-index.py` 生成；状态、标题与验证范围在 status 文件登记 |
| 数据和运行环境 | `runs/`、扩展 `runtime/`、`config/.local/` 等 | 本地保存和单独备份，不加入 Git |

根目录 Arena 与 AutoData 内嵌 Arena 是不同依赖关系，按各自父仓库锁定，不合并目录。`framework-dev/` 已于 2026-10-14 按用户要求移除；源码差异、原分支与文件去向见 `workspace-overlays/framework-dev-removal/manifest.json`。现有恢复快照继续保留本地，新开发使用分支和 worktree。

本次文件清单、忽略边界与原工作树保留状态见 [2026-10-16 Git 整理记录](git-hygiene-20261016.md)。

覆盖所有工作树的后续整理见 [全库工作树记录](git-worktrees-20261016.md)；不能只凭主目录干净就认定整个项目库已整理。

## 交付包与代码引用

`outputs/<artifact-id>/vNNN/` 保存交付所需的正文、图表与数据。**不要**把 `workspace-overlays/` 的源码整份复制进去：副本会与单一事实来源分叉，而封存后无法再同步修正。

- 包内需要指明实现位置时，写 `code-ref.json`，例如：
  ```json
  {"overlay": "workspace-overlays/openarm-benchmark", "commit": "<sha>", "entrypoint": "run.py", "notes": "评测入口，代码以 overlay 为准"}
  ```
- 需要给外部一份可直接运行的包时，在版本目录放 `*.zip` 附件，并在该版本 `README.md` 写清解压后的入口；zip 是交付物，源码仍以 overlay 为准。
- `check-version-management.py` 拒绝 2026-10-20 起封存版本中的 `code/` 目录。此前的 `curobo-v2-grasp-diagnosis`、`curobo-v2-openarm-mvp`、`openarm-benchmark` v001/v002 保留原有副本，仅作历史参考，不再更新。

## 提交与检查

```bash

# 当前机器有意不初始化 RLinf 时使用此选项；完整环境省略它。
bash scripts/cloud-check.sh --allow-uninitialized

# 根仓库启用提交检查。所有根仓库 worktree 共用此 Git 设置。
python3 scripts/review-workspace.py install

# 按任务显式暂存，检查差异再提交。子模块中的数据不会随父仓库提交保存。
git add <本次任务的文件路径>
git diff --cached --stat
git diff --cached --check
python3 scripts/review-workspace.py prepare --allow-uninitialized \
  --review-note "说明本次差异审查、风险和已解决的问题"
git commit -m "Describe the change"
```

`check-version-management.py` 检查上游 URL、索引 gitlink、锁定提交、已初始化子模块 HEAD、嵌套版本偏移、成果文件 SHA256 和暂存文件边界。`build-outputs-index.py --check` 校验成果索引与各 `manifest.json` 一致，`check-doc-links.py` 校验 Markdown 相对链接（跳过上游子模块、保留快照与已归档版本）。暂存文件还有未暂存修改时要求重新审阅和暂存，避免检查版本与提交版本不同。已封存 manifest 的内容元数据不可改写。历史版本默认保留；确需移出主树时，必须先单独备份归档文件、在对应 `ARCHIVE.md` 登记取回方法，并保证 `check-version-management.py` 仍能追溯封存快照。

默认将未保存的上游修改显示为警告，以保留已有工作。需要验证完全干净的源码基线时，执行：

```bash
python3 scripts/check-version-management.py --require-clean-upstream
```

提交钩子验证绑定当前父提交、分支和暂存树的审查回执，并复核版本约束；回执由完整主机检查及相关模块测试全部通过后生成。共享绝对路径钩子覆盖所有 worktree，旧 worktree 不能因缺少 `.githooks/` 而跳过门禁。目录名检查用于阻止常见数据、模型和凭据误提交，不替代人工检查文件内容。根仓库 `.gitignore` 不控制子模块自己的文件跟踪规则。

`cloud-setup.sh` 在初始化前检查现有子模块是否干净且位于锁定提交，随后仅初始化顶层子模块、安装提交门禁并检查。它不再向上游复制设计文档。设计文档从 `workspace-overlays/AutoData/agentic_design/` 阅读。

## 并行开发

```bash
python3 scripts/review-workspace.py start topic
cd .worktrees/topic
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init AutoData IsaacLab-Arena
bash scripts/cloud-check.sh --allow-uninitialized
```

新 worktree 从提交创建，不复制原目录未提交的文件、GPU 环境、准备好的资产或运行数据。先提交需要复用的源码，再建立 worktree。各 worktree 使用独立运行目录；启动 GPU 任务前核对该 worktree 的依赖和资产路径。完成后先提交工作，再执行 `git worktree remove .worktrees/topic`；不要强制删除含未保存内容的 worktree。

## 当前运行边界

共享配置的历史 v003 依赖当时 AutoData 工作树中的 `openarm_autodata`，这些文件不在锁定的上游提交中。当前目录缺少所需的 `left_env_cfg.py`；启动器现在提前报出缺失来源，不再生成不完整的溯源计划。主机测试使用独立夹具，不表示该运行依赖已恢复。

生产扩展是另一条明确的入口：`workspace-overlays/openarm-production/prepare.py` 从校验过 manifest 的原始 ZIP 准备独立 `runtime/`，不会自动替换共享配置的历史环境。原始 ZIP SHA256 为 `afa092e722605cb5b12115ebcb70317565360976c571c68f1e09e6ad2735aa48`；准备目录、资产和 HDF5 仍需单独备份。恢复或统一这两个运行入口后，需要重新进行 GPU 验证，不能沿用旧报告的通过结论。

问题与改进状态见 [过程记录](process-log.md)。任务结束后默认按[自动提交与审查规则](automatic-version-review.md)检查、提交并推送当前任务分支；用户明确要求仅本地、不提交或不推送时遵守该要求。文档统一存放在 `docs/`，入口为 `docs/README.md`。
