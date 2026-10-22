# Franka 家庭场景单条示范

当前 Arena 包含 `lift_object`、`cube_goal_pose` 等 Franka 机械臂环境，以及
`pick_and_place_maple_table` 的 DROID/Franka 系列配置。本扩展复用当前 Isaac Lab
`FRANKA_PANDA_HIGH_PD_CFG` 和 `scripts/tutorials/05_controllers/run_diff_ik.py`
的控制器接口，在家庭场景原餐桌上执行抓取、抬起、横移、放下和松爪。
这是脚本控制的物理示范采集，不是训练策略推理或 Mimic 扩增，也不是未经修改的 Arena 环境入口。
默认仍为方块；`--object-kind banana --object-usd /absolute/path/banana.usd` 使用 Arena 原生 YCB 香蕉。

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
关节位置/速度、物体 13 维根状态、TCP 位姿、阶段编号及两个 RGB 流。
香蕉根状态使用 `obs/object_state`；方块保留 `obs/cube_state` 和旧摘要字段。
动作对应接下来一个控制步，obs 是该步完成后的状态；没有预置状态回放或物体附着。
输出 `overview.mp4`、`detail.mp4`、关键帧、整屋截图与 JSON 判定结果。
相机位姿和内参配置随 summary 保存；视频每帧来自同一次仿真。

成功为本派生任务的明确判定：物体曾比稳定初始高度抬起超过 .15 m，最后至少
50 步在目标 XY ±.04 m、参考静止高度 ±.015 m 内，线速度 <.02 m/s，松爪并撤回。
方块参考高度 .02 m，香蕉参考高度 .018335 m（来自原始网格下边界）。
`verify.py` 从 HDF5 状态重新检查最后 50 步、实际手指开度、TCP 分离距离、
有限数值与两个视频的解码帧数，并要求至少 50 步持续悬空搬运且物体距 TCP <.08 m。
这个判定不同于 Arena 原任务的官方成功谓词。
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

## 香蕉抓取

香蕉来自当前 Arena 注册项 `banana_ycb_robolab`，资产相对路径为
`Isaac/IsaacLab/Arena/assets/object_library/srl_robolab_assets/objects/ycb/banana.usd`，
使用官方 Isaac 6.1 staging 内容根及原始 `textures/obj_000010.png`。
USD SHA256：`a0aee64b0d9f6aae5689c1787e176776696ff38f23d17da0e226da19f0d9b064`。
不缩放香蕉，保留原生 0.12 kg 质量、纹理和凸分解碰撞；这是刚体模型，未模拟果皮变形或损伤。

原始包围盒大小约 `(0.108888, 0.178412, 0.036670)` m。沿 Y 为长轴，
y=0 处的 X 横截面宽约 .03905 m，中点 x≈-.03291 m。
因此 TCP 夹取点为 `(0.46709, 0, .022335)` m，工具 XYZW 四元数为
`(.707107, .707107, 0, 0)`，将夹爪开合方向转到世界 X，跨香蕉中段夹持。
放置点平移 -.2 m 的 Y，绿色标记扩大到 .22×.24 m；运动时长与判定阈值沿用原测试。

在前面的队列命令中增加：

```text
--object-kind banana --object-usd /absolute/path/banana.usd
```

HDF5 记录 `object_kind` 和放置参考高度，summary 记录资产路径、SHA256、抓取点与工具四元数。
新增验证器也对原方块 HDF5 及两路视频做了兼容性复核，输出到本次独立回归目录，
没有修改原方块数据；此项复核不表示重新运行了方块物理仿真。

本次队列任务 105 和最终代码复测任务 107 均通过物理判定。最终结果在
`runs/banana-r02/`：950 帧、50 Hz、19 秒，实测抬高 .227031 m，持续悬空搬运 125 步。
松爪后香蕉在目标区域连续稳定 200 步（4 秒），末尾速度为 0；
验证器确认实际手指已打开、末尾 TCP 距香蕉至少 .21457 m。
广角与近景 MP4 分别为 960×540、640×480，重新解码各 950 帧；动作和状态均有限。
已查看抓取、抬起、最终放置近景和阶段图。两个运行配置相同，不能据此估计泛化成功率。

