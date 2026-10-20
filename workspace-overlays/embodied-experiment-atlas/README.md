# 实验图谱站点源码

从独立本地 Git 仓库提交 `9e727dd` 保存构建脚本、报告、图片和静态页面；原快照位于同步提交 `e730970`，原始逐文件来源与 SHA256 见 `docs/github-sync-20261020.json`。原工作目录保留。

集成到主分支时，将报告内依赖旧工作树的相对引用改为经过 Git 对象存在性核对的固定提交链接，并使用已有 markdown-it-py 环境重新构建 dist。迁移后的哈希登记在同一 JSON 的 `integration_adaptations`；原始哈希仍表示同步快照。

本目录不含托管配置。构建命令为 `python workspace-overlays/embodied-experiment-atlas/build_page.py`，依赖已有 markdown-it-py。本次仅本地构建并验证链接，没有执行网站部署或在线运行验证。
