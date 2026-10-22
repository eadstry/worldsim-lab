"""Write the dated local report and register it only after v3 validation completes."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--date',default='20261021');a=p.parse_args();date=f'{a.date[:4]}-{a.date[4:6]}-{a.date[6:]}';folder=a.project/'docs'/'autodata';report=folder/f'autodata-multirobot-v3-{a.date}.md';gallery=f'autodata-multirobot-v3-gallery-{a.date}.html';assert not report.exists();rows=[];counts=[]
for robot,label in [('g1d','宇树 G1-D'),('openarm','OpenArm'),('so101','SO101')]:
 ds=a.root/'datasets'/robot;validation=json.loads((ds/'validation.json').read_text());info=json.loads((ds/'meta'/'info.json').read_text());assert validation['episodes']==12 and validation['all_numeric_rows_exact'];episodes=[json.loads(path.read_text()) for path in sorted((a.root/'production'/robot).glob('episode-*/verification.json'))];assert len(episodes)==12 and all(x['success'] for x in episodes);worst=max(check['error_xy_m'] for episode in episodes for check in episode['checks']);counts.append(validation['frames']);rows.append(f"| {label} | 12（6 抓取 + 6 排序） | {validation['frames']:,} | {len(episodes[0]['joint_names'])} | {worst*1000:.1f} mm |")
replay=json.loads((a.root/'action-state-replay-final.json').read_text());assert replay['episodes']==36 and replay['frames']==sum(counts);assert all(row['maximum_joint_replay_error']==0 for row in replay['results'])
text=f'''# 三种机器人在 mini 场景中的抓取与 RGB 排序数据

创建日期：{date}。分支：`codex/autodata-multirobot-v3`。任务基线：`2868f7c3c12a5b353f1fe15063b8c97937c0435c`。

三套 LeRobot v3.0 数据分别对应宇树 G1-D、OpenArm 和 SO101，共 36 条演示、{sum(counts):,} 帧。每个本体覆盖抓取方块、RGB 排序两类任务和六种条件。每条 RGB 视频为原生 1920×1080、30 fps；数值状态在动作施加前记录，`next.*` 在随后 40 个 MuJoCo 子步后记录。

数据来源为脚本控制的 MuJoCo 接触仿真，配合 Blender 的 mini 场景渲染。用途为面试可视化和小规模数据管线试验。策略训练、真机迁移和 Isaac Sim 运行未开展。

## 文件与选择方式

打开[素材选择页]({gallery})可按机器人、任务和条件筛选视频，下载 MP4，并查看夹持与终态 PNG。

本地媒体位于工作目录的 `runs/multirobot-v3/production/<robot>/episode-XX/`。三套标准数据位于 `runs/multirobot-v3/datasets/<robot>/`。压缩包在 `runs/multirobot-v3/delivery/`，包括三份各 12 条的本体包，以及一份 36 条合集。媒体和机器人资产保存在本地压缩包，Git 只提交本次脚本与文档。

| 本体 | 演示数量 | 帧数 | 状态/动作维度 | 本次样本最大落点偏差 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

落点偏差为物理释放、稳定后相对于目标中心的 XY 距离。完整排序还要求三块颜色次序正确、间距大于块边长，且均稳定落在桌面。统计只描述本套筛选后的演示。

## 修复与生成方法

G1-D 使用官方 `G1_D` URDF 的 Dex3 原生手部网格和七个手部关节。OpenArm、SO101 均使用本体原生夹爪。凹形夹爪碰撞网格经 CoACD 分解，避免单个凸包填住夹持空间；原始视觉 CAD 网格保留。SO101 还保留了官方 MJCF 的 ±3.35 Nm 执行器限值。

抓取对准点按夹指内侧、方块尺寸和手部姿态确定，路径通过连续逆运动学求解。控制器使用有限刚度位置驱动及理想重力补偿。方块在任务中由自由刚体和接触力运动；数据模型未使用焊接、附着约束或中途修改方块位姿。取放区域留出原生夹爪的运动空间，避免已放置动作碰乱后续待抓物体。

图像保留 `scene000430` 的原桌面、地板、室内结构及已打包贴图。桌面任务区域清除了餐桌摆件和椅子。渲染采用 PBR 材质、平滑 CAD 表面法线、保留锐边的处理及室内面积光；每个 30 Hz 状态单独渲染。训练视频使用 Blender EEVEE、32 samples，H.264 CRF 16；静止阶段允许相同画面，没有将低帧率视频复制成 30 fps。

## 域随机化

| 编号 | 条件 | 配置 |
| --- | --- | --- |
| 0 | 基准 | mini 原室内背景、标准光照 |
| 1 | 暖光 | 暖色面积光，功率比例 0.65 |
| 2 | 冷光 | 冷色面积光，功率比例 1.4 |
| 3 | 布局与视角 | 方块 XY 扰动至 ±2 mm，固定相机位置偏移并重新对准 |
| 4 | 材质 | 桌面及机器人表面粗糙度变化，RGB 语义颜色保留 |
| 5 | 背景替换 | 保留 mini 前景桌面和地板，使用带微表面纹理的三维背景板替换远景 |

每条轨迹还独立采样方块质量、摩擦和微小初始位置变化。质量范围 31.5–38.5 g，方块摩擦系数范围 1.1–1.35。具体种子、实际采样值、相机位姿、焦距和渲染参数保存在每条轨迹的 JSON，以及包内 `meta/domain_randomization.json`。本次没有使用高斯背景资产。

## LeRobot v3 字段

| 字段 | 含义 |
| --- | --- |
| `observation.state` | 动作前的全部受控关节位置，顺序使用源模型关节名 |
| `action` | 随后 1/30 秒施加的绝对关节位置目标 |
| `next.observation.state` | 40 个物理子步后的关节位置 |
| `observation.images.overview` | 与动作前状态对应的 1080p RGB 视频 |
| `observation.cube_positions` | R、G、B 三块方块的动作前世界位置 |
| `next.observation.cube_positions` | 对应的动作后位置 |
| `domain.condition` | 0–5 的随机化条件编号 |

转动关节使用弧度，滑动关节使用米。G1-D 的状态/动作包含固定基座上的全身关节，其中右臂及 Dex3 用于任务；OpenArm 保留左右两臂，右臂执行任务；SO101 为六个原生关节。SO101 的物理弧度没有转换为实机 API 的 0–100 夹爪标定值。

数据由 LeRobot 0.4.3 官方 `create/add_frame/save_episode/finalize` API 写入，包含标准 Parquet、MP4、任务及 episode 元数据。编码参数通过本次导出适配器设为 H.264 CRF 16 / GOP 15。读取示例：

```python
from lerobot.datasets.lerobot_dataset import LeRobotDataset

ds = LeRobotDataset(
    "local/g1d_home_mini",
    root="/path/to/datasets/g1d",
    video_backend="torchcodec",
)
sample = ds[0]
print(sample["observation.state"].shape)
```

本机使用已有的 LeRobot/TorchCodec/FFmpeg 环境通过读取验证；迁移机器需自行配置解码依赖。本次未安装或更新仿真依赖。

## 验证范围

- 36 条、{sum(counts):,} 帧的保存动作已在 MuJoCo 3.8.0 中逐帧回放。动作前/后的关节和方块状态均对应原记录，最大关节回放误差为 0。
- 每次抓取均检查抬升、转运全程离桌、释放后的静止高度及落点；排序进一步检查最终 RGB 次序和间距。SO101 的中心偏差门限为 20 mm，G1-D/OpenArm 为 35 mm。
- 渲染坐标组合与 MuJoCo 原生几何世界坐标在三个本体、三个时刻的核对误差低于 1e-6。
- 三套 LeRobot 数据均通过官方 TorchCodec 读取器验证。所有数值行与源轨迹的 float32 表示完全一致；每条 episode 首帧、中间帧、末帧核对解码图像与源视频，全部 MP4 完整解码并核对帧数和分辨率。
- 压缩包逐文件记录 SHA-256，并检查 ZIP CRC 与归档内容哈希。验收明细在各数据集 `validation.json`、每条 `verification.json`、包内 `provenance/` 和 `manifest.json`。

物理场景采用测量得到的 mini 桌面支撑碰撞代理；全屋用于渲染，机器人自碰撞未启用。材质为面向本次渲染的 PBR 重建。固定基座、理想重力补偿、小范围布局变化和筛选后的轨迹均限制了本套数据可说明的泛化范围。后续训练与实机控制适配需单独验证。

## 来源与复现入口

| 资源 | 固定来源 |
| --- | --- |
| G1-D | [Unitree 官方 URDF](https://github.com/unitreerobotics/unitree_ros/blob/5994d4faef0a9cadd3287f8de0199a67eeb2a259/robots/g1_d_description/g1_d.urdf)，提交 `5994d4faef0a9cadd3287f8de0199a67eeb2a259`；原许可 BSD-3-Clause |
| OpenArm | [官方描述仓库](https://github.com/enactic/openarm_description/tree/14ff67b638ff1c738a1b9a6be8aaa5ce5ed2c831)，本地生成的 v2.0 双臂 URDF；原许可 Apache-2.0 |
| SO101 | [官方仿真模型](https://github.com/TheRobotStudio/SO-ARM100/tree/a758567c3978dfeefe282ede0500085a48fe8f78/Simulation/SO101)，new calibration；原许可 Apache-2.0 |
| mini 场景 | [World-SimReady-Home-mini](https://huggingface.co/datasets/Yootta/World-SimReady-Home-mini/tree/f2c633749e7fdf3f981dfd1dd83fc253786713ac)，`scene000430.usdz`；数据集声明 CC-BY-NC-SA-4.0 |
| 格式 | [LeRobot v3.0 官方说明](https://huggingface.co/docs/lerobot/v0.4.3/en/lerobot-dataset-v3) |

原始场景 SHA-256：`d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6`。原始 G1-D URDF SHA-256：`46527573a7140c7129c3587ba5591f269974deb893a0b095ebca500028b8bf40`。

源码入口：[物理任务](../../workspace-overlays/autodata-multirobot-v3/simulation.py)、[模型转换](../../workspace-overlays/autodata-multirobot-v3/prepare_models.py)、[碰撞分解](../../workspace-overlays/autodata-multirobot-v3/decompose.py)、[逐帧渲染](../../workspace-overlays/autodata-multirobot-v3/render_episode.py)、[v3 导出与校验](../../workspace-overlays/autodata-multirobot-v3/export_lerobot.py)、[运行回放校验](../../workspace-overlays/autodata-multirobot-v3/audit_replay.py)。压缩包同时保留实际执行的生成器快照及模型来源记录。
'''
report.write_text(text)
entries=[(f'AutoData 多本体数据（{date}）',f'autodata/{report.name}','36 条原生末端抓取/排序数据的格式、参数、来源与运行验收'),(f'AutoData 多本体素材（{date}）',f'autodata/{gallery}','本地高清 MP4、夹持/终态静帧和域随机化素材选择')]
rootindex=a.project/'docs'/'README.md';body=rootindex.read_text();anchor='| AutoData | [资料与阅读顺序](autodata/README.md) | 原理、数据流、随机化可视化及博客正文来源 |';assert anchor in body;body=body.replace(anchor,anchor+'\n'+'\n'.join(f'| {topic} | [入口]({target}) | {purpose} |' for topic,target,purpose in entries));rootindex.write_text(body)
index=folder/'README.md';body=index.read_text();anchor='| --- | --- |';assert anchor in body;body=body.replace(anchor,anchor+'\n'+f'| {date} · [多本体生成与验收]({report.name}) | 36 条 LeRobot v3.0 数据的配置、来源、验证及适用范围 |\n| {date} · [高清素材选择]({gallery}) | 三种本体、两类任务、六种域条件的本地媒体筛选 |',1);index.write_text(body);print(report)
