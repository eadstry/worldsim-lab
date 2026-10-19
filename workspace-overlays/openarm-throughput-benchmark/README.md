# OpenArm：32 episode 生产效率对比

`bench32.py` 调用已经配置好的 `openarm-production`，不修改上游源码，不安装依赖。默认只生成计划；`--execute` 才启动 GPU。运行目录和机器配置均不提交 Git。

## 测试口径

每个单元请求 **32 个成功 episode**，保留左臂任务、三路 640×480 RGB、60 步末尾保持、原始规划和成功判据。`guarantee_success=true`、`keep_failed=false` 是强制前提。32 次尝试不等于 32 条成功数据。

本轮排查发现，上游会把执行过程中曾出现的成功信号累积为最终成功；8 环境样本中的一条虽记录成功，保存终态仍有 0.211 m/s 线速度和 5.748 rad/s 角速度。因而测试入口还对**最后保存的状态**应用既有放置、松手、速度阈值，合格后才标记成功、导出并计入 32 条目标。它不修改物理过程、规划、保持步数或阈值；两个导出版本统一启用该检查。不合格尝试计为失败并继续补样本，独立文件回读仍照常执行。

`terminal_launch.py` 复用现有监督器与运行环境，在独立子进程中接入 `terminal_gate.py`。覆盖层只改写内存中的生成函数，不改动上游文件或安装环境；源码边界不匹配时停止。旧的“曾经成功”数据只作诊断，不能与新口径混算速度比。当前 guard 仅适用于本文的 OpenArm 左臂固定任务。

性能改动拆成两层：原始同步路径让 CPU 帧切片持有整批环境存储；`owned_launch.py` 单独复用现有异步实现的 CPU 帧独立存储方法，保留同步 HDF5 写盘。随后再与已有的异步导出比较，此时两者均使用 CPU 帧独立存储，能隔离并行写盘的影响。数值/存储独立性已经通过现有 `PoolTests.test_cpu_capture_has_per_environment_storage` 主机测试；GPU 生产仍需逐组验收。

并行完成可能超过 32 条：记录实际条数和 overshoot，主要吞吐量始终使用 `32 / 耗时`，另列实际条数吞吐量。高并行下的额外工作属于实际成本；不要将“更多额外数据 / 完整时间”误认为固定 32 条工作量的提速。`time_to_32_generated_seconds` 只表示遥测达到 32 个成功的时间，不证明第 32 条已经落盘。

| 指标 | 起止 / 用途 |
| --- | --- |
| `generation_seconds` | 首个 episode 开始至最后一个 episode 完成；包含并发等待，不等于 GPU kernel 时间 |
| `final_ready_seconds` | 首个 episode 开始至 output_ready；包括导出队列排空、分片合并和文件关闭 |
| `launcher_seconds` | 启动监督进程至其退出；包括 Isaac Sim / cuRobo 初始化 |
| `verified_seconds` | launcher 时间 + 结构校验、图像首末帧读取、动作读取、终态判据校验、全文件 SHA256 时间 |
| `episodes_per_minute` | **主指标**：32 × 60 / verified_seconds |
| GPU 利用率均值 / p50 / p95 | 首个 episode 至 output_ready 期间 2 秒资源采样；均值是样本均值，非 GPU kernel profiler |
| 成功率、内存峰值、导出状态 | 排除降低质量、OOM、只入队未写完等伪提速 |

结构和记录终态校验通过，不等于物理重新回放通过。图像检查保留三路流尺寸与首末帧读取；全文件哈希会读取完整字节，但不等于解码校验每帧。并发 episode 的各阶段 host wall 时间有重叠，不能相加解释成整机墙钟占比。当前 GPU 资源采样按现有监督器提供的 GPU 数据聚合，面向本机单 GPU；多 GPU 需按所用 UUID 过滤后再比较。

## 扫描与确认

1. 先扫描 4、6、8、12、16、24、32、64 环境；每个档位依次运行同步、2 个进程、自动导出。单元之间串行，避免多个 Isaac Sim 争用同一 GPU。
2. 内存准入默认估算为 `12 GiB + 环境数 × 4.5 GiB + 异步队列 8 GiB`，另保留 8 GiB 可用内存；运行时低于保护线、或主进程 RSS 超过 44 GiB 则终止本单元。内存限制命中或观察到 OOM 后，不再扩大该版本的并行度。估算和 44 GiB 保守保护线来自本机调查，不是通用硬件容量；其他服务器应按已有实测证据调整 `--max-rss-gib`。
3. 首轮用 seed=1、重复一次筛选。选出吞吐量最佳的共同档位和各版本最佳档位，再用 seed=1/2/3 重复三次。报告中位数和范围，一轮筛选结果不应称为稳定提速。
4. 同时比较**相同并行度**的速度变化，以及**各版本最佳并行度**的可达产能变化。不以 GPU 利用率最大直接选优；CPU 编排、RGB 渲染、缓存和磁盘可能成为瓶颈。
5. 同一批测试固定 CPU governor、GPU 时钟/功耗配置、磁盘位置、压缩方式、相机参数和成功判据。脚本不修改系统 governor。存在其他 GPU compute 进程时拒绝启动该单元。桌面图形活动仍可能带来噪声，确认轮需检查。

