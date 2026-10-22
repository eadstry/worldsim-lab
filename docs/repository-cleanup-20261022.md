# 仓库整合与文档位置

创建日期：2026-10-22。

## 合并范围

开始时 main 为 `2868f7c`，没有打开的 PR，远端有 34 个任务分支。来源 HEAD 逐项保存在[分支清单](integration/branches-20261022.json)。整合保留这些来源提交的父历史，当前树合入独有源码和文档；旧实验附件留在原提交中，不重复导入当前目录。可用 `git show <清单中的SHA>:<原路径>` 读取文本，或用 `git archive <SHA> <原路径>` 导出附件。

纳入的独有实现包括 Arena 域随机化、AutoData 场景执行、Franka/香蕉演示、并行环境调度、HDR 背景、生产容量、LeRobot v3 转换与语义元数据、关节目标记录、多机器人生成、面试媒体工具及 OpenArm 误差分析。已进入 main 的内容保留较新的实现和审查策略；不回退上游子模块 pin、封存成果或当前配置。新增功能只做主机测试，不在本次运行 GPU、训练或实机。

## 文档固定目录

所有新增文档、报告和阅读材料放到 `docs/`，主题目录保存正文及配图，入口为 [docs/README.md](README.md)。既有封存成果保留在 `outputs/<artifact-id>/vNNN/`。

- 博客文章迁到 [AutoData 主题目录](autodata/README.md)，保留 Markdown、11 张 SVG、离线 HTML 和样式。
- 实验图谱正文和配图迁到 [作品集资料](experiment-portfolio/README.md)。
- 根目录报告改写计划迁到 `docs/report-rewrite-plan-20261019.md`。
- 删除 `private-blog/` 和 `workspace-overlays/embodied-experiment-atlas/` 的站点构建脚本、首页、生成副本、npm 依赖及部署说明。初始化、主机检查和 CI 均移除博客构建依赖。
- 此次清理仓库文件，不操作外部 Sites 托管账号；历史封存交付物保持原字节。

## Releases 与归档

原 3 个 Release 的全部 9 个附件先下载到本次 Codex 输出目录的 `release-backup/<原tag>/`，以 `releases.json`、文件大小和 SHA-256 清单核对后删除 GitHub Release。归档文件不重新上传到仓库，原 tag 保留作为历史定位点。

本地备份根目录：`/Users/jiax/Documents/Codex/2026-10-22/github-plugin-github-openai-curated-remote/outputs/release-backup/`。换机前须另行复制该目录；删除 Release 后 Git 克隆不能取回这些附件。

| 原 tag | 附件 |
| --- | --- |
| `archive-branches-20261020` | `worldsim-lab-archive-20261020.bundle`、两个历史工作树 ZIP |
| `archive-autodata-review-20261020` | `autodata-review-v001-v021.zip` |
| `archive-server-shutdown-20261022` | 本地历史 bundle、工作树补丁归档、文件清单、恢复脚本、归档计划 |

服务器停服归档只包含当时实际发布的 5 个附件；不包含 77 GB 实验数据的完整备份，不将文件清单视为数据本体。旧恢复说明保留为历史记录，并标出当前入口。

## 审查与验证

审查源码合并后的错误处理、接口和路径，检查文档与资源迁移、上游 pin 和封存成果不变、部署依赖移除及归档可追溯性。主机检查以本次提交的审查回执和 PR 的 `host-review` 结果为准；未重新验证 GPU 吞吐、仿真物理或实机行为。

已执行的主机验证：Linux 基础工具/队列/审查测试 42 项、共享配置 8 项、生产扩展 41 项、生产容量 20 项、多机器人 4 项、误差分析 7 项、OpenPI 服务 4 项全部通过。另有本机 LeRobot 转换测试 6 项通过，官方加载器读回数值与维度并解码全部视频帧；本机 TorchCodec 受 Homebrew FFmpeg 缺失动态库影响，回读验证显式使用官方 PyAV 后端，未将默认 TorchCodec 路径记为通过。转换器保留 H.264，并兼容两种编码配置/图像写入器 API；可选依赖缺少安装元数据时记录 null。

历史分支对默认参数、版本策略或已更新实现的覆盖，以当前 main 的策略与参数为准；独有旧实验变体和附件可由来源 SHA 查阅。源码整合不是重新执行历史实验。
