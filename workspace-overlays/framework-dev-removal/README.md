# 开发克隆移除记录

`framework-dev/` 已按用户要求移除。这里仅保存两份源码差异补丁、原目录说明和文件去向清单，不包含完整开发克隆。

`manifest.json` 记录原分支、基线提交、补丁 SHA256，以及每个保留文件的位置和 SHA256。已有相同副本的文件继续使用原有恢复快照或上游目录；7 个独有预览、辅助脚本及日志位于已忽略的 `runs/recovered-framework-dev/`。缓存和可再生构建产物不保留。

`README-original.md` 和 `RLinf-placeholder.md` 是历史原件，其中的旧路径和开发建议不再适用。需要并行开发时遵循 `docs/version-management.md`，不要重建重复克隆目录。恢复旧改动前先核对补丁记录的基线提交，并在独立开发 worktree 中审阅，不能直接应用到当前锁定的不同提交。
