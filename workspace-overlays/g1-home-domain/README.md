# G1 家庭场景域随机化对照生产

在已经验证的静态家庭场景中比较域随机化对生产可行性与图像的影响。
本批采用 Mimic 和状态反馈的 G1 全身控制器；RGB 不参与本次动作决策，
因此成功标签衡量数据生成任务完成，不能作为视觉策略泛化、训练收益或真实机器人迁移的结论。

## 对照设计

每个配置运行一段新轨迹，独立进程、独立 HDF5，50 Hz；保留失败结果，不自动重试直到成功。
第三视角与整屋诊断相机固定。真正用于观察的机器人头部相机随 camera 配置扰动。
场景、源示范和运行依赖沿用 `g1-home-scene` / `g1-data-visual`，原始家庭 USDZ 不修改。

| 配置 | 生成 seed / DR seed | 开启内容 |
| --- | --- | --- |
| baseline | 1 / 100 | 原有箱子 XY ±2.5 cm；其余固定 |
| lighting | 1 / 101 | 室内 HDR、光强、色温、HDR 朝向 |
| camera | 1 / 102 | 头部相机外参和焦距 |
| material | 1 / 103 | 客厅地板和墙的颜色、粗糙度 |
| visual_only | 1 / 104 | 光照、相机、材质；箱子沿用基线位姿范围 |
| combined_s1 | 1 / 104 | 光照、相机、材质、箱子 XY ±3.5 cm / yaw ±3° |
| combined_s2 | 2 / 105 | 同上，独立采样 |
| pose_wide | 1 / 106 | 箱子 XY ±8 cm / yaw ±10°；其余同 baseline |

单因素采用同一生成 seed，便于比较。组合组同时改变多个因素，不能用于分离每一项的贡献。
每个单因素只有一个样本，不能从 1/1 或 0/1 推断总体成功率。

## 完整采样范围

所有 U(a,b) 由专用 Python Random(DR seed) 均匀采样，一段轨迹中固定，不逐帧闪变。
箱子位姿由环境 reset 使用生成 seed 采样，其余参数不会消耗该随机数流。

| 参数 | 范围与约定 |
| --- | --- |
| HDR | 本机已有 `photo_studio_01_4k.hdr`；单一室内 HDR，朝向 U(0,360)° |
| 穹顶光强 | U(650,1100)，USD intensity |
| 面光强度 | U(700,1300)，USD intensity |
| 面光色温 | U(4000,6500) K |
| 相机安装平移 | head_link 父坐标系中 XYZ 各 U(-0.005,+0.005) m |
| 相机安装旋转 | 在名义 ROS 光学姿态右侧组合 XYZ 各 U(-2,+2)° 的增量四元数 |
| 头部焦距 | 15 mm × U(0.95,1.05)，fx/fy 一起变化，保持像素纵横比 |
| 地板 base color | g~U(0.35,0.65)，线性 RGB=(1.02g,g,0.96g) |
| 墙 base color | w~U(0.65,0.85)，线性 RGB=(w,0.98w,0.94w) |
| 地板 / 墙粗糙度 | 分别 U(0.45,0.9)、U(0.6,0.95)；metallic=0 |
| 箱子 XY | 名义 (0.5785,0.18) m，按各组给出的半范围独立采样 |
| 箱子 yaw | 名义 π rad，按各组给出的角度半范围采样；roll=π，pitch=0 |
| 箱子 Z | 固定 0.0707 m |

光强不是经校准的照度 lux。材质组用平滑 PBR 替代指定地板与墙面的外观，
不会改变碰撞与物理材质，也不宣称覆盖了真实纹理多样性。箱子、蓝筐和机器人颜色语义保留。

保持质量门槛不变：官方顺序成功条件、末端 100 步物理保持；success 会锁存，
不要求连续稳定两秒。质量检查还记录末尾箱子速度、动作有限性、RGB 暗区/高光占比和完整视频帧数。
住宅家具保持静态、天花板不可见；本批不测试家具关节交互，也不更改质量、摩擦、控制增益或动作延迟。