32 个 episode 是小批端到端生产成本测试。它不足以证明长期稳态吞吐；要另测稳态，应增加独立工作量和 warmup 方案，不将未测的持续产能外推为结论。任务 seed 配对便于重复，但并行度改变会改变共享随机数消费顺序，不能保证生成逐条相同的轨迹；同时报告尝试数、成功率和 episode 长度。

## 使用

在已配置 GPU 机器上设置机器路径，使用现有 autodata Python：

```bash
python workspace-overlays/openarm-throughput-benchmark/bench32.py \
  --production-root "$OPENARM_PRODUCTION_ROOT" \
  --input "$OPENARM_ANNOTATED_SOURCE" \
  --python "$OPENARM_PYTHON" \
  --directory workspace-overlays/openarm-throughput-benchmark/runtime/plan-32
```

执行时换一个全新目录，增加 `--execute`。默认在成功校验后删除**本轮新生成**的 HDF5 和 export-parts，保留结果、哈希、导出元数据及所有日志；这适合空间有限的性能测试。需要保留训练数据则加 `--keep-datasets`，并准备足够磁盘。失败数据不会被自动删除；空间不足时跳过后续单元，不覆盖已有数据。

比较具体代码改动，可用不提交 Git 的 `variants.local.json`，指向已经准备好的不同 overlay 目录；脚本不切换、更新或修改任何上游仓库：

```json
[
  {"name": "owned_sync", "production_root": "/configured/baseline/workspace-overlays/openarm-production", "workers": 0, "owned_recording": true},
  {"name": "changed", "production_root": "/configured/changed/workspace-overlays/openarm-production", "workers": "auto"}
]
```

加 `--variants PATH` 指定，第一项为基线。对比前确认任务、资产、源数据和输出语义一致；代码版本变化不自动证明工作量一致。计划记录源 HDF5、任务、overlay Python 和运行时资源的 SHA256；机器路径只保留在本机运行目录。

已观察到某版本在更高并行档位不可行时，可在对应 variant 增加 `"max_envs": 6` 等上限，避免重复支付已知失败的成本。资源保护触发记为 `capacity_limited`；真实 OOM、生成错误和验收失败记为 `failed`。前者不是成功生产样本，也不证明硬件绝对上限。`passed` 表示所有版本至少有一个有效单元且未出现未处理失败；只有 `complete_requested_grid=true` 才表示所请求的全部单元均完成验收。

`"min_envs": 8` 可限制某版本的本轮范围，例如复用已完成的 6 环境结果而继续探测更高档位，未运行的低档位记为 `skipped_scope`。用 `collect.py REPORT... --output DATA.json` 汇总兼容结果；首份报告的第一个 variant 为基线。收集器拒绝源数据、任务、终态验收策略、重复次数不一致或重复的单元；未完成单元单独列出，不参与速度比较。不同代码修改是否保留任务语义，仍需要结合源码哈希和实际变化人工判断。

确认轮示例：使用新的目录并加 `--envs 8 12 --repeats 3 --seeds 1 2 3 --execute`。该例需按首轮可行档位调整。最高并行度还受 CPU、GPU 和物理内存共同约束；被跳过的档位不能记作实测失败或实测性能上限。

## 检查

```bash
python3 -m unittest discover -s workspace-overlays/openarm-throughput-benchmark -v
```

这些是主机测试：覆盖超额完成的分母、回读计时、未完成导出/中断拒收、终态不合格拒收、重复次数不足时不产生确认结果，以及导出前终态检查的接入边界和数值判据。数值用例需要已有 NumPy，可用已配置 autodata Python 执行；缺少 NumPy 的主机将跳过数值用例。它们不执行仿真，也不证明 GPU 性能。

本轮还使用已有 HDF5 将导出前检查与独立回读器的 32 个终态结果逐条对照，包含 1 条拒收和 31 条通过；两者一致。这验证的是检查逻辑一致性，不是新入口已经完成 32 条 GPU 生产。
