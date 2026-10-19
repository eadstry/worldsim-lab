# AutoData 原理与数据流（总览）

> 本文合并整理自三份笔记：`DatagenInfo-原理与数据流`、`Waypoint-原理与数据结构`、`autodata_implementation_flow`。
> 基于仓库当前代码整理，所有引用标注 `文件:行号`。
> 目标：说明 AutoData 如何把少量人工标注演示（HDF5），经「拆段 → 变换 → 拼接 → 执行 → 录制」批量放大为新的成功演示。
> **贯穿示例**：正文每阶段跟随同一次 Franka 四段堆叠的 MimicGen 尝试（`demo_0` 200 步）。位姿、边界、动作数值均为便于说明而设定的纸面值；字段、参数、顺序取自代码。文中没有启动 Isaac Sim，不把模拟数值当成运行结果。
> 另有一个 12 步的通用小例（第 3.1、四 节）用于说明字段与切段，与 Franka 200 步示例相互独立。

---

## 一、整体定位与分层

AutoData 的目标：拿少量人工标注演示（HDF5），在 Isaac Lab 仿真里并行地拆段、变换、拼接、执行、录制，批量产出新的成功演示。

代码分层（`README.md`）：

```
autodata_core/        # 算法与执行引擎
  algorithms.py       # GenerationAlgorithm 注册表 + Mimic/DexMimic/SkillGen
  data_generator.py   # 主编排器 DataGenerator.generate()
  pool.py             # DataGenInfoPool：源演示容器
  waypoint.py         # Waypoint / WaypointSequence / WaypointTrajectory / MultiWaypoint
  datagen_info.py     # DatagenInfo：源演示 schema
  transforms.py       # 纯张量位姿变换
  selection_strategy.py
autodata_interfaces/  # Datastream / 任务描述 / embodiment / motion planner
autodata_utils/
scripts/generate_dataset.py  # CLI 入口
```

核心设计原则：**生成器只通过 `Datastream` 读状态，不直接碰仿真器**；只有到 `MultiWaypoint.execute` 才把位姿编码成 action。该边界在 `docs/pages/concepts/data_generator.rst` 中亦有强调。

---

## 二、入口装配：`scripts/generate_dataset.py`

`main()`（`scripts/generate_dataset.py:276-385`）顺序关键，存在循环依赖（planner 需要 Datastream，Datastream 需要 `uses_start_signals`，该标志来自算法类）：

```python
# 1) 解析任务描述，拿到 GenerationPolicy
task_descriptor = TaskDescriptor.from_yaml(args_cli.task_descriptor)
generation_policy_params = task_descriptor.get_generation_policy()

# 2) 先按算法"类属性"决定是否用 start signals（skillgen=True）
alg_cls = REGISTERED_ALGORITHMS[args_cli.alg]
generation_policy_params.use_skillgen = alg_cls.uses_subtask_start_signals

# 3) env profile 叠加 → 建 env cfg → gym.make
env = gym.make(env_name, cfg=env_cfg).unwrapped
env.reset()

# 4) 先建 Datastream（内部构建源片段池）
datastream = build_datastream(...)

# 5) SkillGen 才建 curobo planner，再实例化算法
algorithm = get_algorithm(args_cli.alg, **alg_kwargs)
```

- `build_datastream()`（`167-186`）：把 env + task descriptor + embodiment adapter + HDF5 源数据集组合成 `Datastream`。
- `setup_async_generation()`（`189-228`）：**只创建一个 `DataGenerator`，但为每个 `env_id` 创建一个 asyncio task**，所有 task 共享同一个 generator（池加锁的动机）。
- 最后 `env_loop(...)` 跑同步仿真循环。

**示例输入与配置落点。** 在按 `AGENTS.md` 启动的 Docker 容器中、取得真实 HDF5 后运行（命令形状来自 `docs/pages/workflows/franka_cube_stack_mimicgen/step_3_generate_dataset.rst`）：

```bash
python scripts/generate_dataset.py \
    --env_name Isaac-Stack-Cube-Franka-IK-Rel-v0 \
    --viz kit --num_envs 2 --alg mimicgen \
    --generation_num_trials 2 \
    --task_descriptor autodata_examples/tasks/franka_cube_stack.yaml \
    --embodiment autodata_examples/embodiments/franka_ik_rel.yaml \
    --input_file ./datasets/annotated_datasets/dataset_franka_annotated.hdf5 \
    --output_file ./datasets/generated_dataset_mimicgen_franka_example.hdf5 \
    --result_file ./datasets/generated_dataset_mimicgen_franka_example.json
```

| 输入 | 在 `main()` 中变成什么 | 本例关键参数 |
|---|---|---|
| `--env_name` | `setup_env_config()` 的 `env_cfg`、`success_term`，再由 `gym.make()` 创建环境 | 已注册 Gym ID；基础 Franka 堆叠场景 |
| `--task_descriptor` | `TaskDescriptor` 与 `GenerationPolicy` | 四个 `franka` 子任务；`seed=1`、`guarantee_success=true`、`keep_failed=false` |
| `--embodiment` | 位姿与 action 的适配器 | `franka` 单 EEF，6 维相对位姿 + 1 维夹爪 |
| `--input_file` | `Datastream.source_pool` | 人工标注源 HDF5；不是 YAML 里的 `source_dataset_path: null` |
| `--num_envs 2` | 两个生成 task、一个共享 `DataGenerator` | `env_id=0,1` 的 action 一起交给批量 `env.step()` |
| `--generation_num_trials 2` | 覆盖 YAML 的 `num_trials: 10` | `guarantee_success=true` 时累计两个成功，而非只试两次 |
| `--output_file` / `--result_file` | recorder HDF5 / 可选统计 JSON | 生成的 episode 与整次运行计数 |

本例没传 `--env_profile`，因此不应用 `franka_bin_stack.yaml` 的料箱场景。**工作区中上述输入路径只有 Git LFS 指针，不能直接当 HDF5 运行**；下面仅模拟已取得真实源数据之后的数据流。

---

## 三、核心数据结构

### 3.1 `DatagenInfo` —— 源示范的记录（`autodata_core/datagen_info.py:16-64`）

一条源演示每一步的维度集合，字段全可选，子任务片段复用同一类型：

```python
eef_pose:        {eef_name: [T,4,4]}   # 记录的 EEF 实际位姿 [m, rad]
object_poses:    {obj_name: [T,4,4]}   # 记录的物体位姿
target_eef_pose: {eef_name: [T,4,4]}   # 控制器目标位姿
passthrough_action: {channel: [T,D]}   # 非位姿通道（夹爪、底盘等）逐字复制
subtask_term_signals / subtask_start_signals  # {subtask_name: [T]} 二值标志
```

`eef_pose`（实际）与 `target_eef_pose`（目标）分开：变换用后者，前者用于选择/锚定插值。

**12 步小例。** 以"抓起方块、抬高、放入碗中"为例，一条遥操示范录了 12 步（索引 `0…11`）：

```python
DatagenInfo(
    eef_pose={"arm": ...},              # [12, 4, 4]：每步实际观测到的末端位姿
    target_eef_pose={"arm": ...},       # [12, 4, 4]：每步动作给出的末端目标
    object_poses={
        "cube": ...,                    # [12, 4, 4]：方块位姿
        "bowl": ...,                    # [12, 4, 4]：碗位姿
    },
    passthrough_action={"arm": ...},    # [12, D]：夹爪等非位姿动作
    subtask_term_signals={
        "grasp": [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "lift":  [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
    },
)
```

