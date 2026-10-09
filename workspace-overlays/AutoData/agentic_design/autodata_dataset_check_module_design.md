# AutoData 生成数据集自动检查模块设计

> 目标：为 AutoData 生成的 HDF5 演示数据集设计一个**自动检查（quality check）模块**，把现有"结构校验"升级为"分级、可配置、可机器解析"的质量检查，且默认运行不需要 Isaac Sim、GPU 与人工。
> 本文所有现状论据引用仓库当前代码（`文件:行号`）；设计决策单独说明；无法在本地核实、需要容器内对真实数据勘查确认的运行时事实（recorder 实际写出的 obs 子键等）显式标注。
> 按 `AGENTS.md` 约定，本设计写入 `agentic_design/`，不改动 `docs/`（人工维护）与 `submodules/`（只读）。

---

## 一、问题定义：结构合法 ≠ 数据可用

### 1.1 现有检查能力盘点

| 能力 | 位置 | 检查内容 | 局限 |
|---|---|---|---|
| 结构校验 CLI | `scripts/validate_dataset.py` | 文件可打开；顶层 `data` 组；每 episode 含 `actions`（dataset）、`initial_state`（group）、`obs`（group）且类型正确；数据集非空；`env_args` 元数据解析（`24-28`、`55-101`、`104-119`） | 只看"有没有、类型对不对"，不看内容质量 |
| 退出码契约 | `scripts/validate_dataset.py:161-176` | 任一文件无效 → exit 1，否则 0；支持多文件/glob | 只有二值结论，无分级 |
| 人眼回放 | 文档 `docs/pages/workflows/franka_cube_stack_mimicgen/step_4_validate_dataset.rst:20-51` | Kit 回放看"抓取是否干脆、放置是否稳定、子任务边界是否平滑"（`34-38`） | 需要 GPU/Kit 与人工；且 PhysX 非确定性使回放失败不能直接判数据无效（`45-51`、`docs/pages/references/troubleshooting.rst:200-203`） |
| e2e 断言 | `autodata_tests/utils/utils.py:11-20`、`autodata_tests/e2e/test_mimicgen_data_generation.py:49` | `assert_valid_dataset` 仅校验存在性与 episode 数下限 | 不校验内容 |
| 生成后自动校验 | `skills/autodata-generate-datasets/scripts/run_generation.sh:123-126` | 生成结束自动调用 `validate_dataset.py` | 继承结构校验的全部局限 |
| 单测 | `autodata_tests/utils/test_validate_dataset.py:13-23`、`26-47` | 合成最小 HDF5 fixture 验证 0/1 退出码 | 只锁结构行为 |

### 1.2 缺口

结构检查无法发现、但会直接污染训练数据的问题（文档已点名两类：子任务边界处抖动、勉强成功的抓取，`step_4_validate_dataset.rst:34-38`）：

- 动作异常：全零/冻结、NaN/Inf、超出归一化范围、长时间饱和；
- 轨迹异常：EEF 相邻帧位置/姿态跳变，插值段与技能段衔接不平滑；
- 物理异常：物体瞬移、穿地、被抓期间相对 EEF 位姿漂移；
- 语义异常：子任务完成信号无上升沿/多次回落、边界不满足生成器最坏情况偏移校验（对照 `autodata_core/pool.py:148-183`、`185-204` 的解析语义）；
- 多样性异常：episode 初始状态重复、长度分布离群。

目前这些问题的发现途径只有人工回放，或等到下游训练/评估时才暴露。

### 1.3 目标与非目标

**目标**
1. **自动**：一次 CLI 调用即可运行；纯 Python 层不依赖 Isaac Sim/GPU，可被流水线与 CI 直接调用；
2. **分级**：文件/结构错误（error）与质量警告（warning）区分，严重级可配置，默认不破坏现有 gate；
3. **可解析**：人类可读表格 + JSON 报告（含 `check_id`、episode、frame、观测值、阈值），agent/CI 可据此决策；
4. **兼容**：现有 CLI 形态、退出码语义、现有 3 个单测行为保持不变（`test_validate_dataset.py:26-47`）；
5. **可扩展**：检查项注册制，新增检查不改 CLI。

