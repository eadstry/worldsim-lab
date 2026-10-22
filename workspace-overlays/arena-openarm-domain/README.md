# OpenArm 场景中的 Arena 域随机化实测

已在本机 RTX 5090、根目录 Arena、PhysX 后端运行真实 OpenArm 左臂拾放场景。机器人、扫描桌面、柜子、蓝色方块、标定相机来自已准备的 `openarm-production/runtime`。结果为 `outputs/arena-openarm-domain/v001`；当前会话提供可切换的实际 RTX 对照帧。

## 结果与适用条件

| 方法 | 场景绑定 | 实测结论 |
| --- | --- | --- |
| LightIntensityVariation | 原穹顶光 | 250 / 3000，USD 参数与画面均改变 |
| LightColorVariation | 原穹顶光 | 暖红 / 冷蓝，USD RGB 与画面均改变 |
| LightColorTemperatureVariation | 原穹顶光 | 2800 / 9000 K，色温启用且画面改变 |
| HDRImageVariation | 原穹顶光 | 本机 studio / beach HDR，实际纹理路径与画面改变 |
| ObjectMassVariation | 原蓝色方块 | 0.04 / 0.12 kg，读回一致；同力响应不同 |
| ObjectDisappearVariation | 原蓝色方块 | p=0 / 1，移出场景后能在下一次 p=0 reset 恢复 |
| PoseRange（独立入口） | 原方块位置范围 | 原任务 X ±40 mm、Y ±60 mm，两个 seed 的真实区间采样在范围内 |
| LightDirectionVariation | 新增方向光 | 原场景只有穹顶光；增加 DirectionalLight 后，旋转读回与画面改变 |
| CameraExtrinsicsVariation | 新增诊断针孔相机 | ROS 光学 X ±30 mm 生效；为可视化扩大，库默认 XYZ ±5 mm |
| CameraIntrinsicsVariation | 新增诊断针孔相机 | fx/fy ±10%，aperture 比例符合预期，画面改变 |
| 原 third_person_camera 内参 | 原 OpenCV 标定相机 | aperture 改变，但 OpenCV fx=603.1517、fy=603.1273 保持不变；完整标定内参检查未通过 |
| 原 third_person_camera 外参 | 原安装相机与原观测更新 | 仅 reset 对照曾得到 60 mm 差距；加入观测刷新后不稳定，三个原环境零动作控制步后 A/B 差距为 0 mm；持续性检查未通过 |

这覆盖当前根目录 Arena 的全部 9 个具体 Variation，加上 PoseRange。7 项直接作用于原光源/方块；方向光与两项诊断相机测试明确增加场景配置。**不能把这 10 项对照通过解释为 OpenArm 原任务相机的随机化全部可用。** 原相机兼容性直接测试了 `third_person_camera`，未逐一测试两个腕部相机。

质量响应保留原桌面碰撞、摩擦和重力，同一世界坐标 Y 向 1 N 外力持续 24 个 1/120 s 物理步（0.2 s）。0.04 / 0.12 kg 对应 Y 位移为 308.697 / 13.064 mm，包含接触、滑动和翻转影响，不能按自由空间质量反比解释。物体消失是破坏任务条件的压力测试，不表示拾放仍可完成。

## 运行与证据

`run.py` 使用 `ArenaEnvBuilder.make_registered()`；方块和穹顶光以 Arena 原生 Asset 包装原生产配置，保留资产路径和物理参数。原 `reset_all` 保留，原 `reset_cube` 替换为唯一的 Arena 方块位姿事件，避免重置所有权冲突。普通对照固定方块中心；PoseRange 对照使用原任务范围。

复用现有共享适配器的机器人、动作、观测、成功条件及 PhysX 配置兼容层。这里直接构造生产环境配置，不调用已缺少历史来源的 `shared_config.runtime.make_env_cfg()`。通过局部包加载跳过 AutoData 专用的 Gym/cuRobo 注册入口；没有运行规划器。未安装依赖、修改上游源码、改变子模块版本或上传数据。

GPU 任务通过共享 `scripts/task-queue.py` 串行调度：

- 9–11：加载排查和灯光启动验证。缺失 AutoData 注册依赖的加载尝试不算成功。
- 12：全部 10 项真实场景对照通过。
- 13–14：原相机适配器缺少声明字段；保留错误记录，不算兼容性结论。
- 15–16：修正声明字段，内参标定 K 未改变；外参仅 reset 后读回通过。
- 17：追加原观测刷新，发现跨 reset 外参不稳定；内参 K 仍未改变。
- 18：补充方向光实际旋转和 HDR 纹理的 USD 读回，两项通过。
- 19：原环境三个零动作控制步；外参 A/B 差距回到 0 mm，证实扰动没有持续保留。

封存成果包含每轮结果、配置源码 SHA256、对应运行脚本快照、错误记录和 PNG。首次完整运行的脚本快照在运行结束后、修改之前保存；后续脚本在启动时保存自身快照。每轮报告在 `app.close()` 前落盘，判断以 `result.json` 内容为准，不能以 Kit 进程退出码 0 代替通过。

根目录 Arena HEAD 为 `98866596fd024d96c874fe6fb95ae916d1133629`，带有原先存在的本地修改；不等同于纯净上游提交或 AutoData 内嵌 Arena。运行期间纳入 SHA256 的配置源码保持不变；没有完整封存运行环境和所有资产依赖。

运行命令示例（从任务 worktree，替换本机绝对路径；使用现有兼容 Python，不安装环境）：

```bash
python3 scripts/task-queue.py submit --name openarm-domain --timeout 1200 -- \
  env OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y PYTHONDONTWRITEBYTECODE=1 \
  /path/to/IsaacLab-Arena/.venv/bin/python workspace-overlays/arena-openarm-domain/run.py \
  --arena-root /path/to/IsaacLab-Arena --workspace-root /path/to/WorldSimReady-Home \
  --runtime /path/to/WorldSimReady-Home/workspace-overlays/openarm-production/runtime \
  --output runs/openarm-domain-new
```

原相机持续性检查追加 `--only extrinsics --camera-target third_person_camera`。内参追加 `--only intrinsics --camera-target third_person_camera`。

## 验证边界

这里验证场景变化、参数读回和受控物理响应，未执行 cuRobo 规划、抓取回放、任务成功率、训练、Newton 后端或随机分布统计。除 PoseRange 两个 seed 外，均为固定取值/概率端点 A/B 对照。当前可视化已在本机浏览器检查全部 12 个选择、图像解码、736 px 和 360 px 布局，无脚本异常或横向溢出。

保持本地保存，不推送、不发布。
