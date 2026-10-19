# AutoData 与 Arena 共用配置：现状分析与设计建议

版本：v001。材料核对：2026-10-13，Asia/Shanghai。

## 结论与范围

可以让用户维护同一套配置来驱动 AutoData 数据生成和 Arena 策略评估，但当前配置不能不经适配直接作为双方的完整运行入口。已有 OpenArm 左臂抓取放置环境非常适合作为公共基础；推荐“一个公共入口 + 一个环境定义包 + 生成/评估两个执行配置 + 两侧适配器”。用户只维护公共源配置，工具生成双方所需参数，不再手工同步副本。

用户确认讨论的是当前工作区的 AutoData / Arena。未提供所谓夏季测试配置的独立路径，本次以两边已有的 OpenArm 抓放配置与 2026-10-13 Arena 交付包为具体依据。若原测试配置是另一版本，其差异仍需单独核对。本次未执行仿真或训练，也未实施配置加载器。

Arena 在这条链路中评估的是策略在任务环境中的表现，不会因为配置共用就自动完成 HDF5 数据集质量检查。数据生成后的标注持久化、转换完成和数据回读仍需独立验证。

## 1. 当前配置实际如何生效

AutoData 路径：

1. 注册模块 `openarm_autodata.tasks.pick_place` 把左臂 Gym ID 绑定到 `OpenArmLeftPickPlaceEnvCfg`。
2. `scripts/generate_dataset.py` 通过 CLI 或源数据集元数据确定环境 ID；`env_profile.base_env` 是匹配检查，当前脚本不会自动用它替代环境选择。
3. Python 环境定义提供场景、机器人、控制器、相机、观测、reset 和成功判据。
4. task YAML 提供 SkillGen 子任务、示教选择策略、生成目标数量和过滤策略；embodiment YAML 提供生成器的位姿/动作转换；env_profile YAML 提供环境补丁和规划器名称。
5. `setup_env_config()` 应用 profile 后，提取 success 判据并将 `env_cfg.terminations = None`，添加数据记录器。生成的成功检查与失败处理不能等同于评估端环境 done。

Arena 路径：

1. `scripts/run_arena_eval.sh` 调用原生 `policy_runner`，通过 external environment class 加载 `openarm_arena.environment:OpenArmPickPlaceEnvironment`。
2. 该类直接实例化交付包内的 `OpenArmLeftPickPlaceEnvCfg`，复制机器人、动作、观测、场景和 reset，增加 Arena Task / Metric。
3. `reference/` 中 AutoData 的 YAML 仅用于溯源；该入口没有读取它们。
4. `configs/evaluation.json` 自己明确标注为协议参考，要求把字段转成 CLI 参数；启动脚本没有读取这个 JSON。`policy_io.json` 也是接口约定，当前环境不依此自动构建控制器或观测。
5. 当前工作区另有 `openarm_arena_compat_20261013/local_environment.py`：把旧终止接口转成当前 Arena 要求的 `TaskTerminationCfg`，并补齐 PhysX 配置、保留选定设备。

因此，当前是“复用环境实现的复制快照”，还不是“同一套源配置同时生效”。

## 2. 已经一致的部分与实际差异

本次对照源目录和 Arena 交付包，对以下九个关键文件做了文本和 SHA-256 对比，全部一致：

- `tasks/pick_place/configs/{left_env_cfg.py,env_cfg.py,scene_cfg.py}`
- `tasks/pick_place/envs/mdp.py`
- `shared/configs/{robot_v2_cfg.py,camera_cfg.py}`
- `shared/calibration/cameras.json`
- `shared/envs/actions.py`
- `tasks/pick_place/__init__.py`

具体哈希和相对路径见 `evidence.json`。这证明上述文件当前内容一致，不证明未来自动同步，也不代表已比较整个资产树。

| 配置内容 | 当前情况 | 共用策略 |
|---|---|---|
| 场景、资产、左臂初态、被动右臂、reset | 两份 Python 配置一致 | 移到同一个版本化环境包，双方从其构造 |
| 控制器 | 7D 相对 TCP IK，平移 0.02 m、旋转 0.10 rad，正夹爪动作闭合 | 公共动作契约，同时约束 Python 控制器、生成转换器与模型适配 |
| 观测与相机 | 三路 640×480 RGB，状态、TCP、标定一致 | 共用传感器/原始观测定义，模型预处理单独配置 |
| 成功语义 | 复用 `cube_placed_on_pad` | 共用判据实现及全部有效阈值 |
| 生成子任务 | grasp / place、源示教选择、插值、cuRobo | 仅生成配置消费 |
| 回合结束 | 生成移除环境终止条件；评估保留成功、掉落、超时 | 按模式显式定义，不能机械共用 |
| 时限 | 源环境 30 秒；Arena 默认 90 秒 | 分别声明生成保护预算与评估预算 |
| 样本数量 | 生成目标为 10 条成功轨迹（失败上限 25）、keep_failed=false；评估每种子 100 个完成回合 | 使用不同字段和分母，禁止相互代替 |
| 随机数 | Python 默认 seed=1，生成 YAML seed=1，Arena CLI seed 可选 | 统一种子来源并在构建前设置，记录采样初态 |
| 版本接口 | 旧交付基线与当前 Arena 终止接口不同 | 语义配置稳定，适配器按锁定版本实现 |