**非目标**
- 不做策略评估与指标分析（属 Isaac Lab-Arena / RLinf 的职责）；
- 不自动修复数据；
- 不在生成主循环内做运行时断言（生成期检查是另一个候选设计，见 §9 开放问题）；
- 不试图复刻 Isaac Lab 内部逻辑，不硬编码 recorder 实现细节（见 §2 约束 C1、C4）。

---

## 二、可复用的现有基石与硬约束

### 2.1 可复用基石

| 基石 | 位置 | 复用方式 |
|---|---|---|
| `ValidationResult`（issues 列表 + `valid` 属性） | `scripts/validate_dataset.py:31-44` | 升级为 `Finding` 列表 + 严重级，思想保留 |
| 文件级/ episode 级检查组织 | `scripts/validate_dataset.py:55-101`、`104-119` | 拆成独立检查项，runner 统一调度 |
| 注册表元类模式 | `autodata_core/algorithms.py:44-51`；`autodata_core/selection_strategy.py:18-25`、`34-40` | 检查项 `DatasetCheck` 自动注册，按 `check_id` 查找 |
| JSON 原子写 | `autodata_utils/generation_result.py:55-67`（临时文件 + `fsync` + `os.replace`） | JSON 报告落盘复用同一模式 |
| 配置校验风格 | `autodata_interfaces/env/env_profile.py:226`（`validate_*_dict` 坏输入 raise） | 检查配置 YAML 的校验函数 |
| 纯 Python 位姿工具 | `autodata_utils/pose_math.py:4-10`（docstring 自述 Pure-torch；`unmake_pose:41`、`quat_from_matrix:85` 等） | L2 检查计算旋转距离/正交性校验时直接复用 |
| 合成 HDF5 测试夹具模式 | `autodata_tests/utils/test_validate_dataset.py:13-23` | 每个检查项的正/反/跳过用例 |
| 流水线自动触发点 | `run_generation.sh:123-126` | 升级后自动获得新增检查，`--no-validate`（`20`、`68`）继续可用 |
| CI 入口 | `scripts/ci/run_tests.sh`（`TEST_PATH`/`PYTEST_MARK`，`20-22`、`61-78`） | 新单测天然纳入 premerge/nightly 分层 |

### 2.2 硬约束

- **C1 依赖边界**：仓库已有"纯 Python 层不 import `isaaclab`"的先例（`env_profile.py:9`）；检查内核必须遵守，只允许 `h5py` + `numpy`/`torch`（`pose_math.py` 证明 torch 是可接受的轻依赖）。任何需要 Isaac Sim 的检查必须物理隔离到独立脚本（L3）。
- **C2 CLI 契约**：`validate_dataset.py` 以位置参数接收文件、以 0/1 退出码表达结论，已被 `test_validate_dataset.py:26-47` 锁定；新增能力必须向后兼容。
- **C3 数据现状**：本工作区 `datasets/annotated_datasets/*.hdf5` 与 `autodata_tests/test_data/*.hdf5` 均为 132 字节的 Git LFS 指针（已实测），**无法在本地标定阈值**；阈值默认值必须保守，最终标定在容器内 `git lfs pull` 后执行（`docs/pages/references/troubleshooting.rst:150-155`）。
- **C4 recorder 细节待勘查**：生成数据集由 `ActionStateRecorderManagerCfg` 录制（`autodata_interfaces/env/isaaclab_env_interface.py:193-199`），其实际写入的 `obs` 子键取决于上游 Isaac Lab 版本与 recorder 配置；本工作区子模块未初始化（`submodules/IsaacLab-Arena` 为空），无法本地核实。因此 L1/L2 对 recorder 字段的检查必须 **capability-driven**：字段存在才检查，缺失记 `skipped` 并给出原因；首个真实数据集上先用 `--inventory` 模式勘查并固化断言。

---

## 三、总体架构

### 3.1 分层与目录