`...` 代表实际张量，非固定值。字典按名称组织：`object_poses["cube"]` 取方块 12 帧、`object_poses["bowl"]` 取碗 12 帧。

`eef_pose` 与 `target_eef_pose` 分别是"现在在哪里"和"这步想去哪里"。例如末端当前 `x=0.40 m`，动作要求沿 x 移动 `0.01 m`，则本步记录实际位置 `0.40 m`、目标 `0.41 m`；目标由 `target_pos = curr_pos + delta_pos` 算出，**不表示录制时已到达**。[动作换算](../../AutoData/autodata_interfaces/embodiments/single_arm_embodiment_adapter.py) [录制位置](../../AutoData/scripts/annotate_demos.py)

**池里的形态。** 五条已标注遥操示范，源池通常有五个这样的 `DatagenInfo`，每条一个，放在 `pool.datagen_infos` 列表里；字典里的 `"cube"`、`"bowl"` 不是示范编号。`from_hdf5()` 读入时 HDF5 键为 `object_pose`（单数），入池后属性为 `object_poses`（复数）。`DatagenInfo` 另有 `to_dict()`（`49-64`）只materialize 已填充字段。

### 3.2 Waypoint 层 —— 算法与生成器之间的指令 IR（`autodata_core/waypoint.py`）

#### 3.2.1 一句话定位

Waypoint 层是**算法插件与生成器之间的中间表示（IR）**：算法不直接产出 action，而是产出「目标位姿 + 透传动作 + 噪声」；只有到执行那一刻（`MultiWaypoint.execute`）才编码成仿真器能用的 action。

文档原话：*"Algorithms and the generator talk to each other in waypoints, not actions"*；*"Only at the `MultiWaypoint` boundary do poses become robot actions — everything upstream of it is embodiment-agnostic."*（`docs/pages/concepts/data_generator.rst:84-96`）

#### 3.2.2 为什么需要这一层

**核心矛盾：action 不能被变换。** 源示范录下来的 action 是**相对录制那一刻状态的增量**（`single_arm_embodiment_adapter.py`）：

```
delta_pos = target_pos - curr_pos
```

要把同一段技能回放到物体位置不同的新场景，delta 没用——它只在原来的当前位置下成立。设源场景方块在 `x=0.50 m`，新场景方块被随机化到 `x=0.80 m`；直接复用源 action（一串增量），机械臂只会从**自己当前位置**挪一点，永远到不了新方块上方。

**解法：在绝对位姿空间做刚体变换。** 源示范的**目标位姿**是绝对量，可整体搬移（`transforms.py:34-53`，`transform_source_data_segment_using_object_pose`）：

```
T_new_eef = T_current_object · inv(T_source_object) · T_source_eef
```

`x=0.50` 的目标被平移到 `x=0.80`；执行时再用新场景真实状态重新算 delta，action 才正确。文档把这条写成硬约束：*"The transformation requires task-space actions … which is what the embodiment adapters guarantee."*（`docs/pages/concepts/algorithms.rst:45-47`）

**算法要做的运算几乎全在位姿上：**

| 运算 | 作用对象 | 在 action 空间能做吗 |
|---|---|---|
| 选源（比距离）`selection_strategy` | EEF/物体**位姿**距离 | ✗ |
| 变换到新物体位姿 `transforms.py` | **位姿**矩阵乘 | ✗ |
| 段间插值 `interpolate_poses` | 两个**位姿**之间 | ✗ |
| 拼接 merge | 两段**位姿**轨迹首尾相接 | ✗ |
| 运动规划（cuRobo） | 输出**位姿**序列 | ✗ |
| 跨臂约束"原地 hold" | 冻结某个**位姿** | ✗ |
| 加噪做多样性 | 位姿**动作**（编码时） | ✓（只此一项） |

七项里六项只认位姿，因此统一用位姿作为工作表示，即 Waypoint。

#### 3.2.3 四个数据类型

| | 粒度 | 装什么 | 一个实例代表 | 关键方法 | 生命周期 |
|---|---|---|---|---|---|
| `Waypoint` | 1 步 × 1 臂 | 目标位姿 + 夹爪 + 噪声 | 某一刻"手要去哪" | 无（纯数据） | **执行期**逐 tick 取用 |
| `WaypointSequence` | 1 段 × 1 臂 | `list[Waypoint]` | 变换后的一整段技能 | `from_poses` / `split` / `__add__` | **构造期** |
| `WaypointTrajectory` | 1 臂 × 多条段 | `list[WaypointSequence]` | 一臂待执行的完整行程 | `merge` / `add_..._target_pose` / `pop_first` | **构造期** |
| `MultiWaypoint` | 1 tick × 多臂 | `{eef: Waypoint}` | 这一刻所有臂一起动 | `execute()` | **执行期**，每 tick 一次 |

一句话区分：**Sequence 是"段"，Trajectory 是"段拼成的行程"，Waypoint 是"行程里的一步"，MultiWaypoint 是"这一刻多臂捆绑"**。

**`Waypoint`（`26-51`）——最小执行单元（1 步 × 1 臂）**

```python
Waypoint(pose=[4,4], passthrough_action={"franka": [-1]}, noise=0.03)
```

- `pose`：**绝对**目标位姿（世界系），`[m, rad]`。
- `passthrough_action`：这一步的非位姿通道（夹爪、底盘等），每条通道一个值，`{channel: [D]}`。
- `noise`：这一步位姿动作的噪声幅度，**只打位姿、不打透传**。
- `joint_seed`：可选关节种子，供 IK / 离线调度用。

它是纯数据盒。只有配上执行才有意义：`MultiWaypoint.execute` 拿 `pose` 与机器人**当前实际位姿**做差得到 action。**Waypoint 存的是"目标"，action 是"目标 − 当前"。**

**`WaypointSequence`（`54-129`）——变换单位（1 段 × 1 臂）**

```python
WaypointSequence.from_poses(
    poses=[T,4,4],
    passthrough_actions={"franka": [T,1]},
    action_noise=0.03,      # 标量或 [T]/[T,1]
)
```

- 构造时 `deepcopy`，不污染源数据（`63`）。
- `get_poses()` 只取平移分量 `pose[:2,3]`，用于选段比距离；`split(i)` 切前后两半；`__add__` 首尾接；`last_waypoint` 深拷贝末元素。
- 它是**"一个子任务段经过变换后"的产物**（`data_generator.py:358-364`：变换后位姿 → `from_poses` → 包成 Sequence）。

存在理由：算法的最小操作单位是"一段"——选它、变换它、插值它的两端；单步太细，整条行程太粗。

**`WaypointTrajectory`（`132-279`）——拼接/插值单位（1 臂 × 多条段）**

```python
traj = WaypointTrajectory()
traj.add_waypoint_sequence(seq)                                   # 直接接一段
traj.merge(other, num_steps_interp=5, num_steps_fixed=0, action_noise=0.0)  # 带桥接地接
```

- 内部是 `list[WaypointSequence]`；`__getitem__` / `__len__` 把多层拍平成"第 k 个 waypoint"。
- `merge()`（`227-275`）是它独有的能力：先**插值**从本轨迹末位姿到对方首位姿，再可选**固定 hold**，然后接上——只有在这一层看得到"两段交界处"。实现上先 `pop_first()` 取出对方首位姿作为桥接目标，插值/hold 段都指向它，最后接上对方剩余序列。
- `add_waypoint_sequence_for_target_pose()`（`165-216`）：追加一段通往某目标位姿的行程；插值时**丢掉第一个插值样本**（与当前终点重复）。
- `get_full_sequence()`：拍平回一条 Sequence。

