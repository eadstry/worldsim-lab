# v015 逐页详细说明

本版保留 v014 的 51 页顺序与全部实验数据，为每页补充面向首次阅读者的说明：怎么做的、这样做的意义、当前结论、读图与术语。

- [带页下注释的图册 PDF](charts.pdf)：保留原图物理尺寸，在下方扩展说明区域。
- [网页图册](charts.html)：图下直接显示说明，适配窄屏，无需展开。
- [逐页说明原文](charts-guide.md)：与 PDF 和网页使用同一份 page-explanations.json。
- [内部耗时及加速方案](acceleration-analysis.html)：详细方法和源码依据。

历史 8 环境、新增 4 环境插桩配对和 v2 跨日期运行分开解释。原始数据、质量结果和条件估算不变；没有新增 GPU 运行，也没有实施相机缓存优化。

重建顺序：使用已安装 matplotlib、numpy 的 Python 运行 build_figures.py，再运行 build_charts.py。字体使用 WenQuanYi Micro Hei。其余专题报告保留对应证据和独立重建脚本。图表 PNG/SVG 含 PDF 同款页注；chart-images/ 是网页使用的原图。

沿用 local_only 交付策略。v014 保持封存，后续修订新增版本。
