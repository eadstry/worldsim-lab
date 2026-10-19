# 运行环境配置：从主机到可复验的 GPU 环境

版本：v001；整理日期：2026-10-20（Asia/Shanghai）。

本文把散落在[版本管理约定](version-management.md)、[共享配置说明](../config/README.md)、[Arena 示例说明](../outputs/arena-examples-guide/v001/report.md)、[AutoData 全流程讲解](../outputs/autodata-guide/v003/report.md)和 [OpenArm 生产扩展](../workspace-overlays/openarm-production/README.md)里的环境要求，收敛成一条从空机器到可复验运行的路径。

**边界**：本文只编排配置，不安装或升级仿真依赖，不修改上游子模块。运行时版本来自本仓库的历史 GPU 验证记录；GPU 步骤必须在目标机上按第 6 节逐条验收，静态阅读不能替代运行验证。

## 1. 版本锚点

先钉死版本，再谈安装。这个仓库最容易出的问题不是缺依赖，而是两套 Isaac 环境混装。

| 对象 | 锚点 | 依据 |
| --- | --- | --- |
| `AutoData` 子模块 | `1c7360d85c9ad131ca6c8c70f1f731a6312616f3` | `upstream-lock.json`、gitlink 与 `.gitmodules` 三处一致 |
| `IsaacLab-Arena` 子模块 | `98866596fd024d96c874fe6fb95ae916d1133629` | 同上 |
| `RLinf` 子模块 | `b023deb7e90ceadfe18e0a528e862e3c630f7e0a` | 同上；主机检查之外不使用 |
| Arena 原生环境 | Python `>=3.12,<3.13`、`isaacsim==6.1.0.0`、Isaac Lab `16.4.0`、Torch `2.11.0+cu128` | 该提交的 `pyproject.toml` 与 `uv.lock` |
| AutoData 原生环境 | Isaac Sim `6.0.1.0`、Isaac Lab `6.1.14`、Torch `2.11.0` | 2026-10-13 共享配置 GPU 验证记录 |
| 已实测主机 | RTX 5090、驱动 `595.91.07`、Docker `29.8.1` | 同上 |

两套原生环境的 Isaac Sim 与 Isaac Lab 版本不同，不能共用一个解释器，也不要在同一环境里升级或覆盖安装。`curobo` 在 v1 与 v2 中包名相同、API 不同，只能靠独立解释器切换；直接覆盖安装无法实现透明回退。

## 2. 主机层

### 2.1 组件清单

- Linux 主机与可用的 NVIDIA 驱动、GPU。
- 容器路线：Docker 与 NVIDIA Container Toolkit（`nvidia-smi` 在容器内可见 GPU）。
- 出网：GitHub、npm registry，以及 Nucleus 资产服务——SkillGen 初始化 planner 时要下载 Franka URDF。
- 主机检查：Python 3 与 Node.js 22+；不含任何仿真依赖。

### 2.2 上机核对

