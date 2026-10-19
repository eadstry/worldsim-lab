# cuRobo v1 → v2 升级评估

版本：v001；材料截止：2026-10-14 15:05（Asia/Shanghai）。交付范围：用户指定仅本地。

## 结论

**当前 AutoData 后端、本机 autodata 环境已安装的 cuRobo、OpenArm 专用运行补丁都属于 v1 API。建议继续保留 v1 基线，开展独立的 v2 后端试验；目前证据不支持直接替换现有生成环境。**

升级属于“总体影响中等、planner 子系统影响较大、OpenArm 集成风险偏高”的迁移。数据生成核心已有接口隔离，无需为基础升级重写全项目；但碰撞、物体附着、机器人关节映射、执行重采样及监控都不能靠替换 import 自动完成。

本次做了源码、安装元数据和既有运行入口的静态检查，以及官方最新文档核对。没有安装依赖、改动上游、重跑 GPU 生成或验证 v2 性能。当前隔离环境的 `nvidia-smi` 无法连接驱动。

## 1. 当前版本如何确认

当前工作树的三个顶层子模块未初始化。检查使用的是同机已有的 AutoData 源码副本，其 HEAD 与 `upstream-lock.json` 相同：`1c7360d85c9ad131ca6c8c70f1f731a6312616f3`。下表涉及的 AutoData 代码在该副本中没有相对 HEAD 的修改；OpenArm 工作区 overlay 作为额外本地证据单独记录。

| 层级 | 静态证据 | 能得出的结论 |
| --- | --- | --- |
| AutoData 后端 | `autodata_interfaces/motion_planners/__init__.py:6` 标注只提供 v1；`curobo/curobo_planner.py:23` 导入 `MotionGen/MotionGenConfig/MotionGenPlanConfig` | 当前集成面是 v1 |
| Docker 安装约定 | `docker/setup/install_curobo.sh:7` 固定 cuRobo 提交 `ebb71702f3f70e767f40fd8e050674af0288abe8` | 可复现安装目标是该 SHA；不能据此声称本机安装包必定来自该 SHA |
| 本机 autodata 环境 | 安装元数据为 `nvidia_curobo 0.0.post1.dev1`；实际包有 `curobo/wrap/reacher/motion_gen.py` 的 `MotionGen` 类 | 已安装包是 v1 API；该开发版本号不等于正式“v0.0”，也不能精确归类为 v0.7.8 |
| 安装来源 | `direct_url.json` 指向曾使用的本地源码目录，该目录目前不存在 | 无法从现有安装记录恢复确切 cuRobo Git SHA；这是溯源缺口 |
| OpenArm 入口 | `workspace-overlays/openarm-production/generate.py:132` 指定 `--alg skillgen`；`compat.py:100` 加载 `runtime/patches/curobo_planner.py` | 当前 OpenArm 入口确实使用规划器，且加载专用补丁副本 |
| OpenArm 实际加载的补丁 | `runtime/patches/curobo_planner.py:23` 仍导入旧 `MotionGen` | 本地补丁没有迁到 v2 |

“当前使用”在这里指源码、已安装依赖和运行入口的对应关系；没有读取活跃进程的 Python 模块表，不能证明某个此刻正在运行的进程加载了哪份文件。MimicGen / DexMimicGen 路径本身不要求 cuRobo；升级收益主要作用于 SkillGen。