```text
scripts/validate_dataset.py              # CLI 保持（位置参数 + 退出码），内部委托检查内核
scripts/replay_check_dataset.py          # [P3] L3 物理重放检查（需要 Isaac Sim，显式调用）
autodata_utils/dataset_checks/           # 纯 Python 检查内核（无 isaaclab 依赖）
├── __init__.py                          # 公共入口 run_dataset_checks(...)
├── spec.py                              # Severity / Finding / CheckContext / DatasetCheck + 注册表
├── config.py                            # CheckConfig.from_yaml + validate_check_config_dict
├── runner.py                            # 文件发现 → 逐文件/逐 episode 流式执行 → 聚合
├── report.py                            # 人类表格 + JSON 报告（原子写）
└── checks/
    ├── structural.py                    # L0：迁移现有 5 类结构检查
    ├── layout.py                        # L1：布局与元数据一致性
    └── kinematic.py                     # L2：轨迹/物理质量（纯张量计算）
```

存放位置的依据：`autodata_utils` 是 first-party 包（`pyproject.toml` 的 pyright include 覆盖），当前 `__init__.py` 只含版权头，不会拖入 `isaaclab`；`scripts/validate_dataset.py` 与 `autodata_tests` 都可按现有方式导入（测试已用 `from scripts import validate_dataset`，`test_validate_dataset.py:10`）。

### 3.2 检查器模型（`spec.py` 草案）

```python
class Severity(enum.Enum):
    ERROR = "error"      # 数据契约破坏，默认计入失败
    WARNING = "warning"  # 质量存疑，默认仅报告；--strict 时计入失败
    INFO = "info"        # 统计性信息

class Scope(enum.Enum):
    FILE = "file"        # 每文件一次
    EPISODE = "episode"  # 每 episode 一次（流式）
    DATASET = "dataset"  # 需跨 episode 统计

@dataclass
class Finding:
    check: str                       # 稳定 ID，如 "kinematics.eef_translation_jump"
    severity: Severity
    path: str
    episode: str | None = None
    frame: int | None = None
    object: str | None = None        # eef/物体/信号名
    message: str = ""
    observed: float | int | str | None = None
    threshold: float | int | str | None = None
    unit: str | None = None

@dataclass
class CheckContext:
    path: Path
    h5: h5py.File
    config: CheckConfig
    episode_name: str | None = None
    episode: h5py.Group | None = None
    actions_len: int | None = None   # 当前 episode 的 T，供 T 对齐检查复用

class DatasetCheck(metaclass=_CheckMeta):   # 对齐 _AlgorithmMeta（algorithms.py:44-51）
    name: str = ""             # check_id，注册键；对外稳定 API（CI gate 依赖）
    default_severity: Severity = Severity.ERROR
    scope: Scope = Scope.EPISODE
    def check(self, ctx: CheckContext) -> Iterable[Finding]: ...
```

运行器只做三件事：按 `Scope` 调度检查项、把异常包装成 `Finding`（检查内部异常不得中断整次运行，记为 `check.crashed` 的 error 并附 traceback 摘要）、聚合统计。检查项本身不打印、不读 CLI。

### 3.3 执行流程

```text
validate_dataset.py main(argv)
  → 解析文件列表（保持位置参数）
  → CheckConfig 合并（内置默认 + --check-config YAML + CLI 覆盖）
  → runner.run(files, config)
      对每个文件：
        L0 结构检查（对照现有 validate_file 的失败即返回语义）
        打开成功后：L1/L2 逐 episode 流式检查（--max-episodes 可采样）
        DATASET scope 检查在 episode 遍历后汇总
  → report.render(findings)  +  report.write_json(...)（可选）
  → 退出码：0 = 无 error（且 --strict 下无 warning）；1 = 否则
```

### 3.4 为什么不把检查内联进 `generate_dataset.py`

`generate_dataset.py` 是 Isaac Sim 进程（`scripts/generate_dataset.py:32-107` 先启动 AppLauncher 再导入其余依赖），内联检查会把"数据质量"耦合进"仿真生成"，且退出时 report 与 Isaac Sim 的关闭流程相互干扰。保持生成脚本职责单一，自动触发交给两条既有管道：
1. `run_generation.sh:123-126`（生成后校验，已是自动流程）；
2. CI/测试（§6）。
如确有"单命令闭环"需求，可在 P3 评估 `--post_check` 或在 `run_generation.sh` 侧增强，动的是流水线而非生成器。

