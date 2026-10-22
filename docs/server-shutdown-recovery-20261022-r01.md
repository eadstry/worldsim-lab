# 服务器停服备份：大文件改由用户本地保存

创建日期：2026-10-22。本记录取代[此前后台上传方案](server-shutdown-recovery-20261022.md)中有关实验数据上传和完成标志的安排。用户明确要求大文件不上传 Git，由用户自行保存到本地。

- 已终止上传任务 301，并在其退出前取消收尾/重试任务 302；不会自动恢复大文件上传。
- 已推送的源码、文档和 Git 历史备份保留。实验大文件没有加入 Git 提交。
- 本次 GitHub Release 中已经创建的实验数据分包予以清理；Release 保留历史 bundle、工作树补丁和文件清单，并明确标记为不包含完整数据备份。
- 本机原始文件、worktree、上游目录及暂存状态均保留，不执行清理。用户须在停服前自行复制所需大文件。

## 本地取回入口

原始大文件主要在主目录 `runs/`、各 worktree 的 `runs/`，以及 `workspace-overlays/` 中被忽略的运行数据目录。另有位于 `/home/tangyuan/.codex/worktrees/` 的旧 worktree 数据。不要只复制主仓库内的 `runs/`。

文件盘点清单在本机 `/tmp/worldsim-shutdown-20261022/manifest.json`，记录实际绝对路径 `source`、大小和 SHA-256；同一清单也保存在 [GitHub Release](https://github.com/eadstry/worldsim-lab/releases/tag/archive-server-shutdown-20261022) 的 `manifest.json` 附件中。清单包含 16,137 个路径，12,182 个唯一内容对象，共 77,313,524,927 字节唯一内容；它不是数据文件本身。

临时压缩分包在 `/tmp/worldsim-shutdown-20261022/`，仅为部分压缩现场，不可替代完整原始文件。上述 `/tmp` 路径也会随服务器销毁丢失。

凭据、已安装环境和缓存未进入上传范围。`/data` 及外部符号链接的目标不在本次清单覆盖范围内，用户应按需单独保存。此次操作未执行 GPU 验证。
