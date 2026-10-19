# 固定尝试预算的数据生产能力实验

承接 OpenArm 同步/异步导出与内部耗时实验，比较 1/4 环境 × 同步/固定 2 进程/auto，主指标为独立验收合格条数除以首条开始至最终文件就绪的墙钟时间。包括排空、合并、关闭；初始化和校验另列。不把主机计时解释为隔离 GPU kernel 时间。

## 固定计划

- 试运行：1 环境，同步与固定 2 进程各 1 次，seed=101。任一失败则不进入筛选。
- 筛选：每配置 seeds=101/202，每批恰好 4 次尝试，共 48 次。第二轮反转导出配置顺序。
- 确认：筛选中同并行度内，产能提高且成功数未降低的候选中选择观测合格吞吐最高者，与其同步基线比较。seeds=303/404/505，每批 4 次，共最多 24 次。无候选则跳过。
- 共最多 74 次，禁止失败补成功、自动重试和自动扩大配置。运行异常停止余下批次。此数量是小批筛选/确认，不证明长期稳态或统计非劣性。

固定任务、输入、末尾 60 步保持、三路 640×480 原控制频率 RGB、gzip level 2；审阅视频另行从左腕图像生成 320×240、15 fps、H.264 CRF28，无音轨。右腕在原任务中可能黑屏，结构有效不代表视角有用。沿用已记录的 30 Hz 源频率。视频编码不参与产能时间窗口。

`launch.py` 只在子进程内转换源码，检查唯一边界，不修改 AutoData 或 Python 环境。每环境固定配额，完成后提供零相对位移和保持夹爪的 idle 动作，让未完成环境继续；idle 不新开尝试，严格核对遥测 starts/finished/attempts。同步和异步均使用 CPU 帧独立存储，导出前应用原 OpenArm 严格终态谓词。

任务描述符设置 `guarantee_success=false, keep_failed=true`，因此与历史“成功目标、丢弃失败”的工作量不同；只在本轮相同记录设置下解释提速。规划失败可能在记录器导出前返回，保留遥测和分母，缺失失败轨迹单列，不伪造物理数据。完整读回所有已导出数组，检查有限数、图像结构、成功计数和记录终态，保存每数组哈希及完整文件 SHA256。终态校验不是独立物理回放，也不是连续稳定性证明。

## 运行条件与保存

用户新增 `/data` 存储额度约 700 GB，已验证 `/data/WorldSimReady-Home` 可写。数据、日志、视频和最终归档都保存到此目录下全新实验目录，保留至少 70 GiB 文件系统余量，并在打包前保留额外一份 payload 的空间。Ceph 文件系统显示容量不等于个人额度，运行前需核对本轮总量与实际额度，不能以共享池容量推断个人剩余额度。

每批开始拒绝其他 GPU compute 进程；仅使用既有配置环境。内存预检沿用保守估计 `12 + envs×4.5 + async_queue16 + reserve8 GiB`，运行中 effective available <8 GiB、producer RSS>44 GiB、磁盘低于保留值、OOM 或2400秒超时时停止。归档和全部校验在同一共享队列任务内前台执行。打包不包含队列环境快照、凭据或安装环境，不自动删除数据。

准备目录及源文件在工作树内独立复制/固定；AutoData 的只读共享源码在每批前后校验哈希，发现变化停止，禁止更新上游 pins。提交后保持此工作树代码不变。

参数均为显式路径；`run.py --help` 不加载仿真。通过 `scripts/task-queue.py submit --timeout 54000 --cwd <冻结工作树> -- <现有autodata Python> -u workspace-overlays/production-capacity/run.py --directory <全新/data目录> --production-root <production覆盖层> --gate-root <openarm-throughput-benchmark目录> --autodata-root <现有AutoData源码> --input <固定源示范> --task <原任务YAML>` 提交。

本机访问 `/data`、驱动、队列状态和 Git 元数据可能需要沙箱外授权。缺依赖时停止，不安装。入口不支持 resume；新任务不能沿用已存在输出路径。

主机检查：`<现有autodata Python> -B -m unittest discover -s workspace-overlays/production-capacity -v`。覆盖并行有限配额/idle、边界变更拒绝、无效预算、终态检查、坏标签、NaN、计数不一致和失败记录保留。通过不代表 GPU 仿真通过。

完成后生成 `report.json`、逐批 `cell.json`/`validation.json`、数据及日志、视频、文件哈希和 `.tar.gz` 及其校验回执。夸克上传已获用户授权，但目标文件夹与认证上传入口未提供，归档回执如实标为 pending；不声明已上传。