**与 Sequence 的本质区别**：Sequence 是不可再分的"一段"；Trajectory 是"多段 + 段间过渡"的容器，**插值和拼接发生在它这**。`data_generator.merge_eef_subtask_trajectory` 正是先起 Trajectory、塞入起始种子段、再用 `merge()` 接上新段（`data_generator.py:504-515`）。

**`MultiWaypoint`（`282-336`）——执行期捆绑（1 tick × 多臂）**

```python
MultiWaypoint({"left": wp_l, "right": wp_r})   # 每个 EEF 取当前这一步
```

`execute()`（`288-336`）做四件事：

1. 拆出 `target_eef_pose_dict`、`action_noise_dict`，透传通道按名字**去重合并**（`setdefault`，并按 `sorted` 遍历保证跨臂顺序稳定，`316-318`）。
2. 调 `datastream.target_eef_pose_to_action(...)` 编码（**位姿第一次、也是唯一一次变成 action 的地方**）。
3. `env.step(play_action)`，或把 `(env_id, action)` 放进 `env_action_queue` 交给同步 `env_loop` 批量 step。
4. 返回 `success_term.func(env, **params)[env_id]`，实现"每步判成功"。

数据来源：`_collect_eef_waypoints()`（`data_generator.py:649-682`）每 tick 为每条臂取**一个** Waypoint（暂停中的臂取 hold 的那个），组成 dict，再 `MultiWaypoint(eef_waypoints)`（`data_generator.py:578`）。

> 注意名字误解：**MultiWaypoint 不是"更多 waypoint"，而是"多 EEF 在同一刻的捆绑"**；单臂任务里它也只装一个 Waypoint。

#### 3.2.4 装配流程

以单臂 MimicGen 一段技能为例：

```
① 变换后的位姿 [T,4,4]
      │ WaypointSequence.from_poses()
      ▼
② WaypointSequence（这一段）                       ← 构造期
      │ add_waypoint_sequence()
      ▼
③ WaypointTrajectory（本臂行程；merge 加桥接段）    ← 构造期
      │ get_full_sequence().sequence → 拍平成 list[Waypoint]
      ▼
④ 存进 _EEFGenerationState.current_trajectory      ← 执行期开始
      │ 每 tick 取一个 Waypoint
      ▼
⑤ MultiWaypoint({...}) → execute() → action → env.step()   ← 执行期
```

**关键分界**：①②③ 在**构造期**，负责"算出一条正确的行程"；④⑤ 在**执行期**，只按帧消费单个 Waypoint。Trajectory 到最后被拍平成普通 `list[Waypoint]`，执行时不再需要"段"的概念。

#### 3.2.5 三个易混点

1. **Sequence vs Trajectory**：都装有序 Waypoint。Trajectory 能装**多段**并负责**段间插值/拼接**；Sequence 只是一段。需要 merge 就用 Trajectory。
2. **Trajectory 是"一条臂的整条行程"，不是"整个任务"**：双臂任务有两条 Trajectory（每臂一条），最终在 MultiWaypoint 里汇成同一个 action。
3. **前三者是"空间上的包含"，MultiWaypoint 是"时间上的横切"**：步 ⊂ 段 ⊂ 行程 是嵌套；MultiWaypoint 把各臂的同一步横向捆起来。

#### 3.2.6 `noise` 的含义

`Waypoint.noise` 是**编码 action 时给这一步「6 维位姿动作」叠加的高斯噪声幅度（标准差 σ）**，不是加到目标位姿上的偏移量；只在 `MultiWaypoint.execute` → embodiment adapter 编码那一刻起作用，不改变 `Waypoint.pose`。

以 Franka 单臂为例（`single_arm_embodiment_adapter.py`）：

```python
if scale > 0.0:
    pose_action = pose_action + scale * torch.randn_like(pose_action)   # 6 维
if self.clip_pose_action_to_unit:
    pose_action = torch.clamp(pose_action, -1.0, 1.0)
```

- 作用对象是**相对位姿增量**（3 维平移 `[m]` + 3 维轴角 `[rad]`），每维独立 `N(0, σ²)`。
- `noise=0.03` ≈ 每平移轴 ±3 cm、每旋转轴 ±3°（1σ）。
- **只作用于位姿，不作用于透传通道**（夹爪值逐字复制，永不加噪；`waypoint.py:41` 的 *"Not noised."*）。
- 加噪在 **clip 之前**，噪声不会把 action 顶出 `[-1,1]`。
- 逐 tick 存储：`from_poses` 支持标量广播或 `[T]`/`[T,1]` 逐帧值。

**噪声值从哪来**：

| 来源 | 代码 | 典型值 |
|---|---|---|
| 源片段：子任务 `action_noise` | `data_generator.py:361` | `0.03`（Franka 堆叠 YAML） |
| 插值/固定桥接段 | `data_generator.py:510`：`apply_noise_during_interpolation * action_noise` | 默认 `false` → 桥接段 0 |
| SkillGen 的 MP transit | `algorithms.py:269-271`：`motion_planner.config.motion_noise_scale` | 缺省 `0.0` |
| merge 时保留原噪声 | `waypoint.py:272-273` | — |

规则：**被回放的源片段永远加噪，插值/hold 段是否加噪由 `apply_noise_during_interpolation` 决定**（`task_descriptors.rst:133-136`）。目的是制造多样性；幅度要小到任务仍能成功，否则应调小 `action_noise`。

**别和其他"噪声"混淆**：

- `coordination_scheme_pos/rot_noise_scale`（`transforms.py:56-122`）：作用于**物体位姿变换的 delta**，且是**均匀分布**。
- 双臂 `_add_noise`（`bimanual_embodiment_adapter.py:294-299`）：给**绝对** pos/quat 每标量加高斯噪声，空间不同。
- `troubleshooting.rst` 里的 "startup noise" 指日志噪声，无关。

**实现小坑**：`Waypoint(...)` 的 `noise` 默认是 `None`，而单臂 adapter 是 `if scale > 0.0`；直接构造 `noise=None` 的 Waypoint 执行会 `TypeError`。正常路径都会置浮点值，手工构造时应显式给 `0.0`。

### 3.3 `_EEFGenerationState`（`data_generator.py:63-78`）

每个 EEF 一个状态机，算法可直接修改（SkillGen 两阶段即用此）：

```python
current_subtask_index
current_trajectory: list[Waypoint]
subtask_step_index: int | None   # None 表示"需要规划下一段"
subtasks_done
constraint_hold_waypoint
is_currently_paused / _was_paused_prev_iter
pending_subtask_trajectory / is_in_motion_plan   # 两阶段用
```

**示例状态。** `env_id=0` 的 `franka` 初始 `current_subtask_index=0`、`subtask_step_index=None`；算法规划出第一段后把 `current_trajectory` 填入 waypoint 列表，并把步索引设为 0。四段结束后 `subtasks_done=True`。

---

## 四、源片段池：`DataGenInfoPool`（`autodata_core/pool.py`）

### 从 HDF5 构建

`from_hdf5()`（`68-94`）逐个 episode 调 `_add_episode()`。`_add_episode()`（`120-146`）从 `episode.data["obs"]["datagen_info"]` 取出各字段，并用 embodiment adapter 把 `actions` 反解成 passthrough 通道：

```python
passthrough_actions = self.embodiment_adapter.actions_to_passthrough_actions(ep_grp["actions"])
```

