# 多 worktree 验证任务队列

同一主机、同一用户的 worktree 共用一个 FIFO 队列。通过 `scripts/task-queue.py` 提交 GPU 仿真、训练、性能测试及其他需要独占资源的验证命令，一次只运行一个任务。只依赖 Linux 和 Python 标准库；提交后自动启动调度进程，排空队列后退出。

## 提交与查看

在待验证的 worktree 内执行，命令必须放在 `--` 后：

```bash
python3 scripts/task-queue.py submit --name cloud-check --timeout 1800 -- bash scripts/cloud-check.sh
python3 scripts/task-queue.py list
python3 scripts/task-queue.py show 1
python3 scripts/task-queue.py logs 1
python3 scripts/task-queue.py wait 1
python3 scripts/task-queue.py cancel 2
```

`submit` 输出任务 ID；`wait` 成功返回 0，失败、取消、超时或中断返回 1。`cancel` 只取消尚未开始的任务，不终止正在运行的仿真。`show` 给出命令、工作目录、提交时的 HEAD、是否有未提交修改、退出码和日志路径。stdout/stderr 合并保存。

旧 worktree 尚无脚本时，可以使用已有脚本的绝对路径，在旧 worktree 中提交；默认工作目录仍是提交时的当前目录。也可以显式指定 `--cwd /path/to/worktree`。环境变量在提交时保存，后续任务不会误用前一个 worktree 的环境。Python 环境应通过绝对解释器路径或显式激活命令选择。

GPU 任务使用原有入口，例如已配置好运行环境的 worktree：

```bash
python3 /path/to/task-queue.py submit --name autodata-auto --timeout 7200 \
  --cwd /path/to/ready-worktree -- \
  bash workspace-overlays/openarm-production/run-local.sh <原任务参数> --export-workers auto
```

请替换路径和原任务参数。队列不准备 Isaac Sim、资产或 GPU 环境。该例没有执行 GPU 验证。

## 共享状态与恢复

默认状态目录为 `${XDG_STATE_HOME:-~/.local/state}/worldsimready/task-queue`，保存 SQLite、锁和每个任务的日志，权限为目录 0700、文件 0600；环境快照可能包含凭据，仅在本机保存。不要提交或分享状态目录。

`WORLDSIM_TASK_QUEUE_DIR` 或全局 `--queue-dir` 可指定共享位置。所有竞争同一资源的 worktree 必须使用同一目录；不同目录是独立队列。目录必须属于当前用户且权限为 0700。队列使用本机文件锁，不支持跨主机或 NFS 调度，也不隔离不同用户。

机器重启后任务不会自动启动。先查看状态，再启动调度器：

```bash
python3 scripts/task-queue.py list
python3 scripts/task-queue.py worker
```

也可用 `submit --no-start ...` 只入队，之后手动 `worker` 排空。发现上次未完成的 `running` 记录时会标记 `interrupted`，不会自动重试，避免重复写数据。已排队任务继续运行。运行命令继承队列锁；调度器意外退出时，下一个调度器会等该命令退出后再继续。正常终止和超时会清理该命令的进程组。

## 使用边界

- 仅协调通过此队列提交的任务；启动前先等待现有直接启动的 GPU 任务结束。不会扫描、停止或接管已有任务。
- 提交的是命令与环境，不是源码快照。HEAD 和脏状态只用于溯源；等待期间请保持该 worktree 的源码不变，最好先提交。
- 每个任务使用独立输出目录，例如 `runs/<任务名>/`，避免串行任务仍覆盖旧结果。
- 命令必须在前台运行，不使用 `nohup`、`&`、后台 daemon 或脱离进程组的子进程。队列不执行任意命令的沙箱隔离。
- 不替代 Git 同步：其他 worktree 需要 fetch 后选择性引入本任务提交，或共用脚本的绝对路径。

调度器测试使用临时目录和 CPU 小任务，覆盖多个提交者、FIFO、失败继续、超时清理、排队取消、不同工作目录和环境、调度器崩溃恢复；不能据此声称 GPU 仿真已通过。
