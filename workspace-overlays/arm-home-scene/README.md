# Franka 家庭场景单条示范

当前 Arena 包含 `lift_object`、`cube_goal_pose` 等 Franka 机械臂环境，以及
`pick_and_place_maple_table` 的 DROID/Franka 系列配置。本扩展复用当前 Isaac Lab
`FRANKA_PANDA_HIGH_PD_CFG` 和 `scripts/tutorials/05_controllers/run_diff_ik.py`
的控制器接口，在家庭场景原餐桌上执行抓取、抬起、横移、放下和松爪。
这是脚本控制的物理示范采集，不是训练策略推理或 Mimic 扩增，也不是未经修改的 Arena 环境入口。

场景来自 `Yootta/World-SimReady-Home-mini`，revision
`f2c633749e7fdf3f981dfd1dd83fc253786713ac`，原始 USDZ SHA256
`d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6`。
许可证 CC-BY-NC-SA-4.0；不重新分发资产。

`prepare.py` 只写新的 USD 引用层。住宅平移 `(-22.35, 4.75, -.75)` m，
使原生餐桌顶面位于 z=0，地面位于 z=-.75 m。餐桌椅子与桌面装饰在派生层中停用，
其他家具、墙壁、地面和原餐桌保留。住宅刚体动态与家具关节关闭，保留静态碰撞。
停用原住宅灯光及天花板，运行时用穹顶灯与面光源补光。
原始 USDZ、上游源码、其他工作树和此前数据不修改。
派生层保留恒等变换的 default prim，将住宅平移放在子节点，防止加载器的初始位姿覆盖它。
运行时再次检查原餐桌包围盒高度和任务 XY 范围；机器人按 IK 教程显式写入默认关节状态。

复用已有 GPU 运行环境，不安装仿真依赖。资产与环境路径由调用方提供：

```bash
"$ARENA_ROOT/.venv/bin/python" workspace-overlays/arm-home-scene/prepare.py \
  --home /absolute/path/scene000430.usdz --output runs/prepared-NEW

python3 scripts/task-queue.py submit --name franka-home --timeout 1800 -- \
  env ARENA_ROOT="$ARENA_ROOT" bash workspace-overlays/arm-home-scene/run.sh \
  --home runs/prepared-NEW/home-franka.usda \
  --robot-usd /absolute/path/Isaac/IsaacLab/Robots/FrankaEmika/Legacy/panda_instanceable.usd \
  --output runs/episode-NEW

"$ARENA_ROOT/.venv/bin/python" workspace-overlays/arm-home-scene/verify.py runs/episode-NEW
```

机器人资产使用已有 runtime 对应的官方 Isaac 6.1 内容根及其相对引用，不自动更新依赖。
准备层使用绝对资产引用，迁移时重新准备。输出目录必须不存在；失败结果保留，重试使用新目录。
GPU 队列内单进程运行 CPU PhysX 和 RTX 相机；其他验证任务不抢占。

记录 950 个控制步、50 Hz、19 秒。每个控制步四次 .005 秒物理积分。
HDF5 `data/demo_0` 包含 8 维动作（绝对 TCP xyz、XYZW 四元数、单指开度米），
关节位置/速度、箱体 13 维根状态、TCP 位姿、阶段编号及两个 RGB 流。
动作对应接下来一个控制步，obs 是该步完成后的状态；没有预置状态回放或物体附着。
输出 `overview.mp4`、`detail.mp4`、关键帧、整屋截图与 JSON 判定结果。
相机位姿和内参配置随 summary 保存；视频每帧来自同一次仿真。

成功为本派生任务的明确判定：方块曾比稳定初始高度抬起超过 .15 m，最后至少
50 步在目标 XY ±.04 m、z=.02±.015 m 内，线速度 <.02 m/s，松爪并撤回。
`verify.py` 从 HDF5 状态重新检查最后 50 步、实际手指开度、TCP 分离距离、
有限数值与两个视频的解码帧数。这个判定不同于 Arena 原任务的官方成功谓词。
这是一条脚本示范的验证，不是泛化成功率或完整家具交互验证。

运行状态和证据以本次 `runs/episode-*/summary.json`、`verification.json` 为准；
静态检查不能表示物理抓取通过。资产、HDF5、视频及机器路径仅本地保存在 runs。

## 2026-10-17 验证

队列任务 95 成功退出，`runs/episode-r07/` 保存一条 950 帧、50 Hz、19 秒的成功示范。
独立读取 HDF5 状态检查抬高量约 .225225 m、最终位置位于目标区域、末尾 50 步速度为 0、
实际手指已打开，TCP 与物体距离至少 .2109 m。生成器记录末尾连续稳定 200 步（4 秒）。
两个 MP4 重新解码均为 950 帧，分辨率分别为 960×540、640×480。
动作和状态均为有限数；检查了阶段图、整屋截图和 HDF5 抓取近景。

最终数据 SHA256 为 `34d72a5b6311d17c14d21a5e4b544d52e9b4fd393ae1ec026b905fb0cf75b519`。
源代码、原始场景及机器人资产哈希、运行版本与验证记录保存在本次 runs。
材质加载仍有 `orig_diffuse_texture` 的 MDL 参数兼容警告；本次验证不覆盖全部住宅材质或碰撞精度。

排队期间的条目被共享调度多次重新编号；最初任务 75 在命令行解析时失败，未进入仿真。
物理调试任务 90、93、94 的失败数据均保留，依次用于修正根节点变换覆盖、
机器人初始关节状态和控制跟踪滞后。没有把失败示范计入最终成功结果。

自审覆盖场景原始数据不可变性、派生层物理范围、初始化和控制、动作/观测时序约定、
成功标签来源、视频帧完整性与数据归属。自审不是独立审阅批准。
