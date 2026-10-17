# Franka 家庭场景：cuRobo × 有无障碍物

在 `arm-home-scene` 提交 `755a23f` 的物理抓取入口上建立对照。新增实现放在本目录，
不改写旧数据、原始 USDZ、上游 checkout 或已安装运行环境。

## 正式协议

2 个方法 × 2 个障碍条件 × 3 个配对位置，共 12 次尝试。抓取 XY 为
`(.50,.00)`、`(.49,.01)`、`(.51,-.01)` m，目标为 `(.50,-.30)` m。
新增固定蓝色障碍物为 `16×4×32 cm`，中心 `(.50,-.15,.16)` m。
三组位置是固定筛查状态，不是总体成功率抽样。

| 因素 | 条件 |
|---|---|
| 方法 | 局部 DLS IK；cuRobo MotionGen 辅助方案 |
| 新增障碍物 | 无；有 |
| 共用部分 | 原家庭餐桌、Franka 高 PD 配置、4 cm/50 g 方块、摩擦、初始关节状态、抓取点、目标、50 Hz 控制、两路相机与成功阈值 |
| 方法差异 | IK 在各段跟踪 TCP 直线路径；cuRobo 在横移及预放置段执行关节规划，最后 4.9 cm 下降与抓放接触仍共用 IK |

规划端复用现有 `autodata` Python 的 cuRobo v1 API，仿真端复用现有 Arena `.venv`。
两者通过受监督的前台工作进程交换 JSON，不混用两套 torch/CUDA 库，不安装依赖。
MotionGen 使用 4 个 TrajOpt seeds、4 个 graph seeds、32 个 IK seeds、32 个轨迹节点、
20 mm 碰撞激活距离、最多 4 次尝试与 20 秒请求上限。默认自碰撞检查开启。
每次实际查询前，将内置 Franka URDF FK 与仿真关节/手部状态核对，要求位置误差 <3 mm、转角误差 <.03 rad。
携带方块用手部坐标中的 35 mm 包围球表达，仅用于规划碰撞检查；仿真不附着或重设方块位姿。

规划世界包含地面、桌面及新增障碍物的近场代理。桌面固定底座处留孔，避免安装接触被当成非法初态。
住宅完整网格保留在物理场景，但未全部导入 cuRobo；本实验不代表整屋导航或全部家具避障验证。
原生餐桌与住宅坐标、静态家具变体以及资产哈希由 `prepare.py` 的新引用层和 manifest 记录。
原始场景固定为 `Yootta/World-SimReady-Home-mini` revision
`f2c633749e7fdf3f981dfd1dd83fc253786713ac`，原始 USDZ SHA256
`d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6`。
数据集许可证为 CC-BY-NC-SA-4.0；本目录不重新分发资产。

## 运行与数据

```bash
"$ARENA_ROOT/.venv/bin/python" workspace-overlays/franka-curobo-comparison/prepare.py \
  --home /absolute/path/scene000430.usdz --output runs/prepared-NEW

python3 scripts/task-queue.py submit --name franka-curobo-factorial --timeout 2400 -- \
  env ARENA_ROOT="$ARENA_ROOT" python3 -u workspace-overlays/franka-curobo-comparison/experiment.py \
  --home runs/prepared-NEW/home-franka.usda \
  --robot-usd /absolute/path/panda_instanceable.usd \
  --planner-python /absolute/path/existing-autodata/bin/python \
  --trials 0 1 2 --output runs/comparison-NEW
```

必须使用同一主机的共享队列。一个队列条目监督整个实验，所有子进程保留在队列进程组内。
每个样本使用新进程和独立输出，方法顺序在配对位置之间反转；排队/运行期间禁止修改执行源码。
源文件哈希在每次样本启动前核验。基础设施失败会中止余下样本；完成的规划/任务失败会继续并留在分母中。
输出目录必须不存在。失败数据保留，重试使用新目录，不静默覆盖。

