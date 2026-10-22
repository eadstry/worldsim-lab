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

## 单环境控制器的多进程并行

单进程支持向量化的任务优先设置其 `num_envs`；G1 PINK 当前明确限制一个环境，
不能只删除断言。可将独立环境进程交给同一个队列任务监督：

```bash
python3 scripts/task-queue.py submit --name parallel-environments --timeout 1800 -- \
  python3 scripts/parallel-environments.py --manifest /absolute/path/to/manifest.json \
  --output /absolute/path/to/new-batch-output --workers 16 --gpu-monitor \
  --worker-mib 6000 --reserve-mib 4096 --cpu-threads 2 --kit-threads 4 --job-timeout 600
```

manifest 为 `{"jobs": [{"name": "seed-1", "cwd": "/absolute/worktree", "argv": ["bash", "run.sh"], "env": {"SEED": "1"}}]}`。
每个 job 必须有独立数据输出路径；环境变量默认叠加到当前环境，`inherit_env: false` 可使用完整快照。
manifest 若含环境快照应保持本机私有、权限 0600，不加入版本管理。报告不复制环境变量。

`--workers` 是目标上限，不等于无条件同时启动的数量。开启 `--gpu-monitor` 时，
初始容量为 `(总显存 - 已用显存 - 预留显存) / 每进程峰值估算` 向下取整，
且不超过目标上限；每次启动前再检查空闲显存。6000 MiB 是当前单环境 G1 相机任务的初始估算，
不是适用于任意任务的硬件保证；不同相机分辨率、场景和策略模型需重新测量。
同时限制 OMP/MKL/OpenBLAS 线程，避免多个进程各自占满 CPU。

Kit 自身还有独立线程池；使用 Isaac Lab AppLauncher 的 job 应显式加 `--kit-threads 4`，
监督器会将 carb tasking 与 TBB 线程上限作为一个 `--kit_args` 参数传给子命令。
这个开关只适用于会向 AppLauncher 转发参数的命令；通用命令不要启用。
应通过实际初始化与运行吞吐确定线程配置，不能只看单次 GPU 利用率。

每个环境有独立日志。`report.json` 记录实际并行容量、运行时间、退出状态、GPU 连续采样和
未启动任务；进程退出成功不等于生成轨迹成功，仍须回读 HDF5、动作有限性、相机帧数和任务标签。
失败不自动重试，其他环境继续执行。超时和终止清理所属进程组；子进程继承队列锁，
监督进程崩溃后后续队列任务仍须等原环境退出，避免跨任务 GPU 重叠。
不要让 manifest 子任务再次提交同一 GPU 队列，否则会等待自身占用的锁。

当前 RTX 5090 32 GiB 主机的 G1 PINK + 头部/诊断相机任务，实测四进程完成，
五进程确认轮有一个 Kit 初始化停滞，不能记为五环境通过。当前使用
`--workers 16 --worker-mib 6000 --reserve-mib 4096 --cpu-threads 2 --kit-threads 4`，
显存准入为四进程。目标上限沿用 16，这不是 16 环境已经通过的声明。
其他任务（特别是本地策略模型和高分辨率光轮厨房相机）不得套用此显存估算。
