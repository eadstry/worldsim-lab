# AutoData：Ray 并行直接导出 LeRobot v3

创建日期：2026-10-22。状态：实现与主机测试完成；缺少 LeRobot 和运行中的 AutoData 容器，真实写入回读及 GPU 吞吐验收未完成，不能宣称已加速生产。

## 实现范围

[生产入口](../../workspace-overlays/openarm-production/generate.py) 新增 `--export-format lerobot-v3`，通过 [Ray 池](../../workspace-overlays/openarm-production/ray_lerobot_pool.py) 把录制数组交给独立 CPU actor，再由 [直接写入器](../../workspace-overlays/openarm-production/lerobot_direct.py) 调用官方 `create/add_frame/save_episode/finalize`。不创建中间 HDF5；输入示范仍为现有带标注 HDF5。原 HDF5 导出保持默认兼容路径。

此次并行的是视频编码和数据写入，仿真仍为单个 Isaac Sim 进程中的 `num_envs` 环境。尚未实现多个 GPU 仿真进程的 Ray 调度。减少 HDF5 压缩、读取和二次转换是预期收益，收益需要实测。

每个 actor 独占 `OUTPUT.lerobot/shard-NNNN/`，其中各自有官方 v3 的 `meta/`、`data/`、`videos/`。外层 `manifest.json` 是生产清单，**外层目录不是一个可直接传给 LeRobotDataset 的合并数据集**；应加载其中实际生成的分片。一个 actor 对应一个数据集，`--export-workers 1` 可获得单个数据集。没有跨 actor 直接拼接 Parquet/MP4 或重写全局 episode 索引。

每个 actor 同时最多接收一个 episode，字节预算限制在途原始数组；超限施加背压。该预算不是整个进程的 RSS 上限：源 recorder、打包时的副本、Ray object store、编码器和磁盘临时图片另外占用内存/空间。默认 actor 每个请求一个逻辑 CPU、零 GPU；逻辑 CPU 配额并不约束 FFmpeg 的所有系统线程。使用显式整数 worker 上限，拒绝 `auto`，禁止自动重试，超时/失败留下未完成目录并标记失败，重跑必须换新目录。只支持当前主机自建 Ray 实例。

成功录制才进入训练集，要求 recorder 为 `EXPORT_SUCCEEDED_ONLY`。`action` 使用实际九维绝对关节目标；`observation.state` 使用同顺序、同单位的动作前关节状态；TCP 源动作、实际施加目标和后状态分别保留。缺少关节命令、名字、单位或帧长度不一致时拒绝导出，不能拿下一时刻测量状态冒充动作。每个分片 `production.json` 保存语义、源 episode 标识、属性与初始状态。

当前不支持该直接路径的 HDR 背景附加元数据，入口会拒绝同时指定 `--background-config`。不改变上游文件、版本引用或现有生产环境，不上传 Hugging Face。

## 运行入口与验收

在用户已启动、准备好运行依赖和资产的 AutoData 容器中执行；通过仓库共享任务队列提交。沿用原生产参数，增加：

```text
--export-format lerobot-v3 --export-workers 2 --export-queue-memory-gib 4 --generation-seed 101
```

完整命令形态（路径替换为容器内已配置的绝对路径）：

```bash
python3 scripts/task-queue.py submit --name ray-lerobot-v3 --timeout 7200 -- \
  bash workspace-overlays/openarm-production/run.sh \
  --autodata-root /workspace/AutoData --input_file /data/source.hdf5 \
  --output_file /data/new-run/output.hdf5 --num_envs 4 --generation_num_trials 16 \
  --export-format lerobot-v3 --export-workers 2 --export-queue-memory-gib 4 \
  --generation-seed 101
```

`output.hdf5` 此时仅作为已有启动器的输出命名基准，不会写该文件；实际数据位于 `output.lerobot/`。`run.sh` 要求其本地准备目录存在，并把 overlay 复制到已运行容器。不要把缺少资产的隔离 worktree 当作已配置生产环境。

2026-10-22 环境检查：主机系统 Python 无 Ray/numpy；现有 autodata 解释器有 Ray/numpy/h5py，但无 LeRobot；Docker 无运行容器。未安装任何依赖。遵照上游 AGENTS，容器由用户通过 `AutoData/docker/run_docker.sh -c` 启动，不能修改现有 autodata conda 环境。应先在新的隔离环境评估 `python -m pip install 'lerobot==0.4.3' ray` 的依赖兼容性，再构建兼容生产镜像；这不是已验证的安装组合，不能直接用于覆盖现有仿真环境。

主机生产测试共 49 项，48 项通过、1 项因缺少 LeRobot 明确跳过；`cloud-check.sh --allow-uninitialized` 在有意不初始化上游的任务 worktree 通过。新增测试覆盖直接映射、帧长度/单位/名字/有限值拒绝、帧副本所有权、官方 API 调用契约、调度 ACK、预算拒绝、超时和失败状态。真实官方写入与加载测试在 `test_lerobot_roundtrip.py`，依赖缺失时明确 skip，不能把 mock 测试当作官方格式验收。后续必须执行真实 Ray + 官方 writer 组合测试和 GPU 冒烟，再在相同输入、seed、环境数、目标成功数下比较 worker=1/2/4 的整个 run 用时、有效帧/秒、成功率、CPU/RAM/磁盘压力。`manifest` 的速率从导出池创建开始计时，不含完整仿真启动成本；端到端性能应使用 `run.json` 开始和结束时间。

## 自审及未完成项

已检查数据归属（每 actor 独占分片）、禁止覆盖、关闭/失败路径、取消自动重试、动作状态时序和语义、同步 HDF5 兼容性、启动器完成判断和监控事件字段。新增模块不复制上游实现或更改依赖 pin。未解决的验收依赖是官方 LeRobot 运行环境、真实 Ray writer 组合回读及 GPU 吞吐测试；因此保留在任务 worktree，未自动提交/推送。这是执行代理自审，不是独立 reviewer 批准。

格式与资源 API 依据：[官方 LeRobot v0.4.3 格式说明](https://huggingface.co/docs/lerobot/v0.4.3/en/lerobot-dataset-v3)、[Ray actors](https://docs.ray.io/en/latest/ray-core/actors.html)、[Ray 资源说明](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html)。