## 准备、队列执行与分析

必须复用已配置 Arena HEAD `98866596fd024d96c874fe6fb95ae916d1133629` 及其现有本地兼容修改。
不安装仿真依赖、不更新上游、不重写已有数据。

```bash
"$ARENA_ROOT/.venv/bin/python" workspace-overlays/g1-home-domain/prepare_batch.py \
  --base-layer /absolute/path/to/prepared/home-g1.usda \
  --hdr /absolute/path/to/photo_studio_01_4k.hdr --output runs/domain-plans

python3 scripts/task-queue.py submit --name g1-dr-lighting --timeout 600 -- \
  env G1_SEED=1 G1_DR_PLAN="$PWD/runs/domain-plans/lighting/plan.json" \
  bash workspace-overlays/g1-home-domain/run.sh \
  --input_file /absolute/path/to/arena_g1_loco_manipulation_dataset_annotated.hdf5 \
  --output_file runs/domain/lighting/episodes.hdf5

"$ARENA_ROOT/.venv/bin/python" -m unittest discover \
  -s workspace-overlays/g1-home-domain -p 'test_*.py' -v

"$ARENA_ROOT/.venv/bin/python" workspace-overlays/g1-home-domain/analyze.py \
  --plans runs/domain-plans/plans.json --runs runs/domain --output runs/domain-analysis
```

设置 `ARENA_ROOT`、`ISAACSIM_ASSET_ROOT`，按既有许可设置启动环境。
每个 plan 固定 scene/base layer/HDR 哈希，并在仿真开始时回读实际光强、HDR 和相机内参。
运行目录内的 dr-resolved.json 保存完整相机配置和 reset 位姿范围，dr-readback.json 保存仿真回读值。
所有生成数据、资产和视频均仅本地保存，不提交 Git。

分析导出每段完整第三视角视频，另为基线、相机、组合与大位姿组导出完整头部视角视频；
解码帧数必须与 HDF5 相同。固定第 400 控制步计算相对基线的 RGB MAE，
并保存首、中、末帧及对照图；位姿不同的组里，这个差值同时包含几何与外观变化。
亮度指标只用于识别黑图和大面积过曝，不能衡量语义可见性或学习效果。

## 依据与边界

源示范与任务结构遵循官方 G1 Mimic 的物体相对轨迹处理：
<https://isaac-sim.github.io/IsaacLab/v3.0.0-beta/source/overview/imitation-learning/humanoids_imitation.html>。
本批只改变当前任务可解释的有限参数，不测试移动蓝筐、改变桌高、家具重排或整屋随机替换。
这些变动会影响固定导航路线、可达性和物体接触，需要单独重新验证。

## 头部视觉目标的预检

用户确认目标为头部视觉模仿学习与场景泛化。检查上一批成功轨迹的头部第 0、300、600、927 帧，
可见抓取与放置目标；搬运阶段箱子上缘本来就存在裁切。因此相机扰动应保持小幅，并检查
手部接触区和放置目标的可见性，不能仅凭第三视角好看来筛选。
本批只改变同一住宅内的外观与有限位姿，不等于已经覆盖新户型和家具布局的泛化。

## 物理材质绑定修复与补测

初版视觉材质覆盖了原来的 all-purpose 绑定，而原材质同时带有 PhysicsMaterialAPI，
导致原地板静摩擦 0.58、动摩擦 0.48、恢复系数 0.13 回落到引擎默认值。
仅检查碰撞体数量不足以发现这个问题。旧材质与旧组合组样本保留在 domain-r02，作为有混杂因素的诊断数据，
不用于推荐材质随机化效果；旧 combined_s1 发生倒伏且 success=False，也不能归因于箱子位姿。

