# OpenArm 单臂 SkillGen：cuRobo v2 最小验证

这套 overlay 在独立环境加载 v2，保留原有 v1 安装和 AutoData 源码。以同一份已标注源示范、左臂任务、单环境、固定尝试次数比较实际任务成功率、同步后的规划耗时和 GPU 进程显存。

所有机器路径、虚拟环境、模型资产、运行缓存和大文件保存在忽略的 `.local/`。实验结果以版本化的 `outputs/` 报告为准；脚本存在或 schema 检查通过不代表 GPU 验证通过。

## 本机配置

`.local/machine.json` 包含 `autodata_root`、`v1_python`、`v2_python`、`production_snapshot`、`input` 和 `v2_commit`。`production_snapshot` 是 OpenArm production overlay 的独立副本，包含模型、任务、控制适配和输入示范。v2 环境由 v1 环境的副本准备，再仅在副本中安装固定版本 cuRobo；不要在原 `autodata` 环境运行依赖安装。

当前固定 v2 提交：`78fd485fa82d9b9a063fb4985e371814587e666a`。环境内包显示 `0.8.0.dev0+g78fd485`。实验性后端使用两个尚无公开导出的类型；更新提交时应重审，不能直接跟随 `main`。

## 执行顺序

1. 核对原环境保护清单，确认 GPU 空闲。
2. 用 v2 Python 运行 `test_host.py`，用宿主 Python 运行 `launch.py --backend v2 --name v2-model-01 --probe-model`。后者检查转换后的 OpenArm 模型及 GPU FK 与 URDF 的一致性，并设置独立 CUDA 缓存。
3. 用宿主 Python 分别运行下面两个命令，按顺序执行，使用新的运行名称：

```bash
python3 workspace-overlays/curobo-v2-mvp/launch.py --backend v1 --name v1-baseline-01 --attempts 5 --seed 101 --timeout 1200
python3 workspace-overlays/curobo-v2-mvp/launch.py --backend v2 --name v2-baseline-01 --attempts 5 --seed 101 --timeout 1200
```

4. 使用 `summarize.py RUN_V1 RUN_V2 --output RESULT_JSON` 汇总，并核对逐次初始物体/机器人状态。检查成功与失败 HDF5 读回及原环境哈希。

`launch.py` 遇到 GPU 计算任务时拒绝正式比较；`--smoke` 只用于调试，并会明确标记结果。中途出现其他 GPU 任务也会使汇总中的 `uncontended` 为假。每次运行都有超时、独立输出、日志和进程显存采样。

## 比较口径

- `guarantee_success=False`：任务成功率分母为已完成的尝试，不能只数成功保存的轨迹。
- 启动或模型初始化失败单独记为失败阶段，成功率为未知，不能伪装成完成了 0% 的任务测试。
- `request` 包括世界更新、物体附着和完整 transit；`phase` 是单次接触/自由运动规划。计时前后执行 CUDA 同步。
- 分开报告首个请求与后续请求 p50/p95。后续请求仍可能首次触发带物体等代码路径，不能声称所有 kernel 都已预热。
- NVIDIA 进程显存包含模拟器和渲染，2 秒采样可能遗漏瞬时峰值；PyTorch allocated/reserved 统计不包括全部 Warp、CUDA 或渲染分配。
- 保留相同任务参数、2 个 TrajOpt seeds、2 次外层重试、碰撞余量、关节距离重采样和末端重复。v1 的离散轨迹与 v2 的 B-spline 表示不同，优化器内部设置应单列；不要将端到端差异归结为纯内核加速。
- 5 次尝试是可行性筛查，需报告成功率区间，不足以证明总体成功率相同。

`model.py` 转换机器人配置，`v2_planner.py` 实现现有 SkillGen 的 planner 契约。`prepare.py` 只创建独立 hook 副本，去除不能迁移的 v1 内部求解 attempt 监控；公共请求与 episode 监控继续保留。