**示例池输出。** `demo_0/actions: [200,7]` 经单臂 adapter 得到 `passthrough_action["franka"]: [200,1]`，只保留夹爪通道；源目标位姿仍从 `target_eef_pose/franka` 读取。

### 子任务边界解析（关键细节）

`_parse_subtask_boundaries()`（`148-183`）把一条演示切成 `[(start, end), ...]`：

- 非 SkillGen：`start_index = prev_end`（**首尾相接**）。
- SkillGen（`uses_start_signals`）：用 `subtask_start_signals` 的**上升沿**定位起点：

```python
start_indicators = ep.subtask_start_signals[signal_name].flatten().int()
start_index = int((start_indicators[1:] - start_indicators[:-1]).nonzero()[0][0]) + 1
```

- 终点用 `subtask_term_signals` 的上升沿 +2；最后一段用整条轨迹长度。
- 解析后调 `_validate_subtask_offsets()`（`185-204`）：**用最坏情况偏移量做静态校验**，保证随机化后子任务仍非空、不重叠。

**名称与顺序来自任务配置。** 以 12 步小例为例：

```yaml
subtasks:
  arm:
    - description: 抓取方块
      subtask_term_signal: grasp
    - description: 抬高方块
      subtask_term_signal: lift
    - description: 放入碗中
```

代码依次处理这三项，并按配置中的信号名读取示范标注。`DatagenInfo` 里的 `grasp`、`lift` **只标记时间点**；代码不会观察轨迹后自行判断"这段是抓取"。最后一段没有完成信号，因为它直接延续到整条示范末尾。

**MimicGen：三段首尾相接。** 示例中 `grasp` 从索引 3 起为 1，`lift` 从索引 7 起为 1。边界解析把首次为 1 的那一步留在前一段，得到：

| 子任务 | 边界 `[start, end)` | 实际取出的步 |
| --- | --- | --- |
| 抓取 | `[0, 4)` | 0、1、2、3 |
| 抬高 | `[4, 8)` | 4、5、6、7 |
| 放置 | `[8, 12)` | 8、9、10、11 |

`[start, end)` 含 `start`、不含 `end`。三段只需两个内部切点，所以完成信号只有 `grasp` 和 `lift` 两个键。解析后的边界另存于 `pool.subtask_boundaries`；`DatagenInfo` 仍保存完整 12 步数据。

**SkillGen：技能片段之间可以留空档。** 除完成信号外，还使用每段的**开始信号**。假设标成：

```python
subtask_start_signals = {
    "grasp": [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    "lift":  [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
    "place": [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
}
```

同一条 12 步示范，此时切出的技能是：

| 子任务 | 保留的步 |
| --- | --- |
| 抓取 | `[1, 4)` |
| 抬高 | `[5, 8)` |
| 放置 | `[9, 12)` |

索引 4 和 8 落在技能之间。SkillGen 生成下一段技能后，取其首个位姿作为目标，让运动规划器从机器人当前状态规划到那里，再执行技能。

**注解流程要求**：SkillGen 的任务配置需为**每一段**提供信号名称，最后一项在 SkillGen 中还需写 `subtask_term_signal: place`，用作开始信号的键。最后一段的完成边界仍取整条示范长度，不读取 `place` 的完成信号。

**示例原始边界（Franka 200 步）。** 假设 `demo_0` 三个完成信号的上升沿在索引 38、88、138，得到四个半开区间 `[0,40)`、`[40,90)`、`[90,140)`、`[140,200)`；前三个终点等于上升沿索引 `+2`，末段终点为 `T=200`。这是人为设定的有效输入，不是对当前 LFS 指针的读取结果。

---

## 五、`DataGenerator.generate()` 主循环（重点）

`generate()`（`data_generator.py:521-611`）是一次「生成尝试」的完整生命周期。按执行顺序拆解。

### 5.1 复位 + 快照（`_reset_environment_for_generation`, `617-628`）

```python
env_id_tensor = torch.tensor([env_id], ...)
env.recorder_manager.reset(env_ids=env_id_tensor)
await env_reset_queue.put(env_id)      # 交给仿真循环去 env.reset(env_ids=...)
await env_reset_queue.join()
return env_id_tensor, self.datastream.get_scene_state(is_relative=True)  # 初始状态快照
```

复位请求走队列而非直接 reset，是为了与同步 `env_loop` 解耦。

**示例 5.1。** `env_id=0` 的 recorder 清空本次 episode，仿真循环执行 `env.reset(env_ids=[0])`；返回的 `initial_state` 是复位后的场景快照。假设此时 `cube_2` 平移为 `[0.60,0.10,0.02] m`，将在 5.4–5.5 用于选段与变换。

### 5.2 边界随机化（`randomize_subtask_boundaries`, `151-201`）

对每条源演示边界抖动，使不同生成演示不在完全相同的步数切换子任务：

```python
randomize_starts = self.algorithm.uses_subtask_start_signals
...
boundaries[:, 0, 0] += first_start_offsets           # 第一段起点偏移
for i in range(boundaries.shape[1]):
    if randomize_starts:                             # SkillGen：起点也随机
        boundaries[:, i, 0] += start_offset
    elif i > 0:                                      # 其他：上一段终点=本段起点
        boundaries[:, i, 0] = boundaries[:, i - 1, 1]
    boundaries[:, i, 1] += end_offsets               # 终点偏移
```

末尾三条 assert（`194-197`）保证：每段非空、段间递增、扁平化后单调不减。刷新逻辑见 `_maybe_refresh_randomized_subtask_boundaries()`（`639-647`）：**池变大时才重算**（SkillGen 会在生成中往池里加 episode）。

**示例 5.2。** `franka_cube_stack.yaml` 的前三段终点偏移范围是 `[10,20]`、末段 `[0,0]`；假设 `demo_0` 本次抽到 `+15,+12,+14,0`，则原始边界变成：

| 子任务 | 对象/动作 | 原始 `[start,end)` | 本次 `[start,end)` | 片段长度 |
|---:|---|---|---|---:|
| 0 | `cube_2` / 抓红块 | `[0,40)` | `[0,55)` | 55 |
| 1 | `cube_1` / 红块叠蓝块 | `[40,90)` | `[55,102)` | 47 |
| 2 | `cube_3` / 抓绿块 | `[90,140)` | `[102,154)` | 52 |
| 3 | `cube_2` / 绿块叠红块 | `[140,200)` | `[154,200)` | 46 |

非 SkillGen 的后一段起点直接取前一段**随机化后**的终点，因而保持首尾相接；起点偏移未配置时为 `[0,0]`。

### 5.3 规划下一段：算法钩子（`544-572`）

主循环里，只要某 EEF 的 `subtask_step_index is None`，就调用算法：

```python
while True:
    await asyncio.sleep(0)
    pool_lock = self.src_demo_datagen_info_pool.asyncio_lock
    async with _optional_lock(pool_lock):           # 锁住"池快照 + 边界表"的一致性
        randomized_subtask_boundaries, prev_pool_size = self._maybe_refresh...(...)
        for eef_name, eef_state in eef_states.items():
            if eef_state.subtasks_done or eef_state.subtask_step_index is not None:
                continue
            result = self.algorithm.plan_subtask_trajectory(...)
            if result is None:                       # 规划失败（SkillGen）
                return GenerationResult(initial_state=initial_state, success=False)
            next_trajectory, _is_motion_plan = result
            eef_state.current_trajectory = next_trajectory
            eef_state.subtask_step_index = 0
```

