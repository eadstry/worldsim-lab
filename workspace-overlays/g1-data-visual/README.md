# Unitree G1 小批量数据生成与全身可视化

使用官方 `galileo_g1_locomanip_pick_and_place` 与 Isaac Lab Mimic，从已标注种子示范
生成新动作轨迹并保存 RGB、动作和状态。独立进程分别使用种子 1、2、3，
每个进程生成一次尝试；数据保留真实 `success` 标记，不把失败筛除后伪称全部尝试成功。

初始箱子位置沿用官方 XY ±0.025 m 随机化，控制频率 50 Hz，CPU PhysX。
末端增加 100 步（2 秒）保持，以观察放下的箱子是否稳定。保持段仍执行原末端 waypoint，
由原成功判据判断；不改变接触力、位置或速度阈值。

添加诊断相机，位置 `(0, -3.6, 1.2)` m、目标 `(0, -0.6, 0.1)` m，
640×360、水平视野 90°。保留原机器人头部相机和环境资产。
机器人走近桌子时腿部会被实际桌面遮挡；不是裁剪视频。

## 运行环境与兼容处理

必须复用已配置环境，本入口不安装仿真依赖、不修改上游或更新依赖 pin。
独立 Arena HEAD 固定为 `98866596fd024d96c874fe6fb95ae916d1133629`。
本机 Isaac Lab 有既存兼容修改；HEAD 一致不等同于干净上游运行验证。

该版本的 G1MimicEnv 未继承 Arena 新的任务进度和物体静止姿态接口，
而 Mimic 会移除终止管理器并将成功配置当普通函数调用。本地适配层：

- 为 G1 Mimic 补充 ArenaWorld、ProgressTracker 访问属性和 ObjectInitialRestPoseRecorder。
- 通过管理器实例化官方 TaskSuccessTerm，正常推进、重置进度，但不触发自动结束；
  Mimic 从同一 tracker 读取实际成功状态。
- 在生成器导出前执行末端保持，继续用相同成功判据累积结果。
- 每个进程仅运行一次尝试，避开本机曾出现的跨回合生成崩溃。

官方种子数据：`nvidia/Arena-G1-Loco-Manipulation-Task`，revision
`07de42fdade76102fc09d921c7b6200d0b31ec01`，文件
`arena_g1_loco_manipulation_dataset_annotated.hdf5`，SHA256
`0ab51ca69c10c2fe3bbd3d21a398dbf1e4b5cbf8c7600275f1f2408513175bfa`。
输入只有 1 段、855 步，不计为本次生成结果。

## 生成与导出

设置 `ARENA_ROOT` 指向已有源码及 `.venv`，按本机已接受的 EULA 配置环境变量。
若已完整缓存官方资产，将 `ISAACSIM_ASSET_ROOT` 指向缓存根目录，减少首次远程 USD 加载。
所有 GPU 仿真必须经共享队列执行；各次使用独立的新输出目录。

```bash
python3 scripts/task-queue.py submit --name g1-seed1 --timeout 600 -- \
  env G1_SEED=1 bash workspace-overlays/g1-data-visual/run.sh \
  --generation_num_trials 1 \
  --input_file runs/g1/input/arena_g1_loco_manipulation_dataset_annotated.hdf5 \
  --output_file runs/g1/seed1/episodes.hdf5

"$ARENA_ROOT/.venv/bin/python" workspace-overlays/g1-data-visual/export_video.py \
  runs/g1/seed1/episodes.hdf5 runs/g1/videos/seed1
```

另外两段分别改为种子 2、3 及对应独立输出路径。
视频保持原始完整帧序列和仿真时长，重新解码计数核验；默认要求一段且 success 为真。
诊断失败数据时可显式传 `--allow-failed`，manifest 仍记录 false。

## 证据边界

本机首次获取并缓存了 237 个官方资产文件。3 个塑料材质默认贴图在官方地址返回 404，
运行仍有材质解析警告；最终图像需人工查看，不能把此运行称为材质完整性验收。
此前初始化失败、接口异常及无末端保持的失败轨迹保留在运行目录。
最终结果、逐帧视频核验与来源哈希见本工作树 `runs/g1/summary.json`、视频 manifest 和 source 文件。
数据和资产仅本地保存，不提交到 Git，也不上传外部平台。

## 2026-10-17 本机运行结果

最终独立队列任务 47、48、49 均正常退出，三个 HDF5 的 success 均为 true。

| 随机种子 | 完整帧数 | 时长 | 最终箱子线速度 |
| --- | ---: | ---: | ---: |
| 1 | 941 | 18.82 s | 0.000365 m/s |
| 2 | 1021 | 20.42 s | 0.000438 m/s |
| 3 | 922 | 18.44 s | 0.000136 m/s |

三条动作序列均有限，初始箱子位置不同；视频解码帧数与各 HDF5 完全相同，50 fps。
检查了首、中、末帧，可看到机器人搬运及箱子最终放置。
本机运行版本：Isaac Sim 6.1.0.0、Isaac Lab 16.4.0、PyTorch 2.11.0+cu128。
本结论覆盖这三次最终运行，不表示通用成功率或独立第三方验收。

自审：检查了运行边界、单回合隔离、任务进度/重置语义、末端保持与成功阈值、
相机取景、完整视频帧数和数据所有权。修改仅在本地扩展，不提交运行数据或资产；
保留了此前失败证据。主机检查与执行者自审不是独立审阅批准。