---

## 四、检查项目录（L0–L3）

严重级标注为**默认值**，均可被配置覆盖。阈值中标注"待标定"者必须在 C3 流程后用真实数据固化。

### L0 结构（迁移现有行为；默认 error）

| check_id | 说明 | 现状对照 |
|---|---|---|
| `file.exists` | 路径存在 | `validate_dataset.py:60-62` |
| `file.openable` | 可作为 HDF5 打开（含 LFS 指针/截断文件） | `64-68`、`troubleshooting.rst:159-176` |
| `dataset.data_group` | 顶层 `data` 组存在且为 group | `71-77` |
| `dataset.non_empty` | 至少 1 个 episode | `81-85` |
| `episode.required_fields` | `actions`(dataset)/`initial_state`(group)/`obs`(group)，含类型 | `87-99` |
| `meta.env_args` | `env_args` 可解析 JSON，抽取 `env_name`/`sim_args` | `104-119` |

### L1 布局与元数据一致性

| check_id | 默认级 | 说明 | 依据 |
|---|---|---|---|
| `episode.naming` | warning | episode 名建议 `demo_<n>`（不强制，兼容上游命名） | 上游 recorder 导出命名（`data_generator.py:606` 触发导出） |
| `actions.rank` | error | `actions` 为 2D `[T, D]`，`T>1`、`D>0` | `REQUIRED_DEMO_FIELDS`（`validate_dataset.py:24-28`） |
| `actions.finite` | error | 无 NaN/Inf | 训练数据硬约束 |
| `episode.length_consistent` | error | `obs` 下各 `[T,...]` 数据集与 `actions` 第 0 维一致（capability-driven：只检查可判定的数据集） | `pool.py:120-146` 对 T 一致性的隐含要求 |
| `initial_state.structure` | error | `initial_state` group 非空且递归可读；常见键以 inventory 勘查结果固化 | `annotate_demos.py:356-362` 的 `env.reset_to(initial_state)` 用法 |
| `success.flag` | warning | 若存在 per-episode `success` 字段：成功数据集全 true；`keep_failed=true` 的失败文件（`isaaclab_env_interface.py:201-204`，单独文件导出）按文件角色放宽或跳过 | recorder 标记 `data_generator.py:601` |
| `datagen_info.shape` | warning | 若存在 `obs/datagen_info`（注释数据集必有，`pool.py:123-124`）：`eef_pose`/`target_eef_pose`/`object_pose` 各 `[T,4,4]`，`subtask_term_signals`/`subtask_start_signals` 各 `[T]` | `datastream.rst:120-143`、`pool.py:126-130` |
| `datagen_info.subtask_signals` | warning | 每个 `subtask_term_signals` 恰有 1 个 0→1 上升沿且不回落；非最后信号的上沿位置满足"上沿+2 ≤ T"；SkillGen 数据集的 `subtask_start_signals` 存在性 | `pool.py:160-183`（上沿 +2、末段至 T 的解析语义） |

### L2 轨迹与物理质量（纯张量计算；默认 warning，可配置为 error）

| check_id | 核心算法 | 阈值默认（待标定） |
|---|---|---|
| `kinematics.pose_valid` | 对 `[T,4,4]` 位姿：有限性；右下角 `≈1`；旋转块 `RᵀR≈I`、`det(R)≈1`；可用 `pose_math.unmake_pose`（`:41`）后 numpy/torch 计算 | `atol=1e-4` |
| `kinematics.eef_translation_jump` | 相邻帧 EEF 平移增量 `‖Δp‖` 的分位数超阈值（跳变检测） | 待标定（建议起步 0.05–0.25 m/step） |
| `kinematics.eef_rotation_jump` | 相邻帧旋转角（`quat_from_matrix`，`pose_math.py:85` + 角度提取）超阈值 | 待标定（建议起步 30–90°/step） |
| `actions.range` | 相对位姿通道（单臂 6D 情景）越出 `[-1,1]` 的帧占比 | 0（超出即 finding） |
| `actions.saturation` | `\|a\| ≥ 1-ε` 的帧占比超阈值（长时间顶格=覆盖不足/几何越界） | 待标定（建议 ≤10–20%） |
| `gripper.switch_rate` | 夹爪通道（由 embodiment adapter 的 `actions_to_passthrough_actions` 契约识别，`pool.py:132`）开关次数/时长异常（抖动） | 待标定 |
| `objects.translation_jump` | 若存在 `object_pose`：物体相邻帧 `‖Δp‖` 超阈值（瞬移） | 待标定 |
| `objects.below_floor` | 物体 z 低于地面阈值 | 0 m |
| `objects.grasp_consistency` | 抓取窗口内（由 `subtask_term_signals` 划分）"物体相对 EEF 位姿"变化超阈值（打滑/漂移） | 待标定 |
| `dataset.length_outlier` | episode 长度中位数/MAD 的离群检测（dataset scope） | MAD 倍数待标定 |
| `dataset.initial_state_duplicates` | 初始状态向量近重复检测（生成多样性） | 待标定 |