`plan_subtask_trajectory` 返回约定（`algorithms.py:85-96`）：

- `(waypoints, False)`：当作真实子任务执行，约束生效；
- `(waypoints, True)`：当作 MP transit 执行，约束跳过，算法自行把真实子任务 stash 起来；
- `None`：本次尝试失败。

**示例 5.3。** `franka` 步索引起初为 `None`，`mimicgen` 走默认分支，依次调用 5.4–5.6，返回 `(merged_waypoints, False)`；生成器保存该列表并将步索引设为 0。本例不需要 motion planner，也没有 `pending_subtask_trajectory`。

### 5.4 选择源演示（`select_source_demo`, `207-247`）

把每条源演示在该子任务窗口内的片段切出来，交给选择策略：

```python
strategy.select_source_demo(eef_pose=..., object_pose=...,
                            src_subtask_datagen_infos=..., **kwargs)
```

三种策略（`selection_strategy.py`）：

- `random`（`65-72`）：均匀随机；
- `nearest_neighbor_object`（`75-113`）：按源物体位姿与当前物体位姿的**位姿距离**（平移 + 旋转 arccos 距离）排序，在前 `nn_k` 里随机取一个；
- `nearest_neighbor_robot_distance`（`116-167`）：把源 EEF 位姿先变到「源物体系」，再映射到「当前物体系」，与当前 EEF 位姿比距离。

`select_source_demo()` 约束：`subtask_object_name is None` 时只允许 `random`（`218-219`），因为最近邻比较需要参考物体。

**示例 5.4。** 第一段 `object_ref=cube_2`、`selection_strategy=nearest_neighbor_object`、`nn_k=3`。设 `demo_0` 在段起点的 `cube_2` 平移为 `[0.50,0.00,0.02] m`，与 5.1 当前物体位姿的旋转均为单位阵。策略对 3 条源 episode 的段起点计算「平移距离 + 旋转角距离」，再从最近 3 条中随机取一条；这里**假设**输出源索引 `0`（`demo_0`），不意味着必然选中距离最近者。

### 5.5 组装子任务轨迹（`generate_eef_subtask_trajectory`, `253-365`）

「选择 + 变换」的核心。易忽略的细节：

**1. 是否需要重新选择**（`274-287`）：

```python
is_first_subtask = subtask_ind == 0
need_selection = is_first_subtask or policy.select_src_per_subtask
if not policy.select_src_per_arm:
    need_selection = need_selection and selected_src_demo_inds[eef_name] is None
...
if use_delta_transform is not None:
    need_selection = False      # 协调约束已决定 demo，无需再选
```

**示例选源开关。** YAML 同时设置 `select_src_per_subtask: true` 与 `select_src_per_arm: false`。当前代码里，第一次选择后 `selected_src_demo_inds["franka"]` 不再是 `None`，后面三段的 `need_selection` 被压成 `False`，沿用 `demo_0`。**实际行为是整次尝试只选一次**，不能仅按参数名理解为逐段重选（`data_generator.py:274-305`）。

**2. 首段锚定**（`331-344`）：首段（或 `transform_first_robot_pose`）会把**记录的 EEF 实际位姿**拼在目标序列前面，让后续插值从机器人真实位姿出发：

```python
src_eef_poses = torch.cat([src_subtask_eef_poses[0:1], src_subtask_target_poses], dim=0)
```

**示例片段形状。** 第一段切 `demo_0[0:55]`，实际 EEF 和目标 EEF 各为 `[55,4,4]`、夹爪为 `[55,1]`；首段加实际位姿锚后成为 `[56,4,4]` 和 `[56,1]`。`transform_first_robot_pose: false`，所以后面三段只使用各自的目标位姿，不再加锚。

**3. passthrough 通道筛选**（`321-326`）：只保留「本 EEF 自己的通道」+「非 EEF 通道（如 body）」，避免把另一条臂的夹爪动作串进来。

**4. 变换**（`_apply_subtask_transform`, `428-461`）：

```python
if use_delta_transform is not None:            # 协调：直接应用 delta
    return transform_source_data_segment_using_delta_object_pose(src_eef_poses, use_delta_transform)
if coord_transform_scheme is not None:         # 协调：先算 delta 并存回约束表
    delta = get_delta_pose_with_scheme(...)
    runtime_subtask_constraints_dict[key]["transform"] = delta
    return transform_source_data_segment_using_delta_object_pose(src_eef_poses, delta)
if subtask_object_name is not None:            # 常规：按物体位姿变换
    return transform_source_data_segment_using_object_pose(subtask_object_pose, src_eef_poses, src_subtask_object_pose)
return src_eef_poses                           # 无参考物体：原样使用
```

变换数学在 `transforms.py`：`transform_source_data_segment_using_object_pose`（`34-53`）= 先转到源物体系再转到当前物体系；`get_delta_pose_with_scheme`（`83-127`）支持 `TRANSFORM / TRANSLATE / REPLAY` 三种协调方案并叠加均匀噪声。

最后包成 `WaypointTrajectory`（`358-365`）返回。

**示例几何变换。** 常规路径计算 `T_new_eef(t) = T_current_object × inverse(T_source_object_at_segment_start) × T_source_eef(t)`。设源目标 EEF 平移为 `[0.50,0.00,0.20] m`，两边物体旋转均为单位阵，源/当前物体平移分别为 `[0.50,0.00,0.02] m` 与 `[0.60,0.10,0.02] m`，则该目标变为 `[0.60,0.10,0.20] m`。这只是无旋转差的特例；实际运算使用完整 4×4 矩阵。夹爪值不变；输出为一串 `Waypoint(pose=[4,4], passthrough_action={"franka": [1]}, noise=0.03)`，再包成 `WaypointTrajectory`。

### 5.6 合并插值段（`merge_eef_subtask_trajectory`, `467-515`）

基类默认路径即「生成段 + 合并插值」：

```python
use_prev_traj = force_use_prev_traj or (
    self.datastream.get_generation_policy().interpolate_from_last_target_pose and not is_first_subtask)
if use_prev_traj:
    init_sequence = WaypointSequence(sequence=[prev_executed_traj[-1]])   # 从上一段终点起
else:
    init_sequence = ... # 从机器人当前实际位姿起
traj_to_execute.add_waypoint_sequence(init_sequence)
traj_to_execute.merge(subtask_trajectory,
                      num_steps_interp=subtask.num_interpolation_steps,
                      num_steps_fixed=subtask.num_fixed_steps,
                      action_noise=float(subtask.apply_noise_during_interpolation) * subtask.action_noise)
traj_to_execute.pop_first()      # 丢掉仅用于锚定插值的种子 waypoint
```

`merge()` 本体在 `waypoint.py:227-275`：可先插值到 `other` 的首位姿，再固定 hold `num_fixed_steps` 步，然后接上 `other`。`force_use_prev_traj=True` 为 SkillGen 专用——让真实技能段从「MP 终点位姿」而非「实时机器人位姿」开始插值。

**示例 5.6。** 四段 YAML 都是 `num_interpolation_steps=5`、`num_fixed_steps=0`、`action_noise=0.03`、`apply_noise_during_interpolation=false`。首段从 reset 后当前 EEF 位姿接到第一个变换 waypoint；后续段因为 `interpolate_from_last_target_pose=true`，从上一段最后目标 waypoint 接入。桥接段噪声幅度是 0；源段噪声在 action 编码时施加于 6 维位姿，不改变夹爪值（`single_arm_embodiment_adapter.py`）。

