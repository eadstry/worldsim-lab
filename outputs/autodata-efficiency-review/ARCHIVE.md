# 已归档版本：v001–v021

- 归档日期：2026-10-20
- 归档 tag：`archive/autodata-efficiency-review-v001-v021`
- 保留在主树的版本：`v022`

## 为什么移出

该 artifact 的 22 个版本占 **214.3 MB / 1565 个文件**，其中 v001–v021 合计 199.3 MB。
22 个版本各自重复提交整套 PNG + SVG 图表（63 个路径在 8–17 个版本中重复出现，合计 103.9 MB），
使仓库检出体积从约 6 MB 涨到 237 MB。版本内容本身没有丢失，仍可通过 tag 完整取回。

## 恢复方法

```bash
git fetch --tags
# 查看全部归档内容
git ls-tree -r --name-only archive/autodata-efficiency-review-v001-v021 -- outputs/autodata-efficiency-review
# 取回某个版本
git checkout archive/autodata-efficiency-review-v001-v021 -- outputs/autodata-efficiency-review/v015
```

## 校验

每个版本目录内的 `manifest.json` 与 `checksums.json` 保持归档时的内容未改动，
SHA256 可直接用于校验取回的文件。

## 后续约定

新版本继续按 `outputs/<artifact-id>/vNNN/` 新增；不再重复保留同一批图表的位图与矢量两份副本。
确需再次移出旧版本时，沿用本文件的做法：先打 `archive/` tag，再更新本文件。