公共成功规则的当前默认值：方块完整投影位于桌面鼠标垫内；底面高度误差 ≤0.008 m；左夹爪开度 ≥0.30 rad；线速度 ≤0.03 m/s；角速度 ≤0.5 rad/s。它是放置终态判定，并未强制要求先满足抓取高度历史。生成 YAML 中的 grasp 技能分段不能自动视为 Arena 的历史成功要求。

目标垫是桌子扫描网格的一部分，不是独立 Asset。通用配置应支持 `target_region` 及其 table 坐标系，不能为了套标准 PickAndPlaceTask 把它假设为独立容器。若替换为 Arena 通用任务，需要重新证明成功语义一致。

## 3. 为什么不能直接选一份已有 YAML 共用

1. task YAML 描述数据合成过程，不是完整环境。只有 object_ref、subtask_term_signal 等不能构建机器人、物理或 Arena 任务。
2. embodiment YAML 是 AutoData 生成器的转换器配置，不会自动修改 Python 动作配置；两处的动作缩放当前重复，未来可能漂移。
3. env_profile 的 schema 仅覆盖 base_env、刚体增补/物理属性、事件补丁及 planner，缺少完整相机、动作、任务成功和运行协议。不能把新顶层字段直接塞进现有 schema；它会拒绝未知字段。
4. Arena 的 evaluation.json 和 policy_io.json 当前没有自动执行语义。修改说明文件不保证运行参数改变。
5. 仅指向同一个 Python 类仍不够：生成前会应用 profile，Arena 目前不会；相同类名也可能因 PYTHONPATH 加载到不同副本。
6. seed 不足以保证两个程序同一初态。生成脚本在 `gym.make` 后才设置 Python/NumPy/Torch 种子，而环境配置本身另有 seed。并行数、reset 次序和框架版本也影响采样序列。

## 4. 推荐架构

```text
公共入口 experiment.yaml
  ├─ common：任务、场景、机器人、控制器、相机、reset、成功语义
  ├─ generation：SkillGen、示教、planner、生成/筛选/输出参数
  └─ evaluation：policy、预处理、时限、种子、回合数、指标
                 │
       无仿真依赖的校验/解析器
                 │
        解析为 resolved_config + 来源/哈希
          ┌──────┴──────┐
   AutoData adapter    Arena adapter
   基础环境 + 补丁      同一基础环境 + 补丁
   转换器/记录器        Task/Metric/Policy
   生成模式终止策略     评估模式终止策略
```

一个入口可以引用多份文件；“同一套”应指唯一维护来源和确定的解析结果。无需把 USD、相机标定、全部技能参数压成一个巨大的 YAML。

### 公共核心

建立独立、版本化的 `openarm_task_core` 或等价扩展包，只依赖所需 Isaac Lab 基础环境。包含机器人/资产、场景、控制器、相机标定、MDP、统一 reset 和可参数化环境工厂；不导入 AutoData 生成算法、cuRobo 或 Arena runner。双方锁定同一版本和资产哈希。不同机器可以安装同一包版本，无需共享绝对路径。

初期可保留现有 `openarm_autodata` 环境模块作为公共基础，整理依赖边界和版本来源。避免在同一 Python 路径中保留两个同名副本。启动时记录实际加载文件、内容哈希和有效配置。

### 配置解析规则

新增外层 manifest，不直接改变现有三种 AutoData YAML。先输出旧格式文件和明确的 CLI 参数，逐步改为双方共享配置对象。

- 路径相对于声明文件解析；资产和数据根路径由机器本地配置映射。
- 明确 SI 单位、env/robot/table 坐标系、XYZW 四元数、轴角旋转、动作顺序与夹爪符号。
- 定义覆盖顺序：基础默认 → common → 对应模式 → 允许的 CLI 覆盖。CLI 覆盖应回写有效配置；正式评测禁止静默改公共判据。
- 未知键、未支持的机器人/控制模式、缺失资产或对象引用应在仿真启动前报错，禁止忽略。
- 公共场景/控制/成功参数只定义一次；生成转换器、Arena 控制器、模型动作反归一化从同一动作契约派生或校验。
- 成功函数和默认阈值要展开记录，不能只留下空 params 导致依赖版本改变成绩。

### 两个适配器

AutoData adapter：解析公共配置，构造指定基础环境，应用公共场景/reset 补丁，生成 TaskDescriptor 和 EmbodimentAdapter 配置，注册匹配 planner，再应用记录器及生成模式。必须显式传入算法、环境 ID 和种子，防止 CLI 与 YAML 各自决定。