说明：
- L2 全部为**统计/几何判据**，不做物理仿真；结论是"可疑"而非"无效"，因此默认 warning；
- `--strict` 把 warning 计入失败，供质量要求高的流水线（如训练数据冻结前）使用；
- 阈值第一版必须宽松，用真实数据集（正常样本）走一遍 `--inventory` + 全量检查，观察 finding 分布后再收紧并固化到 `CheckConfig`。

### L3 物理重放复现（P3；独立脚本，默认不自动运行）

`scripts/replay_check_dataset.py`（或复用 Isaac Lab 的 `replay_demos.py` 流程，`step_4_validate_dataset.rst:28-32`）：

- 抽样 N 条 episode，逐条 `env.reset_to(initial_state)` 后重放 `actions`（重置方式参考 `annotate_demos.py:356-362`），统计"重放后 success 复现率"；
- 输出报告为 info/warning：**禁止**把重放失败直接判为数据无效——PhysX 跨 reset 非确定性（`troubleshooting.rst:200-203`、`step_4_validate_dataset.rst:45-51`）；
- 该脚本需要 Isaac Sim，只允许出现在容器内的高级检查清单中，不进入检查内核。

---

## 五、CLI、配置与报告

### 5.1 CLI（新增参数全部可选，兼容现有调用）

| 参数 | 默认 | 说明 |
|---|---|---|
| `<files...>`（位置） | 必填 | 保持不变；支持多文件与 glob 展开由 shell 完成 |
| `--tier {structural,layout,kinematic,all}` | `all` | 选择检查层级；`all` 仍全部为纯 Python 层（不含 L3） |
| `--checks a,b` / `--skip-checks a,b` | 空 | 按 check_id 精确开关 |
| `--strict` | off | warning 计入失败（退出码 1） |
| `--json-report PATH` | 不写 | JSON 报告落盘（原子写） |
| `--check-config PATH` | 无 | YAML 阈值/严重级覆盖 |
| `--max-episodes N` | 0=全部 | 大文件采样上限（抽样对 `dataset.*` 检查不生效并会标注） |
| `--inventory` | off | 只打印字段/形状/dtype/统计摘要，用于 C4 勘查与阈值标定 |

**退出码**：保持 `0`（通过）/`1`（存在 error，或 `--strict` 下存在 warning）。不引入新码位，避免破坏现有 gate（`run_generation.sh:123-126`、`SKILL.md:116` 的"non-zero gate"约定）。

### 5.2 JSON 报告 schema（草案）

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-28T12:00:00Z",
  "config": {"tier": "all", "strict": false, "max_episodes": 0},
  "files": [
    {
      "path": "datasets/generated.hdf5",
      "status": "invalid",
      "num_episodes": 10,
      "env_name": "Isaac-Stack-Cube-Franka-IK-Rel-v0",
      "counts": {"error": 1, "warning": 3, "info": 0},
      "findings": [
        {
          "check": "kinematics.eef_translation_jump",
          "severity": "error",
          "episode": "demo_3",
          "frame": 42,
          "object": "franka",
          "message": "EEF translation jump between consecutive frames exceeds threshold",
          "observed": 0.37,
          "threshold": 0.25,
          "unit": "m"
        }
      ],
      "checks_skipped": [{"check": "datagen_info.shape", "reason": "field not present"}]
    }
  ],
  "summary": {"files": 1, "invalid": 1, "error": 1, "warning": 3, "info": 0}
}
```

### 5.3 检查配置 YAML（草案；校验风格对齐 `env_profile.py:226`）

```yaml
version: 1
tier: all
checks:
  kinematics.eef_translation_jump:
    enabled: true
    severity: warning          # 可提升为 error
    thresholds:
      max_translation_delta: 0.25   # m/step（待标定）
  actions.saturation:
    thresholds:
      max_saturated_fraction: 0.2
