# Arena RoboLab：场景、任务和评估配置解耦说明

版本 v001；材料核对日期 2026-10-13（Asia/Shanghai）。依据固定提交 98866596fd024d96c874fe6fb95ae916d1133629。源码静态检查，未运行仿真、模型或完整 Arena schema 验证。

## 文件与来源

- configs/scenes/banana_bowl.yaml：官方场景原文件，保留版权头。
- configs/tasks/banana_in_bowl.yaml：官方任务原文件，保留版权头。
- configs/evaluation.yaml：本说明按同版本 Experiment Runner 加载器编写的评估示例，不是官方现成文件。

官方来源分别为 isaaclab_arena_environments/robolab/scenes/banana_bowl.yaml 和 tasks/banana_in_bowl.yaml。评估文件将 environment.type 指向任务文件；任务用 external_yaml 引用场景；任务参数引用场景 id。机器人仍在场景文件中；策略仍在评估文件中，不是每一模块都单独一个文件。

## 场景参数逐项说明

| 字段 | 当前值 | 含义与可修改量 |
|---|---|---|
| embodiment.id | droid | 场景内部唯一节点 ID，不是控制器选择器 |
| embodiment.registry_name | droid_abs_joint_pos | 从注册表加载 DROID 绝对关节位置控制 embodiment；换控制方式必须与策略输出兼容 |
| embodiment.params | {} | 不额外传构造参数，使用 embodiment 默认值；该类支持 enable_cameras、initial_pose、initial_joint_pose、stand_height_m 等，类型与含义须按构造签名 |
| background.id | maple_table_robolab | 任务和关系引用的背景节点 ID |
| background.registry_name | maple_table_robolab | 加载枫木桌背景资产 |
| background.params | {} | 使用该背景资产默认构造设置 |
| objects[0].id | banana | 被抓取物体的节点 ID |
| objects[0].registry_name | banana_ycb_robolab | 实际加载的香蕉资产 |
| objects[0].params | {} | 使用香蕉资产默认构造设置 |
| objects[1].id | bowl | 目标容器节点 ID |
| objects[1].registry_name | bowl_ycb_robolab | 实际加载的碗资产 |
| objects[1].params | {} | 使用碗资产默认构造设置 |
| relations[0] | is_anchor / maple_table_robolab / null | 桌子作为摆放锚点，无参考物体 |
| relations[1] | on / bowl / maple_table_robolab | 碗放在桌面上 |
| relations[2] | on / banana / maple_table_robolab | 香蕉放在桌面上；不是初始就在碗内 |
| relations[*].params | {} | 使用对应空间关系默认参数 |

registry_name 选实现，id 供内部引用，params 传该实现的构造参数。params 并非允许任意属性的通用字典。更换背景后需重新确认桌面语义、机器人基座位置、放置约束与可达性。On 不是坐标或随机范围；摆放系统结合资产和关系实现求位姿。

所有资产节点 ID 必须唯一。修改 id 必须同步修改 relations.subject/reference 及任务内对象引用。只替换 registry_name 可以保留引用，但任务自然语言需要对应实际对象。

## 任务参数逐项说明

| 字段 | 当前值 | 含义与可修改量 |
|---|---|---|
| env_name | banana_in_bowl | 环境名称；可修改，建议反映任务 |
| external_yaml | ../scenes/banana_bowl.yaml | 相对本任务文件的场景路径 |
| task.composition | atomic | 单一原子任务，要求 subtasks 恰好一项；parallel/sequential 可组合多个任务 |
| task.description | pick up the banana and place it in the bowl | 自然语言指令；不会自动更改物理成功判据 |
| subtasks[0].kind | PickAndPlaceTask | 从 TaskRegistry 获取任务实现 |
| params.pick_up_object | banana | 按 ID 解析为场景中的香蕉 Asset |
| params.destination_location | bowl | 按 ID 解析为碗 Asset |
| params.background_scene | maple_table_robolab | 按 ID 解析为背景 Asset，其 object_min_z 参与掉落失败判定 |
| params.episode_length_s | 70.0 | 最大回合仿真时间，单位秒；可能提前因成功或失败终止 |

图任务 params 会传给任务类构造函数，因此可在本示例的任务 params 中显式加入 force_threshold: 0.1、velocity_threshold: 0.003、support_cone_half_angle_rad: 0.7853981633974483，分别是目标对物体的最小滤波法向支撑力（N）、物体最大线速度阈值（m/s）以及支撑力相对于世界 +Z 的允许半锥角（rad）。后两者源码约束为速度阈值非负、角度在 [0, pi/2)。这与 Python 入门环境未暴露上述字段不同。更改这些阈值会改变成绩判定，比较模型时应固定。

该任务的成功进度是：物体稳定、从稳定参考位置抬起、物体放置于目标并满足相关判据；不能只用“看起来在碗里”代替。Task 同时提供 SuccessRateMetric 和 ObjectMovedRateMetric。精确几何/接触条件以同版本 predicates 为准。

## 评估参数逐项说明