### 5.7 收集 waypoint 与跨臂约束（`_collect_eef_waypoints`, `649-682`）

每 tick 前逐个 EEF 决定「往前走」还是「原地 hold」：

```python
is_paused = self._apply_constraint_progression_rules(...)
just_paused = is_paused and not eef_state._was_paused_prev_iter
...
if is_paused:
    if just_paused or eef_state.constraint_hold_waypoint is None:
        eef_state.constraint_hold_waypoint = deepcopy(eef_state.current_trajectory[eef_state.subtask_step_index])
    waypoint = deepcopy(eef_state.constraint_hold_waypoint)   # 保持不动
else:
    waypoint = eef_state.current_trajectory[eef_state.subtask_step_index]
    eef_state.constraint_hold_waypoint = deepcopy(waypoint)
```

`_apply_constraint_progression_rules()`（`684-738`）实现两类跨臂约束（定义见 `subtask_constraint_spec.py`）：

- **SEQUENTIAL_LATTER**（`706-715`）：后者执行到只剩 `min_time_diff` 步时停下等前者；`min_time_diff < 0` 表示前者完成前完全不启动。
- **COORDINATION**（`717-738`）：
  - `coordination_synchronize_start`：并发臂还没到该子任务时，把本臂 step 压回 0，实现同步起步；
  - `synchronous_steps`：当本臂进入尾段 `len(traj) - synchronous_steps` 时，标记并发约束 `fulfilled`，两边在同步窗口内锁步。

MP transit 期间直接返回 `False`（`694-695`）——**transit 不受约束**。

**示例 5.7。** 本任务只有 `franka` 一个 EEF，也没有 `constraints`，所以每 tick 直接取当前 waypoint，不走跨臂 hold；本节规则用于双臂任务。

### 5.8 执行一步 + 推进 + 完成（`582-596` 与 `740-808`）

```python
exec_success = await multi_waypoint.execute(...)          # 一次 env step + 判成功
buffers.success = buffers.success or exec_success          # 成功一次即锁定
self._advance_subtask_progress(...)
if self._all_subtasks_completed(eef_states):
    break
```

`_advance_subtask_progress()`（`740-759`）：暂停中的 EEF 不推进；`step_index` 到达轨迹末尾就调 `_handle_subtask_completion()`。

`_handle_subtask_completion()`（`761-808`）：

- 若在 MP 阶段，仅把 `step_index=None` 触发「resume 路径」，**不推进子任务**；
- 处理约束「前者完成 → 置后者 `fulfilled`」和协调的 `finished` 断言；
- 最后一个子任务完成时置 `subtasks_done=True`，并 `append(current_trajectory[-1])` 让该臂**原地保持**直到另一臂结束；
- 否则 `step_index=None; current_subtask_index += 1`。

**示例 5.8。** 假设某 tick 当前 EEF 平移为 `[0.58,0.10,0.20] m`，目标为 `[0.60,0.10,0.20] m`，朝向相同，夹爪透传值 `-1`，本步位姿噪声暂取 0：

```text
_collect_eef_waypoints() -> {"franka": Waypoint(target_pose, {"franka": [-1]}, noise=0.03)}
MultiWaypoint.execute() -> target_eef_pose_dict={"franka": [4,4]}
Franka adapter -> action=[0.02, 0, 0, 0, 0, 0, -1]  # [7]，仅此特例
env_action_queue.put((0, action)) -> env_loop 收齐两个环境的 action -> env.step([2,7])
success_term.func(...)[0] -> bool -> buffers.success |= exec_success
```

实际位姿噪声由采样决定，前 6 维还可能裁剪至 `[-1,1]`，因此 action 不会固定等于示意数组。每段最后一个 waypoint 执行后，状态机把 `current_subtask_index` 推至下一段；第四段结束置 `subtasks_done=True`。

### 5.9 录制与返回（`598-611`）

```python
env = self.datastream.get_env()
env.recorder_manager.set_success_to_episodes(env_id_tensor, torch.tensor([[buffers.success]], ...))
if export_demo:
    env.recorder_manager.export_episodes(env_id_tensor)
return GenerationResult(initial_state=initial_state, success=buffers.success)
```

是否导出失败 episode 由之前 `setup_env_config` 里按 `keep_failed` 设置的 `DatasetExportMode` 决定（`env/isaaclab_env_interface.py`）。

**示例 5.9。** 假设本次尝试某步满足 `success_term`，`buffers.success` 锁存为 `True`；四段结束后返回 `GenerationResult(initial_state=<5.1 快照>, success=True)`，recorder 标记并导出 episode。若整条轨迹都未成功，则返回 `False`，本例 `keep_failed=false` 会使失败 episode 不进入成功数据集。SkillGen 规划失败可提前返回 `False`，该路径未走完 recorder 导出（`data_generator.py:521-611`）。

---

## 六、算法插件机制（`autodata_core/algorithms.py`）

### 自动注册

`_AlgorithmMeta`（`44-51`）在类创建时，只要子类定义了 `name` 就写进全局表：

```python
class _AlgorithmMeta(type):
    def __new__(mcs, name, bases, class_dict):
        cls = super().__new__(mcs, name, bases, class_dict)
        if bases and class_dict.get("name"):
            REGISTERED_ALGORITHMS[class_dict["name"]] = cls
        return cls
```

CLI 的 `--alg` choices 硬编码在 `generate_dataset.py:40`，需与注册表人工保持一致。

### 五个行为开关（`GenerationAlgorithm`, `54-65`）

| 属性 | 含义 |
|---|---|
| `name` | 注册键 |
| `expected_eef_count` | `1` / `2` / `(1,2)` |
| `requires_motion_planner` | 构造时是否要 planner |
| `uses_subtask_start_signals` | 池是否按 start signal 解析边界 |
| `supports_coordination` | 是否支持跨臂协调约束 |

构造时校验在 `DataGenerator.__init__`（`111-114`）→ `_validate_eef_count_for_algorithm`（`123-130`）、`_validate_coordination_for_algorithm`（`132-138`）、`_validate_terminal_subtask_offsets`（`140-145`，最后一个子任务的 `subtask_term_offset_range` 必须为 `[0,0]`）。

### 默认实现（Mimic / DexMimicGen）

`GenerationAlgorithm.plan_subtask_trajectory`（`74-142`）分两条路：

1. **Resume 路径**（`110-123`）：若 `pending_subtask_trajectory` 存在，用它做 `force_use_prev_traj=True` 的合并，供 SkillGen 收尾；
2. **默认路径**（`127-142`）：`generate_eef_subtask_trajectory` → `merge_eef_subtask_trajectory`，返回 `(merged, False)`。

`MimicGen`（`148-155`）与 `DexMimicGen`（`158-165`）只设置属性，行为完全继承默认。

**回到贯穿示例。** `mimicgen` 预期一个 EEF、不要求 planner、不使用子任务开始信号；因而第 4 节按完成信号切段，第 5.3 节得到 `(waypoints, False)`。若改用 `dexmimicgen`，还需双臂任务描述、embodiment 与可能的跨臂约束，不能直接复用这条 Franka 单臂示例。

---

## 七、SkillGen 的两阶段（transit + skill）

`SkillGen`（`168-273`）只覆写 `plan_subtask_trajectory`。核心是「**先规划避障 transit，把真实技能段 stash 起来**」。

新子任务时（`220-256`）：