官方版本命名也需区分：研究/架构上的 **cuRoboV2 从包版本 v0.8.0 引入**，不是必须寻找 `2.0.0` 包。官方 README 建议依赖 v1 API 的项目固定 `v0.7.8`；本项目现有提交与安装来源仍应分别核对，不能直接套用该标签。[官方更新记录](https://raw.githubusercontent.com/NVlabs/curobo/main/CHANGELOG.md)、[官方 README](https://raw.githubusercontent.com/NVlabs/curobo/main/README.md)

## 2. 升级好处，以及当前能否用上

| v2 能力 | 当前项目的潜在收益 | 生效前提与限制 |
| --- | --- | --- |
| B-spline 轨迹优化、可微逆动力学和力矩约束 | 更适合高速、带载和物理可执行性要求高的轨迹 | 需可靠惯性/负载/力矩限制，并验证实际控制执行；当前只回传末端位姿，不能自动保留关节轨迹的动力学保证 |
| 高自由度机器人运动学与自碰撞扩展 | 为双臂联合规划、移动操作或全身规划准备能力 | 当前 SkillGen 明确限制单臂。只升级库不会获得双臂协调，需要额外修改算法及执行接口 |
| 新的批量及多环境规划接口 | 有机会降低当前“每个环境独立建 planner”的重复开销，提升多环境生成吞吐 | 必须接入批量调度；当前逐环境调用方式原样迁移不会自动得到全部批量收益；v1 本身也已有批量 API |
| GPU 原生深度 TSDF/ESDF 建图 | 更适合真实深度传感器、未知几何和感知驱动规划 | 当前世界来自 USD 已知几何和物体位姿，短期无需为此接入建图 |
| 新的组合式架构和统一 tool-frame 目标 | 后续扩展新机器人、多个工具坐标系更方便 | 需要重新适配配置与位姿形状，维护收益伴随一次迁移成本 |

前三类算法能力来自[官方技术说明](https://nvlabs.github.io/curobo/latest/technical_reports.html)，新规划接口与目标结构见[官方规划教程](https://nvlabs.github.io/curobo/latest/getting-started/motion_planning.html)和[配置源码](https://raw.githubusercontent.com/NVlabs/curobo/main/curobo/_src/motion/motion_planner_cfg.py)。上表的项目收益判断是基于本地调用链的工程推断，不是本项目实测。

官方 changelog 的“批量规划 GPU 内存减少 3 倍”是 v2 后续内部改进，包含 seed 默认值和插值 buffer 调整，不是本项目从 v1 迁移后必然节省 3 倍。建图加速也不能换算为数据生成端到端加速。[官方 changelog](https://raw.githubusercontent.com/NVlabs/curobo/main/CHANGELOG.md)

## 3. 改动影响具体落在哪里

| 模块 | 现状及迁移动作 | 影响 |
| --- | --- | --- |
| 规划初始化、求解与返回值 | `MotionGenConfig.load_from_robot_config` / `plan_single` 迁到 `MotionPlannerCfg.create` / `plan_pose`；构建 `GoalToolPose`；处理 batch 维度、失败返回 `None` 和新的轨迹类型 | 大 |
| 机器人配置、FK、锁定关节 | 旧 `TensorDeviceType`、`CudaRobotModelState.ee_pose`、关节排序和 `update_locked_joints` 都要逐项映射；确认 tool frame 与原 EE link 一致 | 大 |
| 世界几何与碰撞 | 旧 `WorldConfig`、`UsdHelper`、`world_coll_checker`、按名字更新障碍物的代码需要转换到新 scene 接口 | 大 |
| 抓取、放置和附着物体 | 当前直接启停 hand/attached link 碰撞球，并在规划后恢复；v2 使用新的 attachment manager / link collision 机制，需重做等价语义和失败恢复 | 大，必须 GPU 回归 |
| 配置预设 | planner 配置文件约 494 行，需核对每个参数的单位、默认值和可用性；不能盲目保留旧 kwargs | 中 |
| 轨迹执行 | `get_planned_poses()` 对关节轨迹做 FK，再交给 SkillGen 的末端位姿 waypoint；必须重新验证采样间隔、retiming、终点重复和实际 tracking | 中到大 |
| Rerun 可视化 | `plan_visualizer.py` 约 907 行，直接依赖旧 `JointState`、kinematics 和碰撞球访问 | 中；可晚于最小后端试验完成 |
| 生成入口 | `scripts/generate_dataset.py:231` 每个 env 建一个 planner；增加明确 v1/v2 选择并保留旧默认值 | 小；若改共享批量调度则大 |
| 核心生成器、源示范、HDF5 输出 | 维持 `update_world_and_plan_motion()` / `get_planned_poses()` 契约时可复用 | 小；导出代码不需因 API 升级而重写，但生成的轨迹内容会变 |
| OpenArm 本地补丁 | `prepare.py:67` 从 v1 源文件做精确字符串替换；涉及关节排序、推理模式下启用梯度、锁定另一只手、夹爪判定和接近方向 | 大；换 v2 后这些替换锚点会失效，应改成后端显式能力 |
| OpenArm 监控与比较脚本 | `telemetry.py:304` 直接导入 `MotionGen`，包装 `_plan_from_solve_state*`；需重新定义 v2 外层 attempt 统计与调用计时 | 中；否则监控失败或历史指标不可比 |
| 环境与安装 | 更新版本锁定和构建方案，核对 CUDA/PyTorch/Warp 与 Isaac Sim 共存 | 中到大，取决于独立环境验证 |

当前核心 planner 文件约 2,019 行，加配置与可视化共 3,420 行。这是需要审阅的代码面，**不是预计全部重写的行数**。还需覆盖两个包导出、生成入口、现有配置测试，以及本机 OpenArm overlay。overlay 未包含在当前工作树中，但在同机主工作区存在；相关输入哈希保存在 `evidence.json`。

关键 v2 API 可在[公开类型导出](https://raw.githubusercontent.com/NVlabs/curobo/main/curobo/types.py)、[MotionPlanner 入口](https://raw.githubusercontent.com/NVlabs/curobo/main/curobo/motion_planner.py)和[规划实现](https://raw.githubusercontent.com/NVlabs/curobo/main/curobo/_src/motion/motion_planner.py)复核。应依赖公开模块，避免把新的 `_src` 内部路径直接扩散到业务代码。

## 4. 三个最容易低估的风险

**规划轨迹不等于实际执行轨迹。** `algorithms.py:272` 只把 planner 输出的末端位姿包装为 `Waypoint`。关节分支、速度、加速度、力矩和时间信息没有作为完整轨迹传下去；IK 控制器可能选择不同关节路径。仅换 v2 可以比较 transit 的几何质量，但不能据此保证实际执行满足 v2 规划时的力矩限制。若目标是动力学保证，需要扩大到执行接口与控制器，而不只是 planner 后端。

**批量吞吐与困难场景成功率必须一起测。** 当前每环境一个 planner。v2 `multi_env` 模式在官方配置说明中明确跳过图搜索 seeding；不能假设合并到批量 planner 后与原路径等价。障碍密集、窄通道场景尤其需要独立比较。[v2 配置说明](https://raw.githubusercontent.com/NVlabs/curobo/main/curobo/_src/motion/motion_planner_cfg.py)

**安装兼容不能只看 Python 版本。** 本机静态安装元数据为 Python 3.12 环境、Isaac Sim 6.0.1.0、PyTorch 2.11.0、Warp 1.13.0。它们在版本号上看不出必须全面重装的理由，但不能证明 CUDA 图、二进制与驱动兼容。官方当前安装文档要求 Linux、相应 NVIDIA GPU/显存、驱动至少 580.65.06，并提供 CUDA 12/13 安装选项；当前驱动无法读取，兼容性仍待确认。v2 changelog 还记录 Warp 1.13 API 适配，选择 v2 提交时应包含需要的修复。[安装要求](https://nvlabs.github.io/curobo/latest/getting-started/installation.html)、[依赖声明](https://raw.githubusercontent.com/NVlabs/curobo/main/pyproject.toml)、[变更记录](https://raw.githubusercontent.com/NVlabs/curobo/main/CHANGELOG.md)

## 5. 是否有必要，现在怎么决策

- **目标是尽快稳定产出当前 OpenArm 单臂数据：暂不切默认环境。** 当前没证据证明主要瓶颈由 v1 规划库造成；应先取得规划、执行和导出分阶段基线。导出慢或控制跟踪失败不一定能通过 v2 解决。
- **目标是扩大环境数、降低 planner 显存、改善 transit：值得做 v2 试验。** 先保留逐环境架构做等价迁移，确认正确性后再单独评估批量化，才能区分库升级与调度改造的影响。
- **目标是力矩约束、深度建图或双臂全身规划：升级价值高。** 同时把模型、执行或算法改造计入范围，不能按纯依赖升级排期。

工程量估计（单名熟悉项目的工程师，有可用 GPU；这是计划区间，不是已完成工作或工期承诺）：

| 交付层次 | 估计投入 | 包含范围 |
| --- | --- | --- |
| 最小可行性验证 | 2–4 人日 | 独立环境、固定 v2 SHA、模型加载、单环境障碍规划、FK/位姿转换与一次 transit |
| 可替代当前 OpenArm 单臂生成路径 | 累计约 8–15 人日 | 碰撞/附着/接触、关节与夹爪补丁、监控迁移、生成回归、安装锁定；暂保留逐环境 planner |
| 共享多环境批量调度与性能优化 | 在等价迁移上增加约 5–10 人日 | 请求聚合、不同世界与附着状态隔离、CUDA 图容量、graph fallback 策略、吞吐测试 |
| 动力学执行、双臂联合或深度感知 | 需另立范围 | 当前源码检查不足以给出可信工期 |

如果模型配置或底层运行环境出现兼容阻碍，以上区间需重估。最小试验跑通不等于已完成迁移。

## 6. 建议实施和验收路径

1. 保存可回滚 v1 基线：补齐已安装 cuRobo 的来源 SHA 或可验证源码快照；锁定 OpenArm overlay 和机器人配置。官方 v0.7.8 可作为另一候选基线，但不在当前环境中直接替换现有安装。
2. 新增独立 v2 后端，优先保持 `MotionPlannerBase` 的现有输出契约和每环境调用方式。通过工作区 overlay/补丁提供改动；本次不改上游子模块或既有 autodata 环境。
3. 在单独配置的 GPU 环境验证 v2，固定明确提交；当前官方 `main/latest` 持续变化，不应作为生产安装目标。先测单环境，再测 4/8/16 环境。
4. 用同一组源示范、物体初始分布、机器人模型和显式参数做 A/B。分别报告 seed 数、重试预算、碰撞余量、采样间隔；默认值不同的比较单列，不能都归因于库实现。
5. 比较规划成功率、实际任务成功率、碰撞/穿透、末端误差、p50/p95 规划耗时、首次预热和峰值显存，以及“每小时成功保存的示范数”。失败规划、附着状态恢复和 HDF5 读回都要检查。
6. 为夹爪开闭、带物绕障、接触放置、另一只臂锁定、非原点环境、不同关节顺序及多环境隔离建立 GPU 回归。动力学价值另测实际关节执行与力矩，不用位姿可视化代替。
7. **建议切换门槛**：先满足正确性与成功率不退化，再争取有实际价值的收益，例如成功样本吞吐提高 ≥20% 或 planner 显存降低 ≥25%。这些是建议的决策阈值，不是 v2 官方承诺；样本量与统计区间需随基线成功率和希望检出的变化确定。

## 7. 证据边界与本地交付

- 本次没有执行 v1/v2 GPU A/B，也没有验证 v2 与本机 Isaac Sim 的运行兼容。
- 已有 `local-runtime-validation.json` 仅作为历史记录识别配置；没有把其中的通过状态当作本次复验。
- 官方远端材料来自检查时的 `main/latest`，没有取得统一不可变 v2 SHA；不同页面不能保证处于同一个提交。实施前必须固定版本并重新核对。
- 输入文件 SHA-256 与关键行号摘要见 `evidence.json`；交付文件哈希见 `manifest.json`。证据使用逻辑路径，机器绝对路径不进入共享包。
- 按用户最新指令，仅准备本地报告；飞书与 ChatGPT 外部上传未执行。