```bash
nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

`nvidia-smi` 报无法连接驱动时，先修驱动或容器的 GPU 映射；`--device cpu` 不能当作渲染环境的替代方案。

### 2.3 容量预算

| 资源 | 预算 | 依据 |
| --- | --- | --- |
| 显存 | 1–2 个并行环境至少 24 GB；约 5 个环境建议 48 GB | cuRobo 每个环境一个 planner，随 `--num_envs` 线性增加 |
| 内存 | 8 环境 × 100 条目标的生产运行峰值 RSS 约 66.6 GiB，并触发 cgroup `oom_kill` +1 | 见[过程记录](process-log.md)；长跑前设 cgroup 上限或降低 `--num_envs` |
| 磁盘 | 单条 640×480 RGB 演示约 483 MiB；100 条约 47 GiB（估算） | OpenArm 生产扩展记录 |

8 环境那次运行以 `SIGKILL` 结束，不是任务逻辑失败。扩容前先把内存预算算清楚。

## 3. 仓库层

```bash
git clone https://github.com/eadstry/WorldSimReady-Home.git
cd WorldSimReady-Home
bash scripts/cloud-setup.sh
```

脚本依次做四件事：检查版本锁定与上游是否干净、忽略 LFS 初始化三个顶层子模块、`npm --prefix private-blog ci`、安装提交门禁并运行完整主机检查。

等价的手动步骤：

```bash
python3 scripts/check-version-management.py --allow-uninitialized --require-clean-upstream
GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --jobs 3 AutoData IsaacLab-Arena RLinf
npm --prefix private-blog ci
python3 scripts/review-workspace.py install
bash scripts/cloud-check.sh
```

几个容易踩的点：

- 子模块只按 `upstream-lock.json` 初始化，**不加 `--remote`**；需要嵌套依赖时，进入对应子模块再 `git submodule update --init --recursive`。
- `GIT_LFS_SKIP_SMUDGE=1` 只跳过源码阶段的大型资产。跑生成前必须在子模块内 `git lfs pull`，否则拿到的是 LFS 指针而不是 HDF5。
- `review-workspace.py install` 每台机器、每个仓库装一次：它把门禁放进共享 Git 元数据并把 `core.hooksPath` 指向绝对路径，不改全局 Git 配置。
- 主机检查不需要 GPU。`--allow-uninitialized` 只表示"有意不检出上游"，不表示运行依赖已就绪。
- 需要并行任务时用 `python3 scripts/review-workspace.py start <name>` 建 worktree，不要复制带未提交修改的目录；各 worktree 使用独立运行目录。

## 4. 运行环境

按任务选一条，不要混用。

### 4.1 容器路线（默认）

容器在各自子模块根目录启动，`AutoData` 与 `IsaacLab-Arena` 各自带自己的 `docker/` 脚本：

```bash
./docker/run_docker.sh           # 普通示例
./docker/run_docker.sh -c        # 含 cuRobo：SkillGen、ik_reachable 放置校验
./docker/run_docker.sh -c -r     # 换了 GPU 架构后必须重建
```

- `-r` 不能省：cuRobo 的 CUDA 内核按实际运行那张卡的算力编译，旧镜像能启动但规划阶段会失败。
- Arena 容器内工作目录是 `/workspaces/isaaclab_arena`；交互 shell 的 `python` 已指向 Isaac Sim 解释器；外部 `docker exec` 要显式用 `/isaac-sim/python.sh`。
- 共享配置要求把整个 `WorldSimReady-Home` 挂载进容器，保留两个上游与 overlay 的相对路径——只挂 Arena 目录不足以运行共享环境。
- 启动器不自动接受 EULA、不创建容器、不安装依赖。

### 4.2 Arena 原生 uv

```bash
cd IsaacLab-Arena
uv sync --extra dev
source .venv/bin/activate
export OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y
```

- 以该提交的 `uv.lock` 为准（`isaacsim==6.1.0.0`）；README 写的 6.0.0 与安装文档写的 6.0.1 都不是安装依据，不要按网页文字手装。
- 原生 uv 不含 cuRobo 可选包，SkillGen 与 `ik_reachable` 校验仍须走容器。
- 上游要求代理执行仿真、评估时使用克隆对应的容器；原生环境只作为有明确授权的例外使用。

### 4.3 AutoData 原生 conda

历史验证组合：Isaac Sim `6.0.1.0` + Isaac Lab `6.1.14` + Torch `2.11.0`。仅在用户明确授权复用既有环境时使用，不新建、不改动 conda 环境。

- NVRTC：`libnvrtc-builtins.so.13.0` 找不到时，只给该进程补 CUDA 13 库搜索路径，不安装库。OpenArm 扩展里的等价做法是 `run-local.sh` 只为本次进程设置 CUDA 13 包的库与工具链路径。
- 退出码 0 不代表通过：Isaac Sim 关闭异常会掩盖 Python 异常，验收要看 `runtime_result.json` 的 `status` 和实际断言。

## 5. 机器本地参数（不入库）

解释器路径、库路径、检查点都按机器配置，不写进公共配置。个人副本放 `config/.local/`、`runs/`、扩展 `runtime/`，这些目录已被 Git 排除，需单独备份。

| 参数 | 作用 | 使用位置 |
| --- | --- | --- |
| `OPENARM_PYTHON` | 选择另一个已配置好的 Python | `workspace-overlays/openarm-production/run-local.sh` |
| `--autodata-root` | 指向另一份兼容的 AutoData 检出 | 同上 |
| `AUTODATA_PYTHON` / `ARENA_PYTHON` | 两端各自的解释器 | `config/README.md` 的运行时检查 |
| `AUTODATA_CUDA_LIB` | AutoData 环境已有的 `nvidia/cu13/lib` 目录 | 同上，只补 `LD_LIBRARY_PATH` |
| `WORLDSIM_REVIEW_PYTHON` | 生产类主机测试的解释器 | `scripts/review-workspace.py` |
| `WORLDSIM_V2_REVIEW_PYTHON` | cuRobo v2 主机测试的解释器 | 同上 |

## 6. 验收顺序

配置完成后按顺序过，前一步不过不要进下一步。

| 步骤 | 命令 | 通过判据 |
| --- | --- | --- |
| 1. 主机检查 | `bash scripts/cloud-check.sh --allow-uninitialized` | 版本锁定、封存成果、共享配置测试与博客构建全部通过 |
| 2. GPU 可见 | 第 2.2 节两条命令 | 宿主机与容器内都能列出 GPU |
| 3. 零动作冒烟 | `python isaaclab_arena/evaluation/policy_runner.py --policy_type zero_action --num_steps 20 cube_goal_pose` | 跑完 20 步并正常退出 |
| 4. Kit 交互 | 同上加 `--viz kit --num_steps 200` | 场景正确、可用 Shift+左键拖动物体 |
| 5. 多配置实验 | `experiment_runner.py --viz kit --experiment_config isaaclab_arena_environments/experiment_configs/getting_started_experiment.yaml runs.parallel_envs.environment_builder.num_envs=8` | 每个 Run 有状态，结果 JSON 可读 |
| 6. cuRobo preflight | `import curobo` + `validate_dataset.py` + 1 条 SkillGen | 记录 1 条成功演示且校验器报 `VALID` |
| 7. OpenArm 运行时 | `bash workspace-overlays/openarm-production/run-local.sh --check-runtime` | `runtime-check-result.json` 为 `passed` |

第 3、4 步的零动作策略不会完成任务，只能证明启动链路可用。换 GPU 或重建镜像后，第 6 步必须重做。

## 7. 常见失败对照

| 现象 | 先查 |
| --- | --- |
| `nvidia-smi` 连不上驱动 | 驱动版本、容器 `--gpus` 映射 |
| `import isaaclab_arena` 失败 | 未激活 `.venv`，或不在容器内 |
| 资产加载失败 | Nucleus 出网；SkillGen 首次规划要下载 Franka URDF |
| HDF5 很小或读不出 | 忘了 `git lfs pull` |
| planner 报 CUDA 显存不足 | 降 `--num_envs`，先单环境验证 |
| 换卡后 cuRobo 内核报错 | `./docker/run_docker.sh -c -r` 重建 |
| 每次都在同一子任务规划失败 | 不是环境问题，查标注起点、`eef_offset`、planner profile |
| 进程退出码 0 但结果异常 | 看 `runtime_result.json.status`，不要只看退出码 |

## 8. 尚未验证

- 本文在 macOS 上整理，整理机没有 NVIDIA 驱动，全部 GPU 步骤未复验。
- Arena 原生环境中 `isaacsim==6.1.0.0` 与实际运行的兼容性未验证。
- 当前锁定的 AutoData 提交不含共享配置所需的 OpenArm 本地源文件，`resolve/run` 会提前失败；恢复要求见[版本管理约定](version-management.md)。
- 8 环境 × 100 条的生产运行仍待 HDF5 回读与根因确认，历史通过记录不能替代这次验收。