```python
subtask_traj = data_generator.generate_eef_subtask_trajectory(...)  # 真实技能段
target_pose = subtask_traj[0].pose
expected_attached_object = data_generator.datastream.get_expected_attached_object(...)  # 手里拿的物体，供 planner 做碰撞
planner = self.motion_planners[env_id]
planning_success = planner.update_world_and_plan_motion(target_pose=..., expected_attached_object=..., ...)
if not planning_success:
    return None                       # 规划失败 → 整个 attempt 失败
mp_waypoints = self._convert_planned_trajectory_to_waypoints(planner, subtask_traj[0].passthrough_action)
eef_state.pending_subtask_trajectory = subtask_traj    # stash
eef_state.is_in_motion_plan = True
return mp_waypoints, True
```

下一次调用命中 resume 路径（`205-218`），用 `force_use_prev_traj=True` 把技能段从 MP 终点接上。该 resume 必须在**父类**的 `plan_subtask_trajectory` 里也有对应分支（`110-123`）——父类被子类复用。

配套细节：

- MP transit 期间约束不生效（`data_generator.py:694-695`）；
- MP 段执行完时 `_handle_subtask_completion` 只重置 `step_index`、不推进子任务（`775-777`）；
- `_convert_planned_trajectory_to_waypoints`（`258-273`）读取 `config.motion_noise_scale` 给每个 waypoint 加噪声。

**cuRobo 的轨迹放在哪里。** `DatagenInfo` 保存的是源示范；SkillGen 运行时让 cuRobo 规划「当前状态 → 下一技能起点」的过渡轨迹。规划结果从 `get_planned_poses()` 读出，转换为 `Waypoint` 执行；待执行的技能轨迹暂存在 `pending_subtask_trajectory`。两者都**不写回源** `DatagenInfo`。

```text
源 DatagenInfo ──切片、变换──→ 技能片段
当前机器人状态 ──cuRobo 规划并执行──→ 技能起点 ──执行技能片段──→ 技能结束
```

**与本例的分界。** 若将算法换成 `skillgen`，输入还需要子任务开始信号及起点偏移、每个环境的 cuRobo planner；输出先是 `(transit_waypoints, True)`，完成 transit 后才执行暂存的技能段。前述 `demo_0` 边界与 action 数值仅用于 MimicGen，不能直接当作 SkillGen 的模拟运行结果。

---

## 八、异步多环境并发模型

### 队列 + 锁步仿真

`scripts/generate_dataset.py:189-228` 为每个 `env_id` 起一个 asyncio task，共享一个 `DataGenerator`、`env_reset_queue`、`env_action_queue`。同步侧 `env_loop`（`env/isaaclab_env_interface.py:209-299`）是「锁步」的：

```python
while env_action_queue.qsize() != env.num_envs:   # 等所有 env 都排队一个 action
    asyncio_event_loop.run_until_complete(asyncio.sleep(0))
    ...
    while not env_reset_queue.empty():            # 顺手处理 reset 请求
        env.reset(env_ids=env_id_tensor)
actions = gather(所有 action)
env.step(actions)                                  # 一次批量 step
```

每个 env 的「尝试逻辑（含失败重试）」在各自 task 里独立跑；`env_loop` 只负责统一推进仿真和统计。

**示例同步点。** `env_id=0` 的 5.8 节 action 入队后要等 `env_id=1` 也提供该 tick 的 7 维 action；`env_loop` 组为 `[2,7]`，一次 `env.step()` 推进两个环境，再放行两边各自的生成 coroutine。等待期间可处理环境 0 或 1 的 reset 请求。

### 池的并发保护

多个 task 共享源池，且 SkillGen 可能在生成中往池里加 episode，`_optional_lock`（`data_generator.py:37-45`）只在 `asyncio_lock` 非 None 时才加锁；默认静态池不加锁，零开销。加锁范围覆盖「刷新边界表 + 调算法规划」（`546-547`）。

### 停止条件

`env_loop` 每次统计变化时读 `stats`（`277-291`）：

```python
check_val = num_success if guarantee_success else num_attempts
if check_val >= num_trials:
    return True
```

即 `guarantee_success=true` 攒够 `num_trials` 个**成功**，否则跑够 `num_trials` 次**尝试**。`stats` 由 `run_data_generator`（`generate_dataset.py:135-164`）累加。最终可选写入 JSON sidecar（`autodata_utils/generation_result.py`，原子写：临时文件 + `fsync` + `os.replace`）。

**示例运行输出。** 假设最后累计 3 次尝试、2 次成功、1 次失败，则达到本例 `num_trials=2` 的成功阈值，终端可出现 `2/3 (66.7%) successful demos generated`。若正常达到停止条件，`--result_file` 对应 JSON 形如：

```json
{
  "algorithm": "mimicgen",
  "requested_trials": 2,
  "num_success": 2,
  "num_failures": 1,
  "num_attempts": 3
}
```

`--output_file` 对应 HDF5 的 `data/` 下是 recorder 导出的成功 episode；每条至少有 `actions` 数据集、`initial_state` 组、`obs` 组，action 末维为 7。episode 名、数量、长度与成功比例以真实文件为准。取得可运行数据后，可在容器内用 `python scripts/validate_dataset.py <file>` 检查结构；结构检查不等于物理回放成功。

---

## 九、一次完整尝试的时序总结

```
run_data_generator (per env)
  └─ DataGenerator.generate(env_id)
       1. _reset_environment_for_generation  ── env_reset_queue ──▶ env_loop: env.reset()
          └─ 返回 initial_state 快照
       2. _build_runtime_subtask_constraints()   # 把 sequential/coordination 展开成运行期字典
       3. _initialize_eef_states()               # 每 EEF 一个状态机
       ┌─ while not all subtasks done ───────────────────────────────┐
       │  async with pool lock:                                      │
       │     可能重建 randomized_subtask_boundaries                   │
       │     对每个无轨迹的 EEF:                                      │
       │        algorithm.plan_subtask_trajectory(...)               │
       │          ├─(SkillGen) curobo 规划 transit + stash 技能段     │
       │          └─(默认) select_src → transform → merge 插值        │
       │  _collect_eef_waypoints()  # 应用跨臂约束，决定 hold/前进     │
       │  MultiWaypoint.execute()   # 编码 action ── action_queue ──▶ env.step()
       │      └─ 判 success，锁定 buffers.success                    │
       │  _advance_subtask_progress() / _handle_subtask_completion()  │
       └─────────────────────────────────────────────────────────────┘
       4. recorder.set_success_to_episodes + export_episodes
       5. return GenerationResult(success, initial_state)
```

**将图中的箭头代入本例**：`demo_0[0:40)` 经终点随机化为 `[0:55)` → 选中源索引 `0` → 目标 EEF 位姿按 `cube_2` 当前位姿变换 → 加 5 步桥接并变成 waypoint → 单 tick 编成 7 维 action → 与另一环境的 action 一起 `env.step()` → 四段结束后标记并导出成功 episode。图中 SkillGen 分支与跨臂约束不属于本次 Franka MimicGen 模拟。

---

## 十、关键设计点回顾

