# IsaacLab-Arena 示例运行与使用说明

版本：v001；核对日期：2026-10-12（Asia/Shanghai）。

本说明暂将用户所说的“Arne”理解为本工作区的 IsaacLab-Arena，尚未收到名称确认。依据工作区锁定提交 `98866596fd024d96c874fe6fb95ae916d1133629` 的源码和文档，未修改上游子模块。

## 检查结论与边界

- 工作区子模块只有 Git 元数据，尚未检出源码；本次将锁定提交的源码归档下载到临时目录进行静态检查。
- 主机存在 Docker 29.8.1，但 `nvidia-smi` 报无法连接 NVIDIA 驱动。本次没有安装依赖、构建容器或启动 Isaac Sim，以下命令仍需在配置好的 NVIDIA GPU 机器上验证。
- 最合适的入门顺序：短零动作运行 → 桌面抓放场景交互 → 换物体/背景 → 多配置实验 → 真实策略或演示回放。
- 零动作策略不需要模型权重，也不会自动完成抓放任务。场景能打开只说明启动链路可用，不说明机器人已经学会任务。

## 1. 准备源码与运行环境

下面的初始化命令在 WorldSimReady-Home 根目录执行，使用父仓库记录的提交，不能加 `--remote`：

```bash
git submodule update --init IsaacLab-Arena
cd IsaacLab-Arena
git rev-parse HEAD
# 应为 98866596fd024d96c874fe6fb95ae916d1133629
git submodule update --init --recursive
nvidia-smi
```

后续所有示例路径都相对于 Arena 根目录。需要 Linux、可用的 NVIDIA 驱动/GPU，以及能够获取 NVIDIA Python 包和仿真资产的网络。图形界面示例还需要可用的桌面显示会话。

### 原生 uv 路线

锁定提交的安装文档支持原生 uv：

```bash
uv sync --extra dev
source .venv/bin/activate
```

这会下载较大的 Isaac Sim、PyTorch 等依赖，不是仅安装 Arena 的小型 Python 包。Python 文件指定 3.12，项目要求 `>=3.12,<3.13`。

版本核对发现一处实际差异：README 标注 Isaac Sim 6.0.0，安装文档写 6.0.1，而 `pyproject.toml` 的覆盖项及 `uv.lock` 实际锁定 `isaacsim==6.1.0.0`。因此应使用该提交自己的配置和锁文件，不要手工按网页文字混装版本。本次未验证这一组合的运行兼容性。

阅读并接受 Isaac Sim 许可后，在运行终端设置：

```bash
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y
```

### Docker 路线

需要 Docker 和 NVIDIA Container Toolkit。上游 AGENTS.md 要求代理执行仿真、评估等运行命令时使用当前克隆的容器；本次只进行静态检查。

在宿主机的 Arena 根目录执行：

```bash
./docker/run_docker.sh
```

启动脚本会按需构建镜像并进入容器。进入容器后在 `/workspaces/isaaclab_arena` 执行后面的 Python 命令。容器交互 shell 中 `python` 指向 Isaac Sim 的解释器；外部 `docker exec` 应明确使用 `/isaac-sim/python.sh`，并动态确认本克隆对应的容器名。

普通示例不需要 cuRobo；需要 `ik_reachable` 放置校验时才使用 `./docker/run_docker.sh -c`。原生 uv 不包含该可选 cuRobo 包。

## 2. 最小启动检查：20 步零动作

在已准备好的运行环境中执行：

```bash
python isaaclab_arena/evaluation/policy_runner.py \
  --policy_type zero_action --num_steps 20 cube_goal_pose
```

预期是完成 20 步并正常退出。该命令没有请求 Kit 图形界面；若要观察场景：

```bash
python isaaclab_arena/evaluation/policy_runner.py \
  --viz kit --policy_type zero_action --num_steps 200 cube_goal_pose
```

`cube_goal_pose` 是环境名，`zero_action` 是策略名，`--num_steps` 是仿真步数。不要同时给 `--num_steps` 和 `--num_episodes`，源码要求两者只选一个。

## 3. 查看和交互桌面抓放场景

```bash
python isaaclab_arena/scripts/environment_runner.py \
  pick_and_place_maple_table \
  --embodiment droid_rel_joint_pos \
  --pick_up_object rubiks_cube_hot3d_robolab \
  --destination_location bowl_ycb_robolab \
  --hdr home_office_robolab
```

场景由 DROID 机器人、枫木桌、魔方、碗及家庭办公室背景组成，任务目标是把魔方放进碗里。

- 按住 **Shift + 鼠标左键拖动物体**，检查摆放和物理交互。
- 关闭 Kit 窗口或按 `Ctrl-C` 退出。
- 此入口持续发送零动作，并关闭录制器，不会保存演示数据。
- 源码默认采用 CPU PhysX、Kit 界面、单环境。这里的 CPU 指物理计算设备，Isaac Sim 渲染仍需合适的 GPU。此交互入口不支持并行环境、分布式运行或 Newton 鼠标交互。

