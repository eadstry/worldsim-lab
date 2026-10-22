# 实验图册清晰度修订

创建日期：2026-10-22。实验材料仍截至 2026-10-20，本次没有新增仿真、训练或轨迹数据。

上一版总览将 19 张图压到 1440×1785 像素，各缩略图只有约 480 像素宽。前 14 张图虽然原始 PNG 标记为 180 dpi，但生成 PDF 时再次栅格化为约 100 ppi 的页面内图片，文字也随整图缩小。因此总览和 PDF 放大后都显得模糊。

本次从 v001 封存的小型 JSON 记录重绘全部 19 张图，没有放大旧 PNG。新版本提供：

- [离线图册](../../outputs/experiment-chartbook/v002/index.html)：逐图展示 SVG，点击可打开矢量原图。
- [矢量 PDF](../../outputs/experiment-chartbook/v002/experiment-chartbook.pdf)：20 页，目录加 19 张图，每页一张。
- 各图 300 dpi PNG，3507×2481 像素；标题 24 pt、坐标标签 14 pt、刻度和页脚通常 12 pt。
- [指标 CSV](../../outputs/experiment-chartbook/v002/metrics.csv)、原始证据与 SHA256 清单，方便核对。

图号与实验主题沿用 v001。随机化图展示配置边界和实测标准差，力传感图展示已保存的中位数与峰值，Franka 图展示配对条件的成功计数；没有从汇总数据补造完整散点、力曲线或运动轨迹。产能图展示三个确认 seed，并在图注说明完整的 74 次预算。其他完整记录仍随包保留。

生成入口为 `workspace-overlays/experiment-chartbook/build_sharp.py`，依赖既有的 matplotlib、numpy、Pillow、文泉驿字体和 Poppler 命令。输入首先通过 v001 manifest 全文件校验，输出使用新版本目录，不改写 v001。可复现命令：

```bash
python workspace-overlays/experiment-chartbook/build_sharp.py \
  --source-bundle outputs/experiment-chartbook/v001 \
  --output outputs/experiment-chartbook/vNNN
```

[导出验证](../../outputs/experiment-chartbook/v002/validation.json)确认：19 个 SVG 没有嵌入栅格图、PDF 没有位图对象、20 页、中文文本可提取且无字体警告、所有 PNG 满足 300 dpi、标题和注释未超出画布、指标 CSV 与 v001 字节一致。并检查离线页面本地链接、已封存版本完整性及仓库主机检查。以上属于图表导出和来源验证，不是新实验验证。

自审：检查了数据归属、冻结证据、任务成功与导出完成的不同口径、并行环境数与样本数、GPU 均值与峰值、保守内存模型的范围。所有图表来源于已有记录；未修改上游、运行中的代码或历史封存文件。自动检查及本次自审不属于独立审稿批准。

新版另在本机 `/data/WorldSimReady-Home/experiment-chartbook-20261022-v002.zip` 打包，只包含图册和小型证据。夸克上传仍需既有上传通道和目标目录；本次没有收到上传成功回执，不标记为已上传。