1. **算法无关的骨架**：边界随机化、源选择、变换、插值合并、约束执行、录制全在 `DataGenerator` 里；算法只通过 `plan_subtask_trajectory` 一个钩子介入。
2. **两阶段 stash/resume**：把「动作规划」这类异构能力塞进同一循环，靠 `_EEFGenerationState.pending_subtask_trajectory` + `is_in_motion_plan` 传递状态，生成器完全不知道 cuRobo 的存在。
3. **Datastream 作为唯一读接口**：生成器/planner 都通过它读位姿、关节、物体、USD stage，`get_env()` 是明确的 escape hatch。
4. **池加锁的粒度**：只在静态池之外才付锁开销，且锁住「边界表 + 选段」这一致性窗口。
5. **成功即锁定**：`buffers.success = buffers.success or exec_success`，成功条件一旦在某步成立就锁定，不要求保持。
6. **位姿是唯一可变换的中间表示**：action 是相对量、不可变换；Waypoint 把"要执行什么"统一成绝对位姿，作为算法与仿真器之间的接口。

---

## 附录 A：Waypoint 与 DatagenInfo 的区别

一句话：**`DatagenInfo` 是"记录"（源示范里过去发生了什么），`Waypoint` 是"指令"（本次要执行的下一步目标）。** 数据从前者单向流向后者。

| 维度 | `DatagenInfo`（`datagen_info.py:16-64`） | `Waypoint`（`waypoint.py:26-51`） |
|---|---|---|
| 角色 | 数据容器 / schema，被动描述 | 执行指令，驱动 env 前进一步 |
| 时间跨度 | 整条 episode，字段 `[T, ...]` | **单帧**（一个 tick）`[4,4]` / `[D]` |
| 来源 | HDF5 源演示，`pool.from_hdf5()` 读入 | 运行时由算法从源片段变换/插值/merge 产出 |
| 生命周期 | 静态、只读、长期存在于源池 | 消费即推进，随状态机迭代 |
| 载体 | `pool.datagen_infos` | `current_trajectory` / `pending_subtask_trajectory` |
| 位姿 | **两套**：`eef_pose`（实际观测）+ `target_eef_pose`（动作目标） | **只有一套** `pose`（目标） |
| 物体信息 | 有 `object_poses` | **没有**（变换阶段已用掉） |
| 子任务信号 | 有 `subtask_term/start_signals` | **没有**（切段阶段已用掉） |
| 噪声 | 无 | 有 `noise` |
| 透传 | `passthrough_action: {ch: [T,D]}`（历史序列） | `passthrough_action: {ch: [D]}`（本帧值） |
| 关节 | 无 | 可选 `joint_seed` |

三个易忽略点：

1. **位姿套数不同**：`DatagenInfo.eef_pose` 是"现在在哪"，`target_eef_pose` 是"这步想去哪"；执行只需目标，所以 Waypoint 只留 `pose`，当前实际位姿由 adapter 从仿真器**现读**（`single_arm_embodiment_adapter.py`）。
2. **物体信息被"消耗"**：`object_poses` 只在变换阶段当参考系，算完后目标已是世界系绝对量，不再需要。
3. **noise 是 Waypoint 独有**：源示范是"干净"的，噪声是生成期注入的扰动，属于"未来指令"的属性。

粒度对应（方向相反：一个存源、一个存目标）：

```
DatagenInfo                     一条源示范           [T, ...] 全字段
  └─ 切段 + 变换 + 插值 ──►
       WaypointSequence         本次要执行的一段      [T, 4, 4] → 一串 Waypoint
         └─ Waypoint            其中的一步            [4, 4] + [D]
       WaypointTrajectory       多段拼成的完整行程
         └─ MultiWaypoint        单个 tick 的多臂捆绑 → 一个 action step
```

---

## 附录 B：Waypoint 与 ROS2 / 真机的关系

**不是。** `Waypoint` 不是 ROS2 消息，也不是"向真机传输的数据块"——它是 AutoData 在**单个 Isaac Sim/Isaac Lab Python 进程内**使用的中间表示对象。

- 全仓搜索 `rclpy` / `ros2` / `rospy` / DDS 无运行时命中；依赖是 `isaaclab`（`generate_dataset.py:36` 的 `AppLauncher`、`isaaclab_env_interface.py` 的 `gym.make` / `env.step`）。
- `MultiWaypoint.execute` 的"消费"是同进程的 `env.step()` 与一个 `asyncio.Queue`（让异步生成协程与同步 `env_loop` 解耦、实现多环境锁步），**数据从不离开进程**。
- `Waypoint` 是普通 Python 对象，字段是 `torch.Tensor`，没有序列化、没有 topic、没有消息头。

| | ROS2 消息 | AutoData Waypoint |
|---|---|---|
| 场景 | 真机/分布式实时控制 | 离线仿真数据生成 |
| 传输 | 跨进程/网络（DDS） | 同进程对象引用 |
| 目的 | 驱动真实硬件 | 生成训练数据集（HDF5） |
| 时间 | 实时/软实时 | 仿真步进，无实时约束 |

即使做真机部署，也需在 Waypoint 下游另加一层"action → ROS2 消息"的桥接，该层当前不存在于仓库。

---

## 附录 C：是否领域惯例

**是，但仅限"示范变换式数据生成"这个子领域。** 这不是 AutoData 自创：

- **MimicGen**（Mandlekar et al. 2023, `arXiv:2310.17596`）——`algorithms.rst:36-38`：每个子任务段相对其参考物体存储，换物体位姿回放就是末端轨迹的刚体变换。工作空间就是 EEF 目标位姿。
- **DexMimicGen**（Jiang et al. 2024, `arXiv:2410.24185`）——把该 recipe 扩到双臂，按臂各存各的段。
- **SkillGen**（NVIDIA）——段间插入 cuRobo 规划的 transit，规划输入输出同为位姿，天然接得上。
- 上游 **Isaac Lab Mimic**（NVIDIA）用 `DataGenInfo` + `target_eef_pose` + `generate_eef_subtask_trajectory`，本仓 `autodata_core` 与其同源（`datagen_info.py` 开头注明 *"generator-internal stand-in for the eventual Datastream abstraction"*）。
- 更广地，运动规划（cuRobo）本身以 "waypoint" 为接口（`motion_planners.rst` 有 `get_next_waypoint_ee_pose()`）。

**不是惯例的部分**（避免过度推广）：

- **RL / VLA 训练管线**直接在 action 或 observation 上工作，没有 Waypoint 层。
- **遥操真机下发**传的是 action / 关节指令或 ROS 消息，不经过这层。
- 若某个生成算法**不需要变换、只做原样回放**，这层的价值会退化成"给序列加个标签"。

---

## 附录 D：涉及文件速查

| 主题 | 文件 |
|---|---|
| 主编排器 / 生成循环 | `autodata_core/data_generator.py` |
| 算法注册表与 SkillGen | `autodata_core/algorithms.py` |
| 源片段池与边界解析 | `autodata_core/pool.py` |
| Waypoint / 轨迹 / 执行 | `autodata_core/waypoint.py` |
| 源数据 schema | `autodata_core/datagen_info.py` |
| 位姿变换 | `autodata_core/transforms.py` |
| 源演示选择策略 | `autodata_core/selection_strategy.py` |
| Datastream 读接口与 action 编解码 | `autodata_interfaces/datastream/datastream.py` |
| env 配置与锁步循环 | `autodata_interfaces/env/isaaclab_env_interface.py` |
| 编码 action 的 adapter | `autodata_interfaces/embodiments/single_arm_embodiment_adapter.py`、`bimanual_embodiment_adapter.py` |
| 约束定义 | `autodata_interfaces/tasks/subtask_constraint_spec.py` |
| 生成策略 / 子任务规格 | `autodata_interfaces/tasks/generation_policy_spec.py`、`subtask_spec.py` |
| CLI 入口 | `scripts/generate_dataset.py` |
| 结果文件 | `autodata_utils/generation_result.py` |