episodes:
  max_episodes: 0
```

`validate_check_config_dict(data)` 只接受白名单键；未知 check_id / 未知阈值键立即报错，防止阈值写错静默失效。

---

## 六、集成与自动化触发点

| # | 触发点 | 现状 | 设计改动 | 默认行为 |
|---|---|---|---|---|
| 1 | `run_generation.sh:123-126` | 生成后自动跑结构校验 | 同一命令自动获得 L0–L2（L2 默认 warning，不改变 gate 语义） | 自动；`--no-validate` 仍可跳过 |
| 2 | skill 工作流 `SKILL.md:108-118` | Step 4 只描述结构校验 | 文档补充分级检查、JSON 报告与 `--strict` 用法 | 人工调用 |
| 3 | CI 单测 | `autodata_tests/utils/test_validate_dataset.py` | 新增逐检查单测（合成 fixture，秒级） | premerge 自动 |
| 4 | e2e 断言 | `assert_valid_dataset`（`utils.py:11-20`）只数 episode | 可选：追加调用检查内核（warning 不阻断）作为回归护栏 | nightly/带子进程测试自动 |
| 5 | perf/nightly | `datagen_perf` 断言成功率（`docs/pages/advanced/testing_and_ci.rst:23-25`） | P3：附带质量 finding 趋势统计 | nightly |
| 6 | `generate_dataset.py` | 生成器 | **不做内联**（§3.4）；如需要单命令闭环，P3 评估 | — |

---

## 七、测试策略

1. **合成 fixture 构造器**：在 `test_validate_dataset.py:13-23` 的 `_create_dataset` 基础上扩展为"可注入缺陷"的构造器（合法数据集 + 可控的 NaN、跳变、越界、信号异常等），全部用 `tmp_path`，不依赖 LFS/GPU/容器。
2. **逐检查用例**：每个 check_id 至少 3 类——触发 finding（断言 check_id、severity、episode/frame 定位正确）、通过、字段缺失→记 `checks_skipped` 且不报错。
3. **兼容性用例**：现有 3 个用例（`test_validate_dataset.py:26-47`）语义不变；另加"无效文件 + `--json-report` 仍返回 1 且报告可解析"。
4. **配置用例**：`validate_check_config_dict` 的白名单/坏键/severity 覆盖。
5. **真实数据标定流程**（需容器）：
   - `git lfs pull` 取真实源/生成数据集（C3）；
   - 对正常数据集运行 `--inventory`，记录字段清单与形状（C4 勘查）；
   - 运行默认检查，统计 finding 分布，把无意义项降级/关闭、把有用阈值固化到示例 `check_config.yaml`；
   - 回归：对正常数据全绿（无 error）、对人工构造的坏样本能命中。

---

## 八、分阶段落地

| 阶段 | 内容 | 交付物 | 验收条件 |
|---|---|---|---|
| **P1 结构+布局** | `spec/runner/report/config` 骨架；迁移 L0；实现 L1 中不依赖 recorder 细节的项；`--json-report`、`--inventory`、`--tier`、`--checks/--skip-checks` | `autodata_utils/dataset_checks/**`、改造后的 `scripts/validate_dataset.py`、新增单测 | 现有测试全绿；新单测覆盖每项检查；对现有 e2e 产物可运行且输出与旧版兼容（表格+退出码） |
| **P2 轨迹质量** | L2 全部检查 + 阈值配置；`--strict`；`run_generation.sh` 自动带出 L2；skill 文档更新 | `checks/kinematic.py`、`config.py` 完整版、示例 `check_config.yaml` | 真实正常数据集无误报（或仅少量已解释 warning）；坏样本能被命中；`--strict` 能把它变成 exit 1 |
| **P3 重放+趋势** | `replay_check_dataset.py`（L3）；nightly/e2e 趋势接入；阈值按任务固化 | 重放脚本、CI 流程调整建议 | 抽样重放报告可读；非确定性免责条款写入帮助文本；CI 可消费 JSON |

---

## 九、风险与开放问题

1. **recorder 字段不确定性（C4）**：生成的 `obs` 子键随 Isaac Lab 版本/recorder 配置变化。缓解：capability-driven + `--inventory`，首版不硬编码任何 recorder 私有的键名断言。
2. **`keep_failed=true` 的失败文件**（`isaaclab_env_interface.py:201-204`）：失败 episode 会导出到单独文件。`success.flag` 与质量检查需识别文件角色（建议按导出文件名后缀/CLI 上下文判断），否则误报。
3. **阈值误报**：L2 默认 warning + 宽松阈值 + `--strict` 分级释放；阈值必须经真实数据标定（C3）。
4. **性能**：全量逐帧检查为 O(总帧数)；`--max-episodes` 抽样、逐 episode 流式读取、h5py 分块访问控制内存；P1 补齐基准测试（大文件时长）。
5. **检查项语义漂移**：`check_id` 是 CI gate 的稳定 API，重命名/改动语义需报告版本化（`schema_version`）与 changelog。
6. **是否需要在生成循环内做运行时检查**（发现即早停、归因更快）：与本文的后验检查互补；如要做，建议另立设计，复用 `DataGenerator` 的钩子而不是混入本模块。
7. **报告落盘位置约定**：`--json-report` 由调用方指定；`run_generation.sh` 建议默认写到输出数据集旁 `*.checks.json`（P2 决策）。

---

## 十、附：改动面与文件速查

### 10.1 改动面清单

| 动作 | 对象 |
|---|---|
| 新增 | `autodata_utils/dataset_checks/**`（spec/config/runner/report/checks） |
| 新增 | `autodata_tests/utils/test_dataset_checks_*.py`、示例 `check_config.yaml` |
| 新增（P3） | `scripts/replay_check_dataset.py` |
| 修改 | `scripts/validate_dataset.py`（保留 CLI 契约，内部委托内核） |
| 修改（P2） | `skills/autodata-generate-datasets/scripts/run_generation.sh`、`skills/autodata-generate-datasets/SKILL.md` |
| 可选修改 | `autodata_tests/utils/utils.py`（e2e 断言接入检查内核，warning 不阻断） |
| 不动 | `docs/**`（人工维护）、`submodules/**`（只读）、`generate_dataset.py` 主流程、现有测试语义 |

### 10.2 速查表

| 主题 | 文件 |
|---|---|
| 现有结构校验 / CLI 契约 | `scripts/validate_dataset.py:24-119`、`161-176` |
| 现有测试夹具模式 | `autodata_tests/utils/test_validate_dataset.py:13-23` |
| e2e 数据集断言 | `autodata_tests/utils/utils.py:11-20` |
| 生成后自动校验 | `skills/autodata-generate-datasets/scripts/run_generation.sh:123-126` |
| 检查器注册表先例 | `autodata_core/algorithms.py:44-51`、`autodata_core/selection_strategy.py:34-40` |
| JSON 原子写先例 | `autodata_utils/generation_result.py:55-67` |
| 位姿工具 | `autodata_utils/pose_math.py:41`、`85` |
| 数据集字段语义（datagen_info） | `docs/pages/concepts/datastream.rst:120-143`、`autodata_core/pool.py:123-183` |
| recorder/导出模式 | `autodata_interfaces/env/isaaclab_env_interface.py:193-204`；`autodata_core/data_generator.py:601-606` |
| 重放与非确定性免责 | `docs/pages/workflows/franka_cube_stack_mimicgen/step_4_validate_dataset.rst:20-51`、`docs/pages/references/troubleshooting.rst:178-203` |
| CI 分层 | `scripts/ci/run_tests.sh:20-22`、`61-78`、`docs/pages/advanced/testing_and_ci.rst:10-28` |