Arena adapter：从同一环境工厂及同一补丁得到 source cfg，复用动作/观测和判据，转换为当前版本的 TaskTerminationCfg、ProgressObjective、失败项和 Metric。模型输入预处理、动作转换及 reset 生命周期由 Policy adapter 承担。初期沿用已有外部环境入口，扩展配置参数；不必先迁移到 RoboLab 场景图。

新增刚体时，现有 `_scene_subset` 使用固定名字列表，会漏掉新对象；通用化时应由公共工厂枚举或明确声明场景成员，而不是继续只复制 ground/nightstand/table/cube 等固定项。

## 5. 配置形态示例

随包提供 `shared-config.example.yaml`，仅为待实现的外层 schema 草案，现有 CLI 不能直接运行它。示例首先通过引用已有 Python 环境和原 YAML 落地；字段级参数化在后续版本加入。

预期用户体验（以下命令同样是拟议接口，尚未实现）：

```text
shared-config validate experiment.yaml
shared-config resolve experiment.yaml --mode generate
shared-config run experiment.yaml --mode generate
shared-config run experiment.yaml --mode evaluate
```

resolve 应展示最终环境类、资产/标定哈希、动作缩放、reset 分布、判据阈值、seed、回合预算以及双方差异。运行时保存 `resolved_config.json` 与 lock 信息，并把同一 `task_contract_hash` 写入生成结果 sidecar 和评估报告；生成配置/评估配置另有各自哈希。

相同任务契约不代表相同数据分布。可共用 reset 分布定义，但生成集合和正式评估集合要区分。正式评估使用冻结的初态集合或独立种子；需要严格逐例比较时，保存初始物体/机器人状态和 case_id，按相同 case 重放初态。现有 fixture 是动作回放回归，不能用作独立策略成绩或批量测试集。

## 6. 实施顺序与验收

### 第一阶段：当前 OpenArm 左臂最小闭环

新增外层配置校验器和两侧 launcher，把已有基础环境、三份 YAML 与 Arena 实际 CLI 接起来。统一算法/环境 ID/种子传递，真正消费 evaluation 协议。保留左臂 7D IK，其他组合明确拒绝。配置加载器与设计置于主仓库 workspace-overlays，按既有流程形成补丁或扩展包，不改 upstream submodules。

验收：只改公共配置中的一个 reset 范围，两端 resolve 都能显示相同变化；只改 evaluation 时限不影响生成；未知字段和动作契约冲突启动前失败。

### 第二阶段：消除重复环境和参数

抽取公共环境包，将分散在 Python、YAML、policy_io.json 的重复动作参数和成功阈值纳入工厂；通用化场景成员、对象引用和 profile 应用。冻结资产、标定和版本，构建前统一 RNG，保存有效配置与初态。

验收：两端比较未加运行模式前的 scene/actions/observations/events/success 指纹；证明生成模式的 recorders/terminations 变化仅按显式协议发生。

### 第三阶段：GPU 验证及扩展

在分别配置好的运行容器/GPU 环境执行：

1. 成功判据正负例：垫内静置为真，垫外、悬空、夹爪未开、速度超限为假。
2. 同一初态和匹配控制器下完整动作回放，验证双方任务和动作接口；允许声明的数值误差，不承诺跨版本逐位一致。
3. Arena 超时与掉落失败、并行回合数和分母验证；生成端独立检查失败上限、过滤和导出数量。
4. 相机形状/颜色/坐标、模型预处理和动作反变换验证。
5. 数据标注持久化、转换完成与 HDF5/训练格式回读分别留证；配置解析通过不代表数据已保存。
6. 最后扩展右臂和 KER，逐项验收。现有 Arena 交付仅以左臂 IK 为验证入口，不能推断其他模式兼容。

## 7. 已有证据、限制和交付状态

已有包的 VALIDATION.md 报告了左臂夹具回放、两环境超时、输入输出契约和成功规则正负例。当前工作区另有兼容入口的 summary：smoke 0/2 成功，regression 1/1 成功、1188 平均步数。这些是本地已有运行记录，本次仅阅读；没有复跑，也不能证明拟议公共配置已实现或任何训练策略的泛化成功率。

AutoData 当前 HEAD：`1c7360d85c9ad131ca6c8c70f1f731a6312616f3`。
Arena 当前 HEAD：`98866596fd024d96c874fe6fb95ae916d1133629`。
旧交付 README 的 Arena 基线：`8b82dca224f2b5af08f339f987613c59ce9cdbaa`。
源码包含本地文件/修改，HEAD 不是完整快照；本报告的文件哈希以实际读取内容为准。

本地包已准备并进行 SHA-256 封装校验。未找到机器本地双交付目的地配置；飞书与 ChatGPT 目的地均未指定，尚未上传，也无上传回执。未选择任意 Page 或公开发布。

证据索引和关键输入哈希见 evidence.json；设计示例不等于已交付可运行实现。
