# AutoData 域随机化实测入口

复用现有 `autodata` 环境、AutoData 内嵌 Isaac Lab 和 OpenArm production 的已准备 runtime，不安装依赖或修改上游。

```bash
bash workspace-overlays/autodata-domain-randomization/run.sh --output runs/domain-randomization-NEW
MPLCONFIGDIR=/tmp/autodata-dr-mpl /home/tangyuan/miniconda3/envs/autodata/bin/python workspace-overlays/autodata-domain-randomization/report.py --run runs/domain-randomization-NEW --output outputs/autodata-domain-randomization/vNEW
```

两个输出目录必须不存在。GPU 运行需要可访问的 NVIDIA 设备；在桌面沙箱中需要宿主机执行权限。脚本的准备阶段只创建本次新目录，不改已有 runtime。

测试默认任务的 XY 位置随机化，4 环境 × 64 次 reset，随后比较同种子、不同种子和关闭随机化的对照，并运行 12 步零动作物理检查。没有执行轨迹规划、数据生成或训练。全部 9 项检查通过才视为 reset 测试通过。

统计记录在额外物理步前取样。前九次 reset 在取样后执行一个控制步，将物理位姿传播到 RTX/Fabric，再保存原相机和固定诊断视角；图像标签使用取图时物理状态。诊断视角仅用于展示，不修改任务默认配置或数据集相机标定。

2026-10-16 的最终结果见 [v002 报告](../../outputs/autodata-domain-randomization/v002/report.md)。第一轮 CUDA 库路径缺失；第二轮 reset 图像未同步。失败与中间运行目录均保留在 `runs/domain-randomization-20261016/`。v001 已封存，不改写，但不应用其拼图说明位置变化。