修复在覆盖外观前，为几何 prim 和子集显式保留原 physics purpose 材质绑定，
随后验证原物理材质仍然解析到同一路径。回归测试同时检查摩擦与恢复系数，
防止仅验证图像变色而遗漏接触动力学变化。原 USDZ 不修改，旧运行与旧参数文件均保留。

补测 material、visual_only、combined_s1、combined_s2；visual_only 与 combined_s1 使用完全相同的
光照、相机和材质采样，前者沿用原箱子 XY ±2.5 cm、固定 yaw，后者增加 XY ±3.5 cm / yaw ±3°，
用于区分视觉变化与位姿扰动的影响。
正式分析使用这四条补测和已有 baseline、lighting、camera 共七条。大位姿组为额外诊断，
不要求它进入头部视觉训练候选集。prepare_batch.py 提供八个候选配置，按需选择。

## 2026-10-17 正式生产结果与推荐

在恢复原物理材质后，完成七段正式轨迹，六段 success=True、一段 False，全部动作有限。
每段第三视角视频完整解码核验；含相机扰动的组合额外提供完整头部视频。
原始 HDF5、参数、回读、视频、逐项统计与训练候选清单位于本工作树 `runs/final-review/`；
原始数据通过 `runs/domain-r03/` 索引，重复基线引用已有独立输出，不重写旧数据。

| 配置 | 成功/尝试 | 帧数 | 时长 | 同步头部 RGB MAE / 255 |
| --- | ---: | ---: | ---: | ---: |
| baseline | 1/1 | 928 | 18.56 s | 0.00 |
| lighting | 1/1 | 928 | 18.56 s | 12.64 |
| camera | 1/1 | 928 | 18.56 s | 9.36 |
| material（物理绑定修复后） | 1/1 | 928 | 18.56 s | 2.69 |
| visual_only | 1/1 | 928 | 18.56 s | 36.14 |
| combined_s1 | 0/1 | 843 | 16.86 s | 38.27 |
| combined_s2 | 1/1 | 904 | 18.08 s | 54.25 |

MAE 在第 400 控制步比较，不是学习效果评分；位姿组同时存在运动差异，不能与纯外观组直接排名。
单因素与 visual_only 的动作相对基线最大绝对差均为 0，说明本批视觉变化没有混入动作变化。
material 修复后帧数和动作都恢复到基线；旧有混杂样本继续保留作工程诊断。

对头部视觉模仿学习，推荐 **visual_only** 作为下一批的生产起点：组合室内 HDR/光照、
小幅头部相机误差、墙地视觉材质；箱子仍沿用 XY ±2.5 cm、固定 yaw，保留箱子和蓝筐颜色语义，
不改变质量、摩擦或控制器。完整候选范围见上表，实际本次采样参数保存在 plan.json；
范围边界未被穷举验证。材质单因素的头部像素变化较小，光照和相机是优先的多样性来源。

小位姿组合两段仅一段成功，失败段发生倒伏、箱子未正确入筐，完整数据与视频不剔除。
这支持暂不把增加位姿范围/yaw 作为默认；还不能分离 XY 与 yaw 各自的影响，也不能估计总体成功率。
训练候选清单只列出六段实际成功且动作有限的样本，未把失败重标成成功。

共享队列曾把剩余任务转入并行容量测试；物理绑定修复补测三段由共享批次 83 完成，
visual_only 的第五并发实例在初始化阶段未产生数据，随后用独立任务 87 正常完成。
初始化恢复不属于对任务失败重采样。修复前 GPU 结果、原队列取消/迁移记录与资源测试均保留，
不将它们混进正式七段的成功分母。仿真完成后的图像统计和转码限制 CPU/编码线程，不占用 GPU。

自审核对了物理与视觉材质分离、单段随机化范围、源数据/场景不可变性、失败保留、
并行初始化恢复与真实任务失败的区别、完整视频帧数及头部画面。三项主机回归测试通过；
完整工作区检查随最终提交执行。数据生产可行性不代表视觉策略训练收益或真实场景泛化已验证。
