# OpenArm 无训练策略 benchmark 示例

复用现有 OpenArm 左臂抓放配置和资产，通过 Arena 执行零动作检查与固定轨迹回归。
无需训练检查点。零动作失败用于检查负例计分；固定轨迹成功用于检查抓放链路。
这两项结果不能解释为模型泛化成绩。

## 示例内容

| 检查 | 初始状态 | 控制来源 | 回合数和预算 | 预期行为 |
| --- | --- | --- | --- | --- |
| `smoke` | 源配置随机 reset | Arena `zero_action` | 2 环境，至少 2 回合，每回合 0.5 秒 | 全部任务失败，评测检查通过 |
| `regression` | 原交付夹具固定初态 | 夹具记录的 7 维动作 | 1 环境，1 回合，90 秒 | 抓放成功，评测检查通过 |
| `baseline` | 源配置随机 reset | Arena `zero_action` | 4 环境，种子 11/22/33 各至少 8 回合，每回合 90 秒 | 全部任务失败；可选完整预算基线 |

默认 `--case all` 只运行前两项。`baseline` 需单独选择，避免在简单链路检查中消耗完整预算。
所有秒数为模拟时间。示例没有随机动作、训练策略或假造的模型成绩。

## 复用的 OpenArm 定义

运行输入为原交付包 `openarm_pick_place_arena_20261013_120511`，须保留其完整目录，
包括 `openarm_autodata/`、`openarm_arena/`、资产、`fixtures/replay_left.npz` 和 `MANIFEST.json`。
本仓库不重复提交机器人资产或数据集；另一个机器需要单独获得这个交付包。

场景、左臂动作、观测、相机标定、reset、物理配置和成功判据均来自交付包。
位姿动作为 `[dx,dy,dz,rx,ry,rz,gripper]`，平移乘 0.02 m、旋转乘 0.10 rad，
按实际继承的 `BinaryJointPositionAction.process_actions`，负夹爪动作闭合，零或正动作张开；
原交付说明中的符号描述与实现相反，本例遵循实现，不对夹具动作翻转符号。
控制频率 30 Hz，物理频率 120 Hz。

成功要求方块完整投影位于扫描鼠标垫内、底面高度误差不超过 8 mm、
左夹爪张开至少 0.30 rad、线速度不超过 0.03 m/s、角速度不超过 0.5 rad/s。
方块掉落或超时均会结束回合。没有增加必须先完成抓取的历史条件或连续静置两秒的要求。

AutoData 生成 YAML 中的选源、技能边界、cuRobo 和成功演示数量不参与此评测。
本例使用 Arena `policy_runner` 的外部环境接口，执行配置是实际被读取的 `benchmark.json`，
不把 AutoData YAML 或旧交付的参考 `configs/evaluation.json` 冒充为 Arena Experiment YAML。

## 已有运行环境中执行

先进入已经配置好 GPU、Isaac Sim 和对应 Isaac Lab 的 native 环境或容器。
不要为这个示例更新上游子模块或安装依赖。所有路径必须在所选运行环境中可见。
在仓库根目录设置机器本地变量；下面路径需替换为实际位置：

```bash
export OPENARM_BUNDLE_ROOT="/path/to/openarm_pick_place_arena_20261013_120511"
export ARENA_ROOT="/path/to/IsaacLab-Arena"
export ARENA_PYTHON="/path/to/configured/python"
```

Docker 中 `ARENA_PYTHON` 可以是 `/isaac-sim/python.sh`；native 环境中使用已配置的仿真 Python。
主机 `python3` 只负责检查和编排，仿真子进程始终使用显式指定的 `ARENA_PYTHON`。
已有 Isaac Sim EULA 授权应按所选运行环境的正常方式处理，示例不替用户接受协议。

先检查交付包哈希和 Arena 源码接口，并查看两条实际启动命令：

```bash
python3 workspace-overlays/openarm-benchmark/run.py \
  --bundle "$OPENARM_BUNDLE_ROOT" \
  --arena-root "$ARENA_ROOT" \
  --runtime-python "$ARENA_PYTHON" \
  --output-dir workspace-overlays/openarm-benchmark/runs/demo-001 \
  --dry-run
```

`--dry-run` 不启动仿真，不创建输出目录，也不证明 GPU 环境可用。
去掉 `--dry-run` 即运行默认两项检查。用 `--case smoke`、`--case regression` 单独检查，
用 `--case baseline` 运行可选随机初态基线。每次实际运行都必须选择不存在的输出目录。
需要调整预算或种子时，复制 `benchmark.json` 到机器本地文件，通过 `--protocol` 指定；
运行结果记录有效配置的 SHA-256。固定初态只允许用于 regression。

录制实际 Arena rollout 的完整视口视频：

