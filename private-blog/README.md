# eadstry · 个人博客

分享具身智能方向的项目实践、技术文章与学习记录，包含「开源贡献」和「具身学习」栏目。

## AutoData 文章维护

- `content/autodata/AutoData-全流程可视化讲解.md`：文章唯一正文来源。标题、正文、代码和普通表格使用 Markdown；复杂表格与 CSS 流程图保留必要的 HTML。
- `content/autodata/figures/`：11 张独立 SVG，包含自身字体样式。文章使用相对路径引用。
- `content/autodata/article.css` 与 `template.html`：沿用文章的配色、卡片、导航与分栏设计。
- `content/autodata/anchors.json`：13 个章节的既有锚点。新增或调整章节时同步更新，避免旧链接失效。
- `backups/autodata-before-markdown.html`：转换前的完整 HTML 备份。

```sh
npm ci
npm run build
npm run check
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

`npm run build` 从 Markdown 生成 `dist/embodied/autodata/` 中的网页、MD 副本、SVG、样式和完整下载包。请勿直接修改生成的正文 HTML。首页仍在 `dist/index.html`，其资源在 `dist/assets/`。

## Markdown 扩展

构建使用 markdown-it、markdown-it-container、markdown-it-anchor 与 highlight.js；浏览器不需要加载这些依赖。

卡片和提示示例：

```md
:::: card

## 章节标题

正文使用 **Markdown**。

::: callout blue

蓝色说明卡片。

:::

::::
```

可用容器：`card`、`grid2`、`callout`。提示色支持 `blue`、`green`、`red`；嵌套容器的外层冒号数量应多于内层。复杂布局保留的 HTML 可使用原有 CSS 类。

普通 Markdown 编辑器可阅读文字、表格及 SVG，但扩展卡片需要相应渲染支持。下载包内的 `index.html` 可直接离线打开，保留完整排版；图示目录应与 MD 保持相对位置。

## 验证

`npm run check` 核对原文、13 个章节、55 个小标题、39 张表格、20 个代码块、11 张 SVG、导航、布局及下载包完整性。转换脚本仅用于首次迁移，后续编辑 MD 时不要重新运行它。

## 托管

[eadstry · 个人博客](https://eadstry-learning-notebook.jiaxuan-li996.chatgpt.site) 使用 Sites，当前访问模式为公开。修改后构建、检查，再通过 Sites 发布到 `.openai/hosting.json` 记录的现有站点。首页的 GitHub 链接仅为个人资料外链。
