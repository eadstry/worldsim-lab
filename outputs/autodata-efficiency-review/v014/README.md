# v014 协作交接

本版从 v013 的 43 页扩展到 51 页，新增内容位于第 29–36 页。历史 8 环境与新插桩 4 环境结果分开；v013 的封存内容没有修改。

- 阅读入口：[charts.pdf](charts.pdf)、[charts.html](charts.html)、[加速分析](acceleration-analysis.html)。
- 新数据与计时脚本在 paired4/，完整动作匹配与严格终态均通过。
- 优先实验：A0 现有 auto、A1 仅相机位姿刷新去重、A2 仅同状态 RGB 副本复用、A3 两项组合。尚未实施这些缓存优化。
- 保留两次 observation.compute 与历史更新语义；reset、事件及相机状态变化时缓存失效，所有缓冲有界。
- 本地 TiledCamera 是 Camera 的弃用别名；仅换类名不能产生新的批量渲染能力。
- 21.1% 和 22.6% 是条件情景下 execute 时间减少，不能当作实测加速或最终文件吞吐承诺。
- 本版沿用 local_only 交付策略。继续编辑应新增版本，不改写封存文件。

重建需要已安装的 matplotlib、numpy、markdown 与 WenQuanYi Micro Hei 字体；在新目录副本中运行 build_figures.py，再运行各 build_*_report.py 与 build_charts.py。没有安装或升级运行依赖。
