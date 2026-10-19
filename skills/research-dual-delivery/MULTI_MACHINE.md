# 本机与服务器统一研究交付规范

规范版本：1.0.0。共享 Skill 与成果格式，机器配置与登录状态各自保存。

## 安装

将整个 `research-dual-delivery` 目录复制到目标机器，运行：

```sh
python3 research-dual-delivery/install.py --machine A800-001
```

安装位置按 `--codex-home`、`CODEX_HOME`、`~/.codex` 的顺序解析，不依赖 macOS 或 Linux 的用户名与绝对路径。已有同名但内容不同的 Skill 会备份后更新；全局 AGENTS.md 只维护带标记的本流程段落。重复安装不重复添加规则。安装后在新会话中发现 Skill；当前会话可直接读取安装的 SKILL.md。

机器配置：`<Codex配置目录>/research-dual-delivery.json`。设置 `feishu.target` 为目标文件夹/文档，`gpt.target` 为目标 ChatGPT 对话或 Project；`resource_roots` 保存本机或服务器的数据根目录映射。配置不写令牌、不随成果包上传。留空的目标会被记录为待配置，不会随机上传。

## 生成与交付

```sh
python3 <Skill目录>/scripts/package.py init outputs/lingyu-review/v001 --artifact-id lingyu-review --version v001
# 编写 report.md；按需要加入 index.html、data.json 和 assets/
python3 <Skill目录>/scripts/package.py seal outputs/lingyu-review/v001
python3 <Skill目录>/scripts/package.py verify outputs/lingyu-review/v001
```

报告包含结论、证据、未解决问题。更新内容使用 v002 等新目录；上传状态可以继续更新原版 manifest.json。清单自带文件哈希，清单本身不纳入内容哈希，以便记录交付回执。哈希用于一致性检查，不提供签名认证。

从服务器接到本机时，完整复制版本目录并执行 verify。同步的是成果和交付清单；复制文件不会自动上传到飞书或 ChatGPT。上传前检查清单回执，两端分别续传。两台机器不要同时写同一版本的交付清单，明确一次交付由一台机器负责。

HTML 应使用相对资源路径；云空间是否能播放视频、保存标注或执行交互需要实测。审阅标注应导出独立文件并重新加载验证。大视频、MCAP、训练集默认保留原存储，只按实际需求提供预览和标注数据。

## 验收与范围

本地成果包通过 verify 表示内容一致；飞书 uploaded/verified 与 GPT uploaded/verified 必须有各自实际操作证据。无目标、无登录或无上传能力时保留明确状态，包仍可交付下载。ChatGPT 上传不能用 OpenAI API Files 上传替代。

默认适用：复现方案、论文阅读成果、数据审阅报告、实验比较和周报。简短聊天与中间文件不强制打包。不会因安装而创建定时任务、发送群消息、开放外部权限或搬运全部原始数据。新机器还需要安装实际使用的连接器/CLI 并独立登录。
