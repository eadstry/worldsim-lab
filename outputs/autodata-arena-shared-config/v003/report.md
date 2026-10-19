# 共享配置 GPU 验证 v003

日期：2026-10-13，Asia/Shanghai。本次按用户明确授权，复用现有 AutoData conda 和 Arena `.venv` 进行实际 GPU 验证。没有嵌套启动 Docker、安装或升级依赖，也没有修改上游源码。

## 结果

两侧环境加载、7 维动作处理、6 个控制步和 6 个成功判据正反例均通过。两端比较的 16 项检查全部通过，完整字段见 comparison.json。

| 检查 | AutoData / Arena 结果 |
| --- | --- |
| OpenArm 来源 | 均加载工作区 AutoData 的同一份 openarm_autodata，而非旧交付副本 |
| 动作空间 | `[1, 7]`，左臂相对 TCP IK + 夹爪 |
| 物理 / 控制频率 | 120 Hz / 30 Hz，匹配 |
| 0.1 动作输入的处理结果 | 平移每轴约 0.002 m，旋转每轴约 0.010 rad，匹配 |
| 夹爪目标 | 负值对应 0.0 rad，正值对应约 0.7 rad，匹配 |
| reset 范围 | x 为 ±0.04 m，y 为 ±0.06 m，匹配 |
| 观测 | 全部键、形状、dtype 匹配；三路 RGB 为 `[1, 480, 640, 3]` uint8 |
| 成功函数 / 参数 | 同一 cube_placed_on_pad，四个显式阈值匹配 |
| 公共配置指纹 / 环境源码哈希 | 两次探针记录一致 |

AutoData 通过真正的 setup_env_config 构造生成环境：读取派生 task / embodiment / profile，提取成功项并移除终止条件，然后 gym.make。Arena 通过外置 CompatibleOpenArmEnvironment 和 ArenaEnvBuilder 构造实际仿真环境，成功项取自适配器实际创建的 ProgressObjective。

## 成功判据正反例

以下情况直接写入仿真刚体/关节状态后，调用各自绑定的成功判据：

| 状态 | AutoData | Arena |
| --- | --- | --- |
| 垫内、已释放、静止 | true | true |
| 垫外 | false | false |
| 悬空 | false | false |
| 夹爪闭合 | false | false |
| 线速度超限 | false | false |
| 角速度超限 | false | false |

这是物理环境中的判据测试，不是模型完成任务的成功率，也没有验证完整动作轨迹逐帧等价。

## 完整启动链路及修复

额外运行了 scripts/shared-config.py → Arena 原生 policy_runner 的完整链路。使用临时配置，zero_action、1 环境、1 回合、0.2 秒时限；规范 experiment.json 未修改。完成 6 个控制步，原生 JSONL 确认完成 1 个回合，success_rate=0.0；原生 HTML 评估报告正常生成。这个零动作超时回合用于检查启动、结束与结果记录，不用于衡量策略性能。

完整入口首次运行发现启动器缺少 Arena 环境子命令，导致 --openarm_episode_length_s 参数无法解析。已仅修改根仓库 scripts/shared-config.py：公共/策略参数在前，随后 openarm_left_pick_place，再放环境专用参数。补充顺序断言后，7 项主机测试全部通过，完整 GPU 入口重试通过。

AutoData 首次运行失败于 NVRTC 找不到 libnvrtc-builtins.so.13.0。现有环境已安装该库；按现有 AutoData workflow 的做法，只为重试进程补充 CUDA 13 库搜索路径，随后通过。没有安装库、修改 conda 环境或更改上游。本次失败返回码曾为 0，因此验收以 runtime_result.json.status 和实际断言为准，不能仅用进程退出码。

## 复现与证据

- scripts/validate-shared-runtime.py：每个现有 GPU 环境各执行一次；独立输出配置快照、实际包路径、动作值、判据结果与错误栈。
- scripts/compare-shared-runtime.py：比较已完成探针；失败或缺字段不会被视为通过。
- config/README.md：容器要求、原生环境授权例外及机器本地解释器/库路径参数说明。
- autodata-result.json / arena-result.json：成功探针结构化结果。
- comparison.json：字段级一致性检查。
- evidence.json：GPU、运行状态、原始记录哈希及结束时仓库状态。
- run-records.zip：成功与失败日志、配置快照和原生评估输出；机器根路径已替换为占位符。
- implementation.zip：本版配置、适配器、测试和验证脚本快照。

原始记录保留于机器本地 runs/shared-runtime-20261013，未覆盖失败日志。Arena 顶层工作树保持干净。本任务未修改 AutoData；结束时看到其已有/并行工作树修改，完整清单已记录，未覆盖。

## 版本及结论边界

RTX 5090，驱动 595.91.07。AutoData 环境为 Torch 2.11.0、Isaac Sim 6.0.1.0、Isaac Lab 6.1.14；Arena 环境为 Torch 2.11.0+cu128、Isaac Sim 6.1.0.0、Isaac Lab 16.4.0。实际包路径与发行元数据见结果和 versions 文件；框架版本不同，不能从接口/判据一致推断相同随机初态或物理轨迹逐位一致。

未执行学习策略评估、训练、完整 SkillGen 合成、标注持久化、HDF5 导出或数据回读。仅按用户此前要求保存本地，没有飞书或 ChatGPT 上传，也没有公开发布。
