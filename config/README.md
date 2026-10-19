# AutoData / Arena 共享配置

> 2026-10-14 状态：下文 GPU 结果是历史验证。当前锁定 AutoData 提交不包含所需 OpenArm 本地源文件，当前工作树缺少 `left_env_cfg.py`；resolve/run 会提前失败。恢复要求见 [版本管理约定](../docs/version-management.md)。主机配置校验可独立执行。

唯一入口是 `openarm/experiment.json`。两端都从当前 AutoData 工作树的 `openarm_autodata` 构造同一环境，不再加载 Arena 旧交付包中复制的环境或资产。所有新增实现由本根仓库管理，Arena 源码及子模块提交均不需要修改。

```text
config/openarm/experiment.json
  common ────── shared_config.runtime.make_env_cfg
                    ├── AutoData Gym 注册入口（仅当前进程）
                    └── Arena 外部环境 + Task / Metric 适配器
  generation ── task / embodiment / env_profile → AutoData 原生文件和参数
  evaluation ── policy / seed / budget → Arena 原生参数
```

## 配置归属

| 配置 | 唯一维护位置 | 消费方式 |
| --- | --- | --- |
| 动作平移/旋转缩放、夹爪负值闭合约定 | `experiment.json:common.action` | 环境工厂与生成 embodiment 同时消费；不支持的夹爪约定报错 |
| 方块 reset 的 x/y 偏移范围（米） | `common.reset_pose_range` | 同一工厂写入两端 reset 事件 |
| 放置成功阈值（米、弧度、米/秒、弧度/秒） | `common.success` | 同一工厂写入成功函数参数 |
| 生成环境/算法随机种子 | `common.seed` | 工厂及派生 task descriptor 同时使用 |
| 机器人、USD、相机、MDP 实现、物理默认值 | AutoData 的 `openarm_autodata` | 单一源码来源；每次 resolve 记录实际文件哈希 |
| SkillGen 分段/筛选/成功样本目标数 | `task.json` | 生成端读取；默认目标 10 条成功轨迹、失败上限 25 |
| 生成器动作布局与 TCP 观测映射 | `embodiment.json` | 缩放由 common 派生，禁止重复定义 |
| 环境 ID 和规划器 | `env_profile.json` | ID 必须匹配 common；暂不允许 scene/event 补丁绕过公共工厂 |
| 策略、评估种子、完成回合数、时限 | `experiment.json:evaluation` | 评估端读取；默认 zero_action 仅用于入口检查，无训练模型 |

JSON 可被 AutoData 的 YAML 读取器解析；主机上的校验和解析只需 Python 标准库，无需安装仿真或 YAML 依赖。根目录四份配置组成一套配置，而非两端各维护一份。修改动作缩放或成功阈值会改变任务语义，需要同步模型训练约定。

## 使用

在工作区根目录执行纯主机检查：

```bash
python3 scripts/shared-config.py validate config/openarm/experiment.json
python3 scripts/shared-config.py resolve config/openarm/experiment.json --mode evaluate --run-dir /tmp/openarm-evaluate-plan
python3 scripts/shared-config.py resolve config/openarm/experiment.json --mode generate --input /data/annotated.hdf5 --output /data/generated.hdf5 --run-dir /tmp/openarm-generate-plan
python3 -m unittest discover -s workspace-overlays/shared_config/tests -v
```

`resolve` 只写入新目录，展示命令，不启动仿真。相对配置引用以 experiment 文件所在目录为基准；命令行输入、输出、run-dir 以调用目录为基准。`--run-dir` 必须是新目录，避免覆盖运行证据。解析结果、三份派生原生配置、实际源码/资产哈希、两仓库 HEAD 和完整 argv 都保存在该目录。运行时检查源码未发生漂移，并检查实际加载路径，防止加载到旧交付中的同名包。

运行仿真时，在用户已手动启动并配置好的相应 GPU 容器内执行下面命令。须将整个 WorldSimReady-Home 工作区挂载进容器，保留两个上游与外置扩展的相对路径；仅挂载 Arena 目录不足以运行共享环境。选择该容器已有的解释器，不新建或修改 conda 环境。

```bash
python3 scripts/shared-config.py run config/openarm/experiment.json --mode evaluate --python /isaac-sim/python.sh --run-dir runs/openarm-evaluate-001
python3 scripts/shared-config.py run config/openarm/experiment.json --mode generate --python /isaac-sim/python.sh --input /data/annotated.hdf5 --output /data/generated.hdf5 --run-dir runs/openarm-generate-001
```

`--python` 可换为相应容器的已配置解释器，`--device` 默认 `cuda:0`。启动器不自动接受 EULA、不创建容器、不安装依赖。输入示教必须已完成有效标注；配置解析不验证 HDF5 内容。生成会拒绝不存在的输入和已存在的输出。