| 字段 | 示例值 | 含义与修改效果 |
|---|---|---|
| shared | 公共配置 | 各 Run 默认值，Run 中同名字段覆盖它 |
| environment.type | configs/tasks/banana_in_bowl.yaml | 任务图文件入口；此路径按进程工作目录解释，不按 evaluation.yaml 位置解释 |
| environment.enable_cameras | false | 当前示例不要求机器人相机；视觉策略通常应启用并确认加载后的有效相机设置 |
| num_envs | 1 | 并行环境数，必须大于零 |
| env_spacing | 2.5 | 环境实例空间间距（米），不是物体间距 |
| seed | 42 | 环境随机种子 |
| placement_seed | 42 | 单独指定放置系统种子；alt Run 两个种子均改为 43 |
| policy.type | zero_action | 返回全零动作，不需权重；只验证配置链路，不是自主抓放策略 |
| rollout_limit.num_episodes | 3 | Run 的总完成回合停止阈值，不是每个并行环境的次数 |
| num_rebuilds | 1 | 从头构建环境次数，默认一次 |
| runs.baseline | {} | 全部继承 shared |
| runs.alternate_placement | seed=43 / placement_seed=43 | 改变随机条件，不保证必然产生某个指定位置或每回合都重新采样 |

特别注意：官方场景采用绝对关节位置控制，零动作会给机械臂发送零关节目标，不能理解为保持初始姿态；可能运动或碰撞。若要做静止保持，应使用匹配控制器的保持策略。若改用相对控制，则场景不再与官方原文件完全相同，要记录为派生版本。

num_episodes 与 num_steps 互斥。并行环境同一步可能同时结束，实际完成数可以超过阈值，应读取实际回合数。num_rebuilds>1 时总回合预算分配给重建，要求预算不小于重建数；builder.seed 按重建编号递增，但显式 placement_seed 不会因此自动递增。想每回合重采样，可研究 environment_builder.resolve_on_reset，而不是只加 seed。

可扩展的执行量：语言指令覆盖 language_instruction；record_trajectories 记录逐步轨迹；presets 选择受支持后端；variations 采用已经注册的随机扰动和采样器。视觉模型的 checkpoint、远程主机/端口、适配器等字段取决于 policy.type 对应 PolicyCfg，不能把其他策略字段直接填进 ZeroActionPolicyCfg（它没有额外参数）。设备、视频、输出路径等也可由 Runner CLI 控制。

## 关联规则与加载边界

1. 从包根目录启动，使 evaluation.environment.type 的 configs/tasks 路径正确。
2. loader 读取任务 YAML，以任务所在目录解析 ../scenes/banana_bowl.yaml。
3. 将两个文件的顶层键组合为一份图；不是深度覆盖，重复顶层键会报错。
4. 用 registry_name 创建场景节点，并检查唯一 ID 和关系引用。
5. task.params 中 Asset 类型参数按 ID 解析，数值参数传给构造函数。
6. builder 创建仿真环境，policy 产生动作，Run 按回合预算执行并保存证据。

锁定版本 external_yaml 仅支持入口引用一个文件，被引用文件不能继续嵌套引用。场景与任务不要同时定义 objects、task、embodiment 等同名顶层键。shared/runs 的覆盖机制与 external_yaml 的互斥键合并不是同一机制。

## 运行位置和命令

以下为待在 GPU 环境验证的命令。先按官方安装方式准备固定版本的 Arena 及其运行环境。本包不是完整的仿真依赖。

在已有 Arena 运行环境里，将 ARENA_ROOT 设置为本机 Arena 源码根目录，并将工作目录切换到本包根目录（即 report.md 与 configs 同级的目录）：

```bash
python "$ARENA_ROOT/isaaclab_arena/evaluation/experiment_runner.py" \
  --viz kit \
  --experiment_config configs/evaluation.yaml
```

若在容器中运行，必须保证源码和本包都可见；ARENA_ROOT 用容器内源码路径。不要在机器上没有驱动时把 --device cpu 当作完整的无 GPU 仿真替代方案。

输出默认在工作目录 outputs/<timestamp>/，包含实验汇总 arena_experiment_result.json，以及各 Run 的 episode_results_rebuild0.jsonl。completed 表示执行完成，不代表任务成功；有效模型比较需检查逐回合 success、实际样本数和异常。

## 修改建议

- 换抓取物体：场景 objects.registry_name；若改 id，任务及关系同步改；description 同步改。
- 换目标容器：同上；验证几何、接触与可达性。
- 改任务时限或阈值：任务 params；模型比较时冻结判分协议。
- 换模型：评估 policy，保持测试环境相同，核对动作/观测契约。
- 改吞吐：评估 num_envs，不能把不同并行数导致的样本预算差异误认为模型提升。
- 改摆放分布：空间关系/放置配置或注册 variation；seed 只决定随机序列。
- 改相机、灯光或物理：使用对应资产构造参数、图扩展字段或已注册 variation；不能直接把 Python 入门环境的 hdr/light_intensity 等字段移植到任意图任务入口。

## 固定版本证据

源文件 URL 前缀：https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/

- isaaclab_arena_environments/robolab/scenes/banana_bowl.yaml
- isaaclab_arena_environments/robolab/tasks/banana_in_bowl.yaml
- isaaclab_arena/environment_spec/arena_env_graph_yaml_loader.py
- isaaclab_arena/environment_spec/arena_env_graph_task_conversion_utils.py
- isaaclab_arena/hydra/typed_experiment_loader.py
- isaaclab_arena/evaluation/run_execution.py
- isaaclab_arena/evaluation/policy_runner.py
- isaaclab_arena/tasks/pick_and_place_task.py
- isaaclab_arena/embodiments/droid/droid.py

交付：本地源包已准备。飞书和 ChatGPT 尚无已配置的指定目的地，也未取得相应上传能力；本地文件链接不是已上传回执。