```bash
python3 workspace-overlays/openarm-benchmark/run.py \
  --bundle "$OPENARM_BUNDLE_ROOT" \
  --arena-root "$ARENA_ROOT" \
  --runtime-python "$ARENA_PYTHON" \
  --output-dir workspace-overlays/openarm-benchmark/runs/video-001 \
  --record-viewport-video
```

当前版本在 `--viz none` 下录制时自动启用无窗口 Kit 渲染；`--viz kit` 使用 Kit 可视化后端。
当前 Isaac Lab 的 `render(rgb_array)` 返回空值，所以进程内适配将 Arena 的录像选项接到
Isaac Lab `VideoRecorderCfg`。这是本次评测的实时录像，不是历史 AutoData 演示或示意动画。
视口显示 env 0；并行环境的判定仍分别记录，不声称每个环境都有独立视频。

## 版本和兼容转换

`input-lock.json` 记录交付包清单哈希，以及两个 Arena 版本的关键源码文件哈希：

| Arena 提交 | 任务结束接口 | 验证范围 |
| --- | --- | --- |
| `8b82dca224f2b5af08f339f987613c59ce9cdbaa` | 原 Isaac Lab termination 配置 | 原交付包保存了 GPU 回归记录；本次新运行器尚未 GPU 复验 |
| `98866596fd024d96c874fe6fb95ae916d1133629` | `TaskTerminationCfg` | RTX 5090 实测：零动作 0/2，固定轨迹 1/1 成功；两项均有原生报告和实测视频 |

原交付的 Isaac Lab 基线为 `ffff603eafc6b74264a5261cc0183d6a65390d78`。
本次 GPU 运行的 Isaac Lab 为 `bb0c8e1b9af381bf13064ec3303e17db79e4b6ef`。
Arena 源码匹配不代表已安装的 Isaac Lab、Isaac Sim 或驱动匹配。
未知或已修改的关键 Arena API 文件会被拒绝，需要人工审查兼容性后更新版本记录。

`openarm_benchmark/environment.py` 继承原交付环境，在当前 Arena 上将原成功项包装为
一个 `ProgressObjective`，保留掉落失败项，并显式声明回合预算。旧版本直接返回原结束项。
转换不会改写交付包、生产环境或上游源码。默认 90 秒沿用原 Arena 交付协议；
源 OpenArm 配置的 30 秒可能截断历史约 40 秒的回归轨迹。

适配还保留 Arena 解析出的 PhysX 后端，并为新版 Warp 夹爪关节索引提供 Torch 读取索引；
原动作处理、目标写入和限速语义保留。录像收尾时，只在 env 0 恰有一个完成回合且恰有一个
视口文件时关联回合；多回合长视频不冒充单回合录像。

## 输出和验收

运行目录包含：

- `benchmark_result.json`：协议和输入哈希、所选 Arena 接口、各项执行状态、返回码与实际计分。
- `index.html`：本次示例检查的汇总页面。
- 每项检查的 `.log`，以及 Arena 创建的时间戳目录、原生 `index.html` 和 `episode_results_rank0.jsonl`。
- 启用录像时的 `.mp4`，同时链接到汇总页面；单回合视频也显示在 Arena 原生报告中。

检查通过要求子进程退出成功、完成回合数达到目标、记录种子一致、原生 HTML 报告存在，
且实际成功数符合该检查的预期。并行完成可能略超目标，所有完成回合都计入分母。
请求录像时还要求非空 MP4 存在；文件可解码性另用实际视频解码检查验证。
未完成回合不被转换为失败回合；目标未完成则整项检查失败。
执行在首项错误后停止，保留日志与部分产物，整体返回非零值。输出目录绝不自动清空或复用。

本例记录的是成功率和回合长度，不据此宣称物理吞吐率、规划器表现或学习策略性能。
当前检查均使用无状态零动作或显式按环境 reset 的夹具策略。以后接入真实模型时，
还需核对图像预处理、18 关节观测顺序、动作反归一化、历史状态清理和策略输出限幅。
AutoData 生成器的位姿动作限幅 ±0.2 不是本例自动施加给任意模型的协议。

## 主机检查

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s workspace-overlays/openarm-benchmark/tests -v
```

这些测试检查哈希保护、固定初态隔离、缺失结果、重复回合、并行超额计分、
异常退出及旧新任务接口转换。任务接口测试使用显式替身，不导入仿真依赖。
它们不替代实际 USD 加载、控制器执行、相机渲染和成功回归。

2026-10-15 实测固定轨迹在第 1,191 个控制步成功，录像 39.70 秒；零动作两回合各 15 步超时。
最终录像自动关联逻辑随后又通过一次真实 GPU smoke 检查。17 项主机测试通过。
可移交的视频、原生报告、模块说明和验证边界见 `outputs/openarm-benchmark/v002/`；v001 保留原始静态验证记录。