使用符合 OpenArm 观测契约的 TorchScript 模型时，可将 evaluation.policy_type 改为 `shared_config.policy.OpenArmTorchScriptPolicy`，并在 policy_args 中提供 checkpoint。检查点路径由运行机器配置；个人配置副本可以放入已忽略的 `config/.local/`，同时复制其相对引用的三份文件。policy_args 当前支持字符串和数值，布尔/列表参数显式拒绝；公共参数不可通过 policy_args 覆盖。

## Arena 清理与历史证据

2026-10-13 整理时，顶层 Arena 没有已跟踪源码改动，只有未跟踪的 `deliveries/`。完整旧包（含配置、复制的环境/资产、验证日志与 fixture）现位于 `workspace-overlays/arena-deliveries/`；当时没有使用 reset/clean，也没有更改 HEAD。2026-10-14 检查已发现两侧 AGENTS 与嵌套依赖的本地变更，详见过程记录。

历史包保持原样，仅供追溯；其脚本包含旧目录假设，不作为新运行入口。归档体积约 93 MB，已从 Git 排除，保留在本机；新配置、适配器和说明由根仓库管理。不要将归档复制环境加入 PYTHONPATH。2026-10-14 两侧顶层 HEAD 均匹配根仓库锁定提交，本地工作树变更保留。

## 边界与后续扩展

当前实现针对左臂 7D 相对 IK、现有桌面/方块任务。生成端在公共工厂之后按原逻辑添加 recorder、移除终止项并提取成功判据；评估端保留成功、掉落和超时并使用 Arena Metric。不同模式 seed 和时限可以不同，配置共用不保证两个框架逐位相同的轨迹。

Arena 版本兼容只存在外置 `shared_config.arena` 中，处理 TaskTerminationCfg、PhysX 和夹爪索引差异。场景成员仍显式限定为当前任务的固定成员，暂不接受新增对象；下一步如需多任务，可将公共环境工厂提取成独立版本包，并为各锁定 Arena 版本提供适配器。当前不需要改变上游结构来完成该扩展。

初版主机测试覆盖配置传播、派生配置冲突、参数隔离、非法输入和命令生成。本次实际 GPU 检查见下节；仍未执行完整轨迹回放、学习策略训练或数据回读。旧交付的运行结果不能作为新架构运行成功的证据。


## 2026-10-13 实际 GPU 验证

经用户明确授权，本次复用已有 AutoData conda 和 Arena `.venv`，没有使用嵌套 Docker、安装依赖或修改上游。两端环境加载、6 步动作执行和 6 个成功判据正反例均通过；共享源码、动作处理、观测形状、reset 和判据参数比较全部一致。Arena 完整 launcher 的短回合也已跑通。记录见 `outputs/autodata-arena-shared-config/v003/report.md`。

本次新增独立运行检查及比较入口；每侧在自己的 Python 环境中执行，输出目录必须不存在。解释器路径和 CUDA 库路径由运行机器配置，不写入公共配置：

```bash
# AUTODATA_PYTHON / ARENA_PYTHON 指向机器上已有、已配置好的解释器。
# AUTODATA_CUDA_LIB 指向该 AutoData 环境已有的 nvidia/cu13/lib 目录。
# 容器按各仓库要求启动；如例外使用原生环境，须有用户明确授权。
LD_LIBRARY_PATH="${AUTODATA_CUDA_LIB}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
  "$AUTODATA_PYTHON" scripts/validate-shared-runtime.py --backend autodata --run-dir runs/check-autodata
"$ARENA_PYTHON" scripts/validate-shared-runtime.py --backend arena --run-dir runs/check-arena
python3 scripts/compare-shared-runtime.py runs/check-autodata/runtime_result.json runs/check-arena/runtime_result.json --output runs/comparison.json
```

启动前遵循运行环境已有的 Isaac Sim EULA 接受设置。AutoData 首次运行暴露了已有 CUDA 13 NVRTC 库搜索路径缺失；只补充该进程的 LD_LIBRARY_PATH 后通过，未安装任何库。原 launcher 缺少 Arena 环境子命令的问题已修正，环境专用参数现在位于 `openarm_left_pick_place` 后，公共参数在其前。

验证脚本使用真正的 AutoData setup_env_config 和 ArenaEnvBuilder。成功判据用直接写入物理对象状态的六个正反例检查；不依赖正在产生的随机轨迹是否偶然完成任务。比较不通过会返回非零状态。须同时检查 runtime_result.json 的 status：本次一次 Isaac Sim 初始化异常后的进程退出码为 0，退出码本身不足以判定成功。

本次没有验证完整轨迹的数值等价、学习策略性能、完整 SkillGen 数据生成或 HDF5 标注/导出。两侧 Isaac Sim / Isaac Lab / Torch 版本不同，即使接口和判据测试通过，也不能推断逐位相同的物理轨迹。