最终 HDF5 SHA256：`18cca555becd501397b4ee270952e2851f4cf1d94d6ca70f6ac6f941b722c432`。
香蕉原始 USD 与纹理哈希、复用的住宅和机器人资产、最终源码与运行版本均在本次 runs 记录。
自审确认香蕉未缩放、未挂接到夹爪、未写入搬运物体位姿；原方块模式保留旧状态和摘要字段。

## 腕部相机、抓取特写与仿真力

采集命令增加 `--capture-sensors`，保留外部广角，新增手腕相机并收紧外部近景。
腕部相机挂在 `panda_hand`，安装位置复用 Arena 配置的 `(.11, -.031, -.074)` m，
朝向手坐标系 TCP `(0, 0, .1034)`，输出 640×480；手掌和夹爪会占据画面的一部分。
近景相机位于 `(.9, -.55, .45)`、朝向 `(.48, -.1, .14)` m，输出 960×720。
三路 RGB 均为 50 Hz，新增 `wrist.mp4` 和两路近景的阶段 PNG。
腕部设置 `update_latest_camera_pose=True`，以获取移动相机的实际位姿。

`data/demo_0/obs` 新增以下同步记录，T 为控制步数：

| 字段 | 形状 | 意义 |
| --- | --- | --- |
| `finger_normal_force_w` | T×4×2×3 | 左右指尖受到的物体接触法向力，世界 XYZ，N |
| `finger_friction_force_w` | T×4×2×3 | 左右指尖受到的物体摩擦力，世界 XYZ，N |
| `wrist_joint_wrench` | T×4×6 | panda_hand 传入关节的反力 Fx/Fy/Fz（N）、力矩 Tx/Ty/Tz（N·m） |
| `sensor_time_s` | T×4 | 相对记录开始的物理时间，秒，间隔 .005 s |
| `wrist_pose_ros_w` | T×7 | 相机世界位置及 ROS 光学坐标系 XYZW 四元数 |
| `hand_pose_w` | T×7 | 手掌世界位置及 XYZW 四元数，用于安装关系校验 |

力信号每个物理子步读取，200 Hz，每个 RGB 帧对应四个采样点，RGB 对齐该组最后一个时间。
指尖传感器按当前操作物体过滤，不把餐桌等其他碰撞算作香蕉接触力。
腕部六维量在 child-side joint anchor 处、incoming joint frame 中表达，是关节反作用力；
包含运动动力学等影响，不是已做零点、重力和惯性补偿的独立外力六维传感器。
机器人仍沿用原示例的禁用重力配置；未加入传感器噪声、偏置或硬件标定模型。
香蕉仍为刚体，夹持力不能解释为真实香蕉的安全夹持力或损伤阈值。

`data/demo_0/calibration/<camera>/K` 保存实际渲染内参，属性保存安装父节点和 OpenGL 安装位姿。
移动相机每帧的世界外参从 `wrist_pose_ros_w` 读取；静态相机使用安装位姿。
运行以下主机校验导出原始 200 Hz `forces.csv` 和 `forces.png` / `forces.svg`：

```bash
MPLCONFIGDIR=/tmp/arm-home-mpl "$ARENA_ROOT/.venv/bin/python" \
  workspace-overlays/arm-home-scene/sensor_report.py runs/episode-NEW
```

该脚本先独立验证物理任务与全部视频，再检查力数据有限、时间连续、搬运期间双指接触、
接近前及撤离后无物体接触，以及移动相机安装位置与手掌位姿的一致性。

本次最终队列任务 111 成功，结果保存在 `runs/wrist-force-r02/`：19 秒、950 RGB 帧、
每种力信号 3800 个采样点。三路视频完整解码；物体抬高 .227031 m，末尾速度为 0，
搬运期间左右指尖法向力中位数分别为 38.7077、38.8348 N，撤离后为 0。
腕部相机安装位置的逐帧最大重建误差为 7.49e-8 m；已查看实际腕部与外部近景和原始力曲线。
HDF5 SHA256：`a5a3dc8933c9e99e02a4b11d642723b721ffe528155b9e729dc8b511a7bc0311`。
任务 109 的第一版数据保留，但相机位姿使用了初始化值，未通过安装关系校验，不能用于移动相机外参。
修正后重新采集了任务 111，没有改写第一版数据。原有双相机数据通过新验证器兼容复核。
自审覆盖力的单位、坐标系和过滤对象、四个物理子步的时间对齐、移动相机外参刷新、
默认双相机行为和独立输出归属；未将仿真关节反力表述为独立硬件传感器测量。