每次生成状态/动作 HDF5、完整广角和近景 MP4、阶段截图与 `summary.json`。
为控制本机磁盘占用，HDF5 不重复保存 RGB 数组；RGB 用同期 50 Hz 视频保留。
HDF5 动作统一为 7 个关节目标（rad）和 2 个指关节目标（m），观测是执行该控制步后的状态。
同时记录关节状态、TCP、方块、阶段、物体与障碍物 AABB 辅助间距及障碍物接触力。

## 判定与计时

任务完成：抬高 >15 cm；末尾至少连续 50 步在目标 XY ±4 cm、z=.02±.015 m 内且速度 <.02 m/s。
报告另读 HDF5 检查实际松爪与 TCP 撤回 >15 cm。
“无障碍物接触完成”还要求新增障碍物与所有机器人刚体/方块的接触力峰值 <1 N。
每个 .005 s 物理步读取过滤接触力，保存每控制步峰值；此指标不等于没有任何桌面或自碰撞。

规划请求前后同步 CUDA，记录 FK/负载更新和规划请求时间。
模型构建/预热不包含导入；完整工作进程启动、逐步控制计算、含渲染/IPC 的进程墙钟时间分别保存。
不同指标不能相互冒充。各进程预热后的实际负载请求仍可能首次触发部分 kernel，不宣称完全稳态。
cuRobo 轨迹只放慢、不加速超过规划时间；额外保持时间与实际仿真时长均记录。
开始每次样本前记录 GPU 占用，不能把有外部负载的墙钟数字当成独占性能。

## 报告与验证

```bash
"$ARENA_ROOT/.venv/bin/python" workspace-overlays/franka-curobo-comparison/test_host.py
python3 scripts/task-queue.py submit --name franka-curobo-report --timeout 600 -- \
  env MPLCONFIGDIR=/tmp/franka-curobo-mpl "$ARENA_ROOT/.venv/bin/python" \
  workspace-overlays/franka-curobo-comparison/report.py --runs runs/comparison-NEW \
  --output outputs/franka-curobo-home-comparison/vNEW
```

报告要求 12 个完整且不重复的正式样本，源文件版本相同，并逐组核对配对初态。
独立读回所有 HDF5 和视频帧，输出中文报告、HTML、逐次 CSV、PNG/SVG 图和四格同步视频，
最后生成带 SHA256 的封存 manifest。每个新报告使用新版本，原报告不修改。
视频按相同 50 Hz 起点对齐；较短视频尾帧保持，原视频不改写。

预检曾发现：cuRobo 仅覆盖横移时，横移无接触，但后续 IK 下放仍碰到障碍。
最终协议因此覆盖横移与预放置；最后接触段仍共用 IK。模型预检、传感器接口调试与这些流程试跑
独立保存在 runs，不混入正式 12 次结果。存在材质兼容警告；本次不验收全部住宅材质或家具关节。

实验及报告都仅在本机交付，不上传飞书、ChatGPT 或发布站点。执行者自审与自动检查不是独立审阅批准。

## 已完成的正式结果

共享队列 108 完成 `runs/comparison-r01` 的 12 次物理仿真，队列 110 完成独立读回和报告生成。
无新增障碍时 IK/cuRobo 均为 3/3；有障碍时完成且无新增障碍物接触分别为 0/3、3/3。
有障碍 IK 的接触峰值为 355.70、381.79、322.73 N，cuRobo 三次均为 0 N。
cuRobo 无/有障碍的平均单次规划请求分别为 107.8/113.6 ms，模型构建及预热另需约 2.7 s。
正式样本均为 1000 帧、20 s；已核对配对初态、12 份状态数据及 24 路视频的帧数与 50 Hz 帧率。

封存交付见 [v001 报告](../../outputs/franka-curobo-home-comparison/v001/report.md)。
先在新的 `runs/report-draft-NEW` 生成并检查画面，再运行：

```bash
python3 workspace-overlays/franka-curobo-comparison/seal.py \
  runs/report-draft-NEW outputs/franka-curobo-home-comparison/vNNN
```

封存工具会核对草稿全部文件哈希，要求目标版本不存在；不改写既有交付或正式运行源码。
