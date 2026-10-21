# G1 家庭场景接入

将 `Yootta/World-SimReady-Home-mini` 的 `scene000430.usdz` 接入已验证的
G1 Mimic 单段生成入口。扩展只维护在根工作区；不编辑上游、原始 USDZ 或既有运行结果。

## 场景版本与布局

固定 Hugging Face revision `f2c633749e7fdf3f981dfd1dd83fc253786713ac`；
USDZ SHA256 `d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6`。
场景原生单位为米、Z 向上，根 prim `/root`；原始 metadata 和预览随场景保存在本地。
许可以原数据集的 CC-BY-NC-SA-4.0 为准；本扩展不重新分发资产。

`prepare.py` 写入新的 USD 引用层，将家庭坐标平移 `(-22.4, 4.35, -0.795)` m，
让原 G1 任务处于客餐厅，地面与原任务的 `z=-0.795` m 对齐。
仅在派生层中停用餐桌及其椅子组，腾出区域；保留原任务货架和工作台，去掉实验室其余背景及电钻。
箱子、蓝筐、机器人、导航点、原始示范的坐标关系沿用已有入口。

该版本是静态家庭环境：关闭家庭资产 501 个刚体的动态仿真及 120 个关节，
保留家具、墙面和地面碰撞；不覆盖原箱子、蓝筐和 G1 的物理配置。
关闭住宅内 278 个原光源，加入穹顶灯和面光源；天花板设为不可见以便观察。
因此运行结果覆盖此派生变体，不代表原住宅家具关节交互已验证。

## 准备和生成

复用已有兼容 Isaac Sim/Arena 环境，不自动安装依赖。Arena HEAD 由启动器校验，
本机仍保留先前的运行兼容修改。`g1-data-visual` 是本分支已包含的扩展依赖。

```bash
hf download Yootta/World-SimReady-Home-mini --repo-type dataset \
  --revision f2c633749e7fdf3f981dfd1dd83fc253786713ac \
  --include 'scene/scene000430/*' README.md --local-dir runs/home-input

"$ARENA_ROOT/.venv/bin/python" workspace-overlays/g1-home-scene/prepare.py \
  --home runs/home-input/scene/scene000430/scene000430.usdz \
  --galileo "$ISAACSIM_ASSET_ROOT/Isaac/IsaacLab/Arena/assets/background_library/galileo_locomanip/galileo_locomanip.usd" \
  --output runs/prepared

python3 scripts/task-queue.py submit --name g1-home --timeout 600 -- \
  env G1_SEED=1 G1_HOME_USD="$PWD/runs/prepared/home-g1.usda" \
  bash workspace-overlays/g1-home-scene/run.sh \
  --input_file /absolute/path/arena_g1_loco_manipulation_dataset_annotated.hdf5 \
  --output_file runs/home/episodes.hdf5

"$ARENA_ROOT/.venv/bin/python" workspace-overlays/g1-data-visual/export_video.py \
  runs/home/episodes.hdf5 runs/videos/home
```

准备输出和生成输出均要求新目录或新文件，避免覆盖。准备层引用本机绝对资产路径，迁移时应重新准备，
不能单独复制 `.usda` 文件当成完整资产包。运行必须设置 `ARENA_ROOT`、`ISAACSIM_ASSET_ROOT`，
且依照已有本机许可设置启动环境；以上命令不会更新上游依赖。

## 可视化与判定

第三视角相机位于 `(-1.25, -1.4, 1.25)` m，观察 `(0, -0.65, -0.05)` m；
640×360、焦距 14 mm、水平光圈 36 mm。保留完整 50 Hz 视频序列及机器人头部相机。
额外 640×640 整屋相机在第 100、400、800 控制步保存诊断截图，不写入视频帧序列。

成功使用 `g1-data-visual` 中的官方顺序判据适配，仍为“初始静止→抬起超过 1 cm→目标上放稳”，
放置要求目标范围内的箱子中心、≥0.5 N 向上支撑力且方向位于 45° 支撑锥、速度 <0.1 m/s。
末端物理保持 100 步，不修改阈值。成功状态会锁存，不要求连续稳定两秒，也不要求整箱完全包含。

原始家庭网格在 PhysX 烘焙时存在非封闭 SDF 和部分 GPU 凸包兼容警告，本入口使用 CPU PhysX。
任务运行和图像检查不能替代全部住宅碰撞几何的验收。

## 2026-10-17 本机验证结果

最终队列任务 52 正常退出，生成一段新轨迹：928 帧、50 Hz、18.56 秒，
HDF5 `success=True`，动作全部有限，最终箱子线速度约 `0.000504 m/s`。
完整视频重新解码后确认 928 帧；检查了首、中、末帧与整屋截图。
最终数据与图像位于本工作树 `runs/home-r03/`、`runs/videos/home-r03/`，
资产哈希、准备层变更、源文件哈希及验证摘要见 `runs/summary.json`。
这些运行数据仅本地保存，不加入 Git。

此前队列任务 50 也通过物理成功判定，但照明不足导致黑画面；任务 51 补光后通过，
第三视角被货架遮挡。最终任务 52 在另一侧机位重新生成，保留全部诊断结果。
这是一次任务的场景接入验证，不把相机迭代算作多个独立随机成功样本。

静态检查确认原 USDZ 哈希未变、派生层中保留 787 个启用的住宅碰撞体、
家庭刚体动态关闭、实验室背景停用且原货架/工作台保留；Python 编译和 shell 语法检查通过。
完整工作区检查在自动提交步骤运行，范围不包含全部住宅家具交互或碰撞精度验收。

自审已检查场景坐标与单位、原始资产不可变性、静态家具物理范围、灯光和相机遮挡、
Mimic 单段输出隔离、成功标签来源和视频完整性，以及数据不进入版本库的边界。
原场景 SDF/凸包烘焙警告保留记录；执行者自审不属于独立审阅批准。
