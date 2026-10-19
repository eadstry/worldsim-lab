# AutoData 架构说明与 cuRobo 升级分析 · v022

- [项目架构 · 阅读版](architecture.html) / [Markdown](architecture.md)
- [cuRobo v1 与 v2 · 独立文章](curobo-v1-v2.html) / [Markdown](curobo-v1-v2.md)
- [完整图册 · 阅读版](charts.html) / [Markdown](charts.md)

本版以用户指定的 e476 worktree 中 v021/charts.md 为基准，重写实验前的项目架构说明，另写规划库比较文章。第 15 页及之后的正文逐字节保留，原图按文件哈希核对；验证记录见 verification.json。旧版文件未修改。

新增六张可编辑 SVG，统一配色与图文布局。HTML 提供目录、图像放大链接和打印样式，离线打开即可阅读。build_visuals.py 可重建架构图；build_html.cjs 使用根仓库已有的 markdown-it 生成阅读版。无需安装 GPU 运行依赖。

来源代码与历史 v2 提交区分记录。本版没有运行新的 GPU 实验，也没有发布博客。实验图中原有页码和说明保留，不以新文章替换历史实验记录。
