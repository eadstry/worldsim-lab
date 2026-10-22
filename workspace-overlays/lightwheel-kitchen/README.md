# 光轮厨房：芥末瓶放碗

本地部署保持官方 DROID 机器人、单墙 coastal 厨房、芥末瓶与碗及原任务判据。
`scene.yaml` 是 Arena `98866596fd024d96c874fe6fb95ae916d1133629` 原配置的逐字副本，
来源和 SHA256 见 `source.json`。不修改上游，不安装依赖，不下载策略权重。

## 启动

在本工作树根目录运行，复用本机现有 Arena 环境：

```bash
export ARENA_ROOT=/home/tangyuan/WorldSimReady-Home/IsaacLab-Arena
export ARENA_PYTHON="$ARENA_ROOT/.venv/bin/python"
# 使用者确认接受 NVIDIA Omniverse EULA 后设置：
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y
python3 scripts/task-queue.py submit --name lightwheel-kitchen-smoke --timeout 600 -- \
  bash workspace-overlays/lightwheel-kitchen/run.sh smoke
```

默认无窗口，1 个环境、开启相机、零动作执行 20 步。该检查仅验证场景加载和步进，
不要求完整回合，不代表抓放成功。具有桌面显示权限时，末尾添加 `--viz kit` 可显示窗口。
Lightwheel SDK 在首次构建时按需获取厨房资产，需对应网络服务可访问。

`pi05.yaml` 准备了 1 个环境、3 个回合的真实策略评测。先按 Arena
`skills/user/serve-openpi-policy/SKILL.md` 准备兼容的 pi05 DROID 服务（默认 127.0.0.1:8000），
再通过相同队列执行 `run.sh pi05`。本部署没有自动启动模型服务。
外部服务可通过尾部覆盖参数指定：
`runs.lightwheel_mustard.policy.remote_host=<host>` 和
`runs.lightwheel_mustard.policy.remote_port=<port>`。

运行结果由 Arena 写到本工作树 `runs/lightwheel-kitchen/<模式>/<时间戳>/`。
保留每次输出和共享队列日志。正式评测应检查 `arena_experiment_result.json` 中各 Run 状态，
并检查回合记录及 `index.html`；不能只根据进程退出码判断策略成功。

启动器固定使用同目录的 `scene.yaml`；共享 environment.type 覆盖发生在 Arena 解析场景前。
原生 YAML 直接运行时默认引用上游等价场景，使用启动器则选择本地副本。

## 2026-10-16 本机验证

- 共享队列任务 32 成功：RTX 5090，1 环境，开启相机，零动作完成 20 步。
- 结果：`runs/lightwheel-kitchen/smoke/2026-10-16_18-32-40/arena_experiment_result.json`，
  `lightwheel_mustard.status = completed`，环境定义指向本地 `scene.yaml`。
- 未完成完整回合（episodes 为空）；生成的 HTML 报告为空。没有策略成功率证据。
- 首次获取 Lightwheel 厨房包成功。实际复用环境包版本：Isaac Sim 6.1.0.0、
  Isaac Lab 16.4.0、lightwheel-sdk 1.0.3；与上游文档支持表不同，此结论仅覆盖本次短检查。
  上游 Arena/IsaacLab 存在原有本地修改并保留；HEAD 检查不等同于源码干净性保证。
- 任务 30 因未设置非交互 EULA 变量退出；任务 31 因错误地覆盖类型化后的
  environment.type 退出。最终入口改为解析前的 shared.environment.type，任务 32 通过。
- `bash -n`、场景来源 SHA256 校验和 `bash scripts/cloud-check.sh --allow-uninitialized` 通过。
  本工作树有意不检出上游子模块，运行时显式复用主目录环境；主机检查未覆盖 Pi 推理。

自审：检查了全部配置、来源、启动参数和输出位置；部署保留原任务和上游文件，
使用共享队列串行执行，输出独立保存。未提交资产缓存、模型、运行日志或机器环境。
主机检查和执行者自审不代表独立审阅批准。
