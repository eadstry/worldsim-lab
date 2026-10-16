# GPU 为什么没有持续满载：沿原始代码定位

## 新增 4 环境插桩配对与加速方案

本版引入 2026-10-15 的独立 4 环境配对：同步与 auto 各 8/8 严格终态通过，8 组完整动作序列精确匹配，最终文件吞吐提升 47.2%。这组结果不替换历史 8 环境数据，也不代表已测得 GPU kernel 占比。

详见 [内部计时与加速方案](acceleration-analysis.html) 和图册新增八页；原始结果、计时脚本与校验记录在 paired4/ 中。下面的新增分析优先去除重复相机刷新和重复 CPU 图像副本，缓存优化尚未实施。



当前最明确的结构性限制是：GPU 批量仿真嵌在一个由主线程推进的闭环里；每批动作需要等齐，观测会回传 CPU，规划与打包也占用这条主线程。异步 writer 移走压缩和写盘，尚未把整个生成流程改为可持续提交 GPU 工作的流水线。以下解释代码为什么可能留下设备空闲区间；已有日志不能给各原因分配百分比。

## 先明确“拉不满”的指标

已有 v1 设备级 GPU 利用率均值为同步 22.7%、cap4 40.8%、cap8 35.6%、auto 32.8%。它统计采样周期内有一个或多个 kernel 执行的时间比例，不是 SM occupancy，也不是 GPU 算力使用比例。不能据此推导剩余算力或理论加速倍数。定义见 [NVIDIA nvidia-smi 文档](https://docs.nvidia.com/deploy/nvidia-smi/index.html)。

统计窗口含生成后的排空、合并等收尾，auto 的最后完成到 output_ready 为 74.477 秒。因此整批均值不能代表稳态仿真利用率。cap4 的平均 GPU 利用率最高，cap8 的最终就绪最快；优化目标应是单位时间的合格产出。

## 1．全环境动作屏障：8 个环境不是 8 条独立的 GPU 提交流

[env_loop 原代码 250 行](source/env-loop.html#L250) 在队列长度等于 num_envs 之前，只推进协程和处理 reset；[271 行](source/env-loop.html#L271) 才调用整批 env.step，随后逐个 task_done。每个环境在 [MultiWaypoint.execute 333–336 行](source/waypoint.html#L333) 提交动作后等待 queue.join。

```python
while env_action_queue.qsize() != env.num_envs:
    asyncio_event_loop.run_until_complete(asyncio.sleep(0))
# 等齐后收集动作
env.step(actions)
for _ in range(env.num_envs):
    env_action_queue.task_done()
```

因果链：某环境正在同步规划、重置或提交导出 → 它尚未提交下一动作 → 整批 step 尚不能开始。asyncio 让协程交替推进，不会把同步 Python 函数自动移到另一线程。这里确认的是全批动作屏障；等待期间 GPU 也可能执行规划工作，不能把全部屏障时间算作 GPU 空闲。

改进方向：先记录各环境动作就绪时刻与整批 step 开始时刻。批量规划、预计算或分组调度需要保持世界状态和动作步对齐；不能简单跳过慢环境而改变任务语义。仅增大 num_envs 还会增加相机、内存及等待负担。

## 2．相机观测：GPU 图像每次都复制回 CPU

冻结任务的 [cameras.py 46–55 行](source/camera.html#L46) 是直接证据：

```python
def rgb_image(env, name):
    update_mounted_camera_poses(env.scene)
    return env.scene[name].data.output["rgb"].torch[..., :3].to(device="cpu", copy=True)
```

这里明确要求 CPU 上的新副本，且没有请求 non_blocking。CPU 消费者必须等数据可读后继续。这样做原本是为了避免 recorder 将整条轨迹的 RGB 长期保留在显存中，目的合理，但会让设备到主机传输进入 step 的关键路径。异步 HDF5 writer 不会消除这次传输。

[20–43 行](source/camera.html#L20) 的 update_mounted_camera_poses 每次循环更新三个相机；[配置 122–124 行](source/config.html#L122) 为三路 RGB 分别注册 rgb_image。因此一次完整观测计算会调用三次 RGB 回传，并调用九次 set_world_poses。每次处理的是当前整批环境，不是单张图片。这是函数调用次数，不是渲染次数，也不是 kernel 次数。

## 3．启用录制时可能重复计算观测：先录制，再返回重置后状态

当前 [ManagerBasedRLEnv.step 242–245 行](source/rl-step.html#L242) 在 recorder 有 active_terms 时计算观测供录制；[270 行](source/rl-step.html#L270) 在 reset、command 和 interval event 之后再次计算观测并更新历史。

```python
if len(self.recorder_manager.active_terms) > 0:
    self.obs_buf = self.observation_manager.compute()
    self.recorder_manager.record_post_step()
# reset / command / interval events
self.obs_buf = self.observation_manager.compute(update_history=True)
```

[ObservationManager.compute 333–341 行](source/observation.html#L333) 每次重建观测字典，并没有在入口直接返回上次缓存。[395 行](source/observation.html#L395) 对每个 term 执行 func(...).clone()。当 term 是 rgb_image 时，先产生 CPU RGB 副本，再做 CPU clone；录制还可能另行复制以管理所有权。

在“运行时加载当前这份 RL step、录制开启、三路 RGB 启用”三个条件同时成立时，一次外层 step 的两次观测计算意味着至少六次批量 RGB 回传调用、十八次相机 set_world_poses 调用及相应观测 clone。reset 还可能产生额外调用。**这不是实测次数，也不是六次渲染。** 相机 data 读取是否复用缓存、是否触发更新，需要进一步追踪。

版本边界：相机和任务配置来自 v1 冻结实验包；上述 RL step 与 observation_manager 来自当前依赖源码。尚未通过历史运行的 __file__ 与源码 hash 证明依赖逐字一致，因此该重复路径是当前代码的明确候选，不能直接归因为历史实验已证实的瓶颈。

改进方向：把一次 step 内相机位姿刷新集中处理；给图像读回与观测缓存添加有效性标记。只有在 reset、事件、相机姿态和观测历史语义均允许时，才能复用结果。不能直接删除第二次 compute，因为它负责返回重置后的正确观测。另可评估有界 pinned-memory 缓冲与异步传输，但消费者读取前仍须等待事件，且必须保留正确的帧归属。

## 4．同步规划和标量读回：GPU 能并行求解，不等于上层调用并行

[algorithms.py 240–247 行](source/algorithms.html#L240) 直接调用 planner.update_world_and_plan_motion，没有在线程池或进程池中调度。冻结加载器 [compat.py 98–104 行](source/compat.html#L98) 加载 runtime/patches/curobo_planner.py；该补丁在 [1312–1314 行](source/planner.html#L1312) 使用 plan_single 并读取 result.success.item()。

```python
result = self.motion_gen.plan_single(start_state, goal_pose, self.plan_config)
if result.success.item():
    ...
```

plan_single 内部可使用 GPU 批量 seeds，但接口调用仍是单个环境的问题。主线程调用期间其他协程不能靠 asyncio 自行推进；success 若在 CUDA 上，item() 还需等待结果可供主机读取。不能把“内部求解并行”理解为“8 个环境同时提交一个批量规划请求”。

同样，[waypoint.py 336 行](source/waypoint.html#L336) 每环境每次动作后执行 bool(success_term.func(...)[env_id])。若返回 CUDA tensor，转 Python bool 是主机读取结果的同步边界；它还可能重复计算整个环境批次的成功条件。实际张量设备、函数计算范围以及同步延迟需要采样验证。

另一个 v1 候选是 [get_planned_poses 1599–1604 行](source/planner.html#L1599)：逐 waypoint 调用 _compute_kinematics，可能产生较多小任务与主机调度开销。v2 适配器 [233 行](source/v2-planner.html#L233) 已将整条 _current_plan 传入 _state 和 _ee_pose 计算矩阵，因此不能把这一 v1 循环问题原样套到 v2。它也不能证明 v2 整体更快，现有实验并未建立这样的结论。

改进方向：在状态不变且语义相同的边界批量计算成功条件，再集中读回；评估跨环境批量规划和 v1 FK 批处理。每项分别消融，保留动作、轨迹与成功判定一致性检查。

## 5．异步导出只移走保存的一部分，主线程仍打包和等待预算

冻结 [ExportPool.submit 296–314 行](source/export.html#L296) 先检查共享内存预算，必要时 poll(wait=.05) 等待释放，再分配 SharedMemory 并同步 pack。这里 .05 是预算不足时的轮询等待参数，不是每步固定睡眠 50 ms。

[pack 77–107 行](source/export.html#L77) 对 CPU 帧逐帧 np.copyto；GPU 状态列表仍需 stack、cpu 和复制。writer 接收的是已打包的共享内存任务，压缩和写盘才在子进程内进行。因此保存已经并行，提交大 episode 时主线程仍可能停顿，并通过动作屏障影响下一批 step。

[export_governor.evaluate 143–170 行](source/governor.html#L143) 使用 CPU、内存、进程数、共享内存及 I/O 等条件决定资源策略；没有按 GPU 利用率闭环扩容。增加 writer 不能保证 GPU 更忙，且可能争用主线程所需的 CPU 和内存带宽。

## 6．现有实验支持到哪一步，下一次怎样定量拆开

v1 四组完成样本的 execute 调用数均为 23,476；每 100 次调用窗口的中位数约 108–114 ms，而窗口 P95 从同步约 944 ms 降至 auto 约 187 ms。它支持“等待长尾减少”，不能证明余下约 108 ms 主要耗在 physics 或相机。execute 本身包含动作屏障、env.step 和协程恢复等墙钟时间，多环境累计会重叠。

| 优先级 | 要确认的代码区间 | 最少记录 | 判据与正确性检查 |
|---|---|---|---|
| 1 | 两次 observation.compute → rgb_image | 实际加载文件 hash；每 step 调用计数；CPU 区间与 CUDA 复制时间线 | 确认重复读回后再改缓存；比较 RGB、重置后观测与帧序 |
| 2 | action put → step → task_done | 每环境动作就绪时间、最早/最晚就绪、step 起止 | 判断设备空隙是否与等齐动作一致；不能将 CPU 区间直接视作 GPU 空闲 |
| 3 | success bool/item 与 plan_single | NVTX 区间、CPU/CUDA 关联；规划调用和同步耗时 | 分开 CPU 调用耗时、GPU 工作和同步等待；复用判定须语义相同 |
| 4 | submit/pack/预算等待 | pack 秒数、budget wait、内存占用与设备时间线 | 确认导出是否阻断下一批提交；监控峰值内存与输出一致性 |
| 5 | 仿真与渲染内部 | profiler 中 physics、render、copy 的时间线；必要时再查 kernel 指标 | 先判断提交间隙还是设备工作本身昂贵，再决定是否增大批次 |

以上是诊断方案，本版未新增 GPU 实验。建议在单独诊断运行使用 CPU 区间标记与设备追踪，避免每个子步骤插入全局 synchronize 而改变原本调度。对照实验按生成阶段与最终收尾分别统计，最终仍用合格吞吐、输出完整性和任务质量判断改进。

另需排除一个误解：[任务配置 215–218 行](source/config.html#L215) 的 dt=1/120、decimation=4 给出每外层 step 的仿真时间推进量约 1/30 秒，并不等于墙钟必须等待 1/30 秒；仅凭这个参数不能断言代码限帧。
