> 当前归档位置与范围见[2026-10-22 仓库整理记录](repository-cleanup-20261022.md)。以下保留历史操作记录；原 Release 下载入口已停用，不能据此认定实验数据备份完整。

# 服务器停服前的 GitHub 恢复入口

创建日期：2026-10-22。用户要求保存当前目录全部更改，并选择后台执行大文件备份。本记录描述恢复方法；完整性以 Release 的完成回执为准。

| 内容 | 远端位置与状态 |
| --- | --- |
| 文档、目录规则及原报告移动 | `codex/github-sync-20261022`，提交 `0526209` 已推送；后续提交保存本恢复说明 |
| 6 个尚未出现在 origin 历史中的本地提交 | Release 的 `local-history.bundle`，6,257,125 字节，GitHub SHA-256 已核对 |
| 50 个 worktree、67 个仓库的 HEAD、补丁和暂存状态 | Release 的 `worktree-state.tar.gz`，541,230 字节，GitHub SHA-256 已核对 |
| 未跟踪和被忽略的实验文件 | 后台上传：16,137 个路径、12,182 个唯一内容对象、77,313,524,927 字节未压缩内容；以 `manifest.json` 和各组回执核对 |

私有备份入口：`archive-server-shutdown-20261022`（原 Release）。不会发布博客或变更访问权限。上传过程中出现的 Release 不代表备份完成。

## 判断后台任务是否完成

主机命令：

```bash
python3 scripts/task-queue.py show 301
python3 scripts/task-queue.py logs 301
python3 scripts/task-queue.py show 302
python3 scripts/task-queue.py logs 302
```

301 是实际压缩及上传任务；302 是失败重试、补充仓库备份、远端校验和完成回执提交任务，在同一队列随后执行。任务由队列 worker 执行，退出聊天后继续运行；关闭服务器、结束容器或终止 worker 会中断任务。

实验文件上传以 `summary.json` 的 `complete: true`、空 `errors`、全部分组回执及文件大小/SHA-256 为依据。整个任务还须等待 302 成功，远端分支出现 `docs/server-shutdown-recovery-20261022.json` 完成回执，且 Release 说明更新为 `Backup complete`。每个 `group-NNNN.json` 标识一个已完整上传、可独立恢复的组。仅有 `.part-*` 文件而缺少该组 JSON 回执的组尚未完成。压缩和上传由共享队列调度，不启动 GPU 仿真。

## 恢复 Git 历史与现场

先克隆 GitHub 仓库，下载 Release 附件。不要从网页直接复制补丁。

```bash
git clone https://github.com/eadstry/worldsim-lab.git WorldSimReady-Home
cd WorldSimReady-Home
git fetch origin codex/github-sync-20261022
# 从下载附件的位置读取：
git bundle verify /absolute/path/to/local-history.bundle
git fetch /absolute/path/to/local-history.bundle 'refs/heads/*:refs/remotes/shutdown/*'
```

bundle 是增量备份，要求原仓库已包含提交 `4a45d64fc002d16930906c6bd521750dadf0d479` 与 `dedb148b151abe81542503cfe4e135a3771f5ed6`；这两个提交在本次备份时均可从 origin 引用到达。`metadata/worktrees.json` 记录原目录、标签和准确 HEAD。为需要恢复的 worktree 检出对应 HEAD，再依据各仓库编号的补丁恢复现场：先 `git apply --index NNN-index.patch`，再 `git apply NNN-unstaged.patch`。空补丁跳过；`NNN-head.patch` 是整体内容核对副本，不要在前两份补丁之后重复应用。

上游目录不作提交、不更新 pin。AutoData 的 7 个 `.hdf5` 文件只是 132 字节的 LFS 指针，已确认与 HEAD 字节相同；它们不包含原始训练数据。四个空的嵌套 partial clone 仅登记 HEAD 和空检出状态，未为备份下载其缺失对象。

## 恢复实验文件

下载 `manifest.json`、所有已完成组的 `group-NNNN.json`、对应 `.part-*` 和 `restore-worldsim.py` 到同一目录。恢复程序会先核对每个分片的 SHA-256 和大小，再逐对象核对 SHA-256，拒绝覆盖现有文件，并保留文件权限及修改时间。

```bash
python3 restore-worldsim.py --assets-dir /absolute/path/to/downloads --dest /absolute/path/to/recovered
```

也可使用仓库中的 [恢复程序](server-shutdown/restore-worldsim.py)。目标目录按 `main/` 和 `worktrees/<名称>/` 展开，先在空目录恢复，再与对应 Git 检出合并。多个路径共享相同内容时分别恢复。符号链接只保存链接文本，不跟随访问；换机后应检查指向外部位置的链接。

嵌套在忽略目录内的另外五个独立 Git 仓库由 `supplemental-repositories.tar.gz` 附件补充保存，若该附件尚未出现，其补充备份尚未完成。

## 范围与限制

- 不上传凭据、私钥、已安装的虚拟环境、`node_modules` 和常见缓存。逐路径排除清单/汇总在 manifest 内；匹配凭据模式的文件不会上传。
- 原目录及所有原 worktree 的暂存状态、上游 pin、封存成果均保留；不会因备份进行 reset、清理或合并 main。
- `/data` 不属于当前目录。本次访问其证据包发生阻塞，未计入这份备份；外部符号链接指向的数据也未计入。
- 完成备份不表示仿真、训练或历史研究结论经过重新验证。主机检查、链接检查和博客构建已用于此前文档提交；恢复程序另用两个独立压缩组验证内容校验、重复对象恢复、符号链接和拒绝覆盖行为。