### 如何更换组件

| 参数 | 意义 | 可替换的示例值 |
|---|---|---|
| `--embodiment` | 机器人及控制方式 | 保留 `droid_rel_joint_pos` 先验证其他变化 |
| `--pick_up_object` | 被抓取的物体 | `mustard_bottle_hot3d_robolab` |
| `--destination_location` | 目标容器 | `wooden_bowl_hot3d_robolab` |
| `--hdr` | 全景背景与环境光 | `billiard_hall_robolab` |

参数值需要对应注册的资产/机器人，不能随意填写物体名称。更换机器人还需确认动作空间、控制器和策略兼容。

## 4. 一次运行多个配置

官方入门实验包含四个顺序运行的配置：基线、换物体、换背景、64 个并行环境。为了首次运行负担更小，可先将最后一项改为 8 个环境：

```bash
python isaaclab_arena/evaluation/experiment_runner.py \
  --viz kit \
  --experiment_config isaaclab_arena_environments/experiment_configs/getting_started_experiment.yaml \
  runs.parallel_envs.environment_builder.num_envs=8
```

此处四个 Run 按顺序执行；8 个环境是在最后一个 Run 内并行步进。实验仍使用零动作策略；每回合默认 1.5 秒仿真时间，每个 Run 的回合上限为 1，不代表任务成功。

结果默认保存在 `outputs/YYYY-MM-DD_HH-MM-SS/arena_experiment_result.json`，终端会打印实际位置。检查每个 Run 的状态和回合指标；如要增加共享回合上限，可追加 `shared.rollout_limit.num_episodes=4`。Run 内的显式设置优先于 shared 设置。

## 5. 如何继续用于自己的工作

Arena 把环境拆为 Scene（场景）、Embodiment（机器人及动作/观测）、Task（目标及成功条件）。修改物体/背景适合复用现有 CLI；建立新任务时，在自己的扩展包或 workspace overlay 中组合这三部分，保持上游子模块不变。

根据目的选择入口：

| 目的 | 入口 |
|---|---|
| 看场景、检查摆放、鼠标交互 | `isaaclab_arena/scripts/environment_runner.py` |
| 用一个策略运行环境 | `isaaclab_arena/evaluation/policy_runner.py` |
| 比较多套配置并保存实验结果 | `isaaclab_arena/evaluation/experiment_runner.py` |
| 回放已录制演示 | `submodules/IsaacLab/scripts/tools/replay_demos.py` |
| 采集演示 | `submodules/IsaacLab/scripts/tools/record_demos.py`，另行配置遥操作设备 |

真实策略需要匹配的模型权重、动作/观测配置，部分策略还需独立推理服务。GR1 开微波炉演示回放需要下载指定 HDF5 数据集；它与零动作场景查看是不同工作流。建议先通过前三步，再按目标选择真实策略、模仿学习或强化学习说明。

## 6. 常见问题与验收

- NVIDIA 驱动不可用：先在 GPU 服务器确认 `nvidia-smi` 正常，再尝试启动仿真；`--device cpu` 不能替代渲染 GPU。
- 脚本路径不存在：子模块未检出，或当前目录不是 Arena 根目录。
- 导入失败：确认已经激活 uv 环境，或处于 Arena 容器内。
- Kit 界面打不开：检查显示会话；无显示服务器先使用不加 `--viz kit` 的短零动作命令。
- 资产加载失败：核对资产服务的网络访问和完整错误日志。
- 机器人不动：这两个入门示例发送零动作，本身不会自主完成抓放。
- 交互入口提示只支持一个环境：切换到 policy_runner 或 experiment_runner 做并行运行。

建议保留首次启动的完整日志、GPU/驱动信息、提交号和退出码。验证分三个层次：20 步正常结束；Kit 中场景正确且可拖动物体；实验 JSON 能读到每个 Run 状态。本次三项均未做运行验证。

## 证据来源

以下链接均固定到工作区锁定提交，避免 main 后续变化影响命令：

- [安装文档](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/docs/pages/quickstart/installation.rst)
- [首个环境](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/docs/pages/quickstart/arena_env.rst)
- [首个实验](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/docs/pages/quickstart/arena_experiment.rst)
- [交互入口源码](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/isaaclab_arena/scripts/environment_runner.py)
- [策略运行源码](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/isaaclab_arena/evaluation/policy_runner.py)
- [实际依赖配置](https://github.com/isaac-sim/IsaacLab-Arena/blob/98866596fd024d96c874fe6fb95ae916d1133629/pyproject.toml) 与同提交 `uv.lock`

交付状态：本地包已准备；未配置飞书和 ChatGPT 的指定目标，且当前未取得相应文件上传能力。此本地链接不表示已上传到 ChatGPT。
