# 实验图册整理工具

从已封存的作品集 v004 复用 14 张原始 PNG，按原字节校验；另外用保存的 JSON 及单个失败末态向量绘制 5 张验收图。输出包括 19 张 PNG、5 张新增 SVG、20 页 A4 横版 PDF、本地 HTML、图表索引和 157 行主要指标/阶段数据 CSV。按主题组织，原图号保持稳定；历史原图不宣称全部为矢量图。

只整理已有证据，不启动仿真、训练或全量 HDF5 扫描，不复制大型轨迹数据。构建入口明确接收来源目录，输出目录必须不存在；原 `outputs/` 版本保持不变。`evidence/` 保存本次用到的小型原始记录及 SHA256。失败向量快照另附原始 `episode_finished` 事件，保留 4 次规划请求通过与末态未稳定的区别。

使用现有带 Matplotlib、NumPy、Pillow 的 Python。字体使用机器已有的文泉驿正黑，PDF 字体嵌入与中文提取已检查；不会安装或变更仿真依赖。

```bash
python workspace-overlays/experiment-chartbook/build.py \
  --reference-workspace /path/to/portfolio-worktree \
  --evidence /path/to/saved-portfolio-json \
  --audit /path/to/audit.json \
  --regression /path/to/closed-export-regression \
  --conversion /path/to/named-conversion/validation.json \
  --failure-state /path/to/failure-final-state.json \
  --output /new/chartbook-directory
python workspace-overlays/experiment-chartbook/verify.py /new/chartbook-directory
```

这是针对截至 2026-10-20 材料的版本化图册，不是可忽略数据变化的通用模板。构建时显式核对 v1/v2 样本归属、4 条相机记录/5453 帧、8 次回归和具备语义名称的转换回执；来源变化时需更新说明与新版本，不能沿用固定图题。

`verify.py` 检查全部 payload/来源哈希、原图字节一致性、PNG 完整性、SVG XML、HTML/Markdown 本地链接、CSV 的关键数字与有限值，以及 PDF 页数、中文文字和字体警告。任务数、后续规划请求数、视频帧数和资源快照分别标注，不把时间采样或帧当成独立任务试次。回归图不作为速度对照；资源图中的 144 GiB 是准入模型而非实测最低内存。

主机检查使用仓库要求的 `bash scripts/cloud-check.sh --allow-uninitialized`；隔离工作树有意不检出上游源码。主机检查和图表整理不代表重新验证历史 GPU 运行。图册本地交付，不发布网站或博客。
