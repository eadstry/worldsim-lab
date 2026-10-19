# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Build local figures and a report from measured reset states."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('--run', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
r = json.loads((a.run / 'result.json').read_text())
data = np.load(a.run / 'samples.npz')
d = (data['positions'] - r['center_m']) * 1000
plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': '#f7f9fc'})
fig, ax = plt.subplots(1, 3, figsize=(15, 4.4), layout='constrained')
ax[0].scatter(d[:, 0], d[:, 1], c=np.arange(len(d)) % 4, cmap='viridis', s=17, alpha=.7)
ax[0].plot([-40, 40, 40, -40, -40], [-60, -60, 60, 60, -60], '--', color='#df7145')
ax[0].scatter([0], [0], marker='+', c='red', s=110, label='Randomization disabled')
ax[0].set(xlabel='X offset (mm)', ylabel='Y offset (mm)', title='256 measured reset positions', xlim=(-48, 48), ylim=(-70, 70))
ax[0].legend(fontsize=8)
for i, k in enumerate(('x', 'y'), 1):
    lo, hi = np.array(r['pose_range'][k]) * 1000
    ax[i].hist(d[:, i-1], bins=np.linspace(lo, hi, 13), density=True, color='#447caa', alpha=.85)
    ax[i].axhline(1/(hi-lo), ls='--', color='#df7145', label='Configured uniform density')
    ax[i].set(xlabel=f'{k.upper()} offset (mm)', ylabel='Density / mm', title=f'{k.upper()} marginal distribution')
    ax[i].legend(fontsize=8)
fig.suptitle('AutoData / OpenArm: real GPU reset randomization', fontsize=16)
fig.savefig(a.output / 'distribution.png', dpi=160)
fig.savefig(a.output / 'distribution.svg')
plt.close(fig)
fig, axes = plt.subplots(3, 3, figsize=(13, 10), layout='constrained')
image_arrays = []
for ax, frame in zip(axes.flat, r['frames']):
    image = np.array(Image.open(a.run / frame['overview']))
    image_arrays.append(image)
    ax.imshow(image)
    xy = (np.array(frame['position']) - r['center_m'])[:2] * 1000
    ax.set_title(f"{frame['file']}  |  dx={xy[0]:+.1f}, dy={xy[1]:+.1f} mm", fontsize=9)
    ax.axis('off')
fig.suptitle('Actual GPU RGB: fixed diagnostic view, one control step after reset', fontsize=14)
fig.savefig(a.output / 'renders.png', dpi=140)
plt.close(fig)
pixel_differences = [float(np.mean(np.abs(x.astype(float)-image_arrays[0].astype(float)))) for x in image_arrays[1:]]
r['rgb_mean_absolute_differences_from_first'] = pixel_differences
for filename in ('samples.npz', 'result.json'):
    shutil.copy2(a.run / filename, a.output / filename)
(a.output / 'image-check.json').write_text(json.dumps({'mean_absolute_pixel_differences': pixel_differences}, indent=2))
for f in r['frames']:
    shutil.copy2(a.run / f['file'], a.output / f['file'])
    shutil.copy2(a.run / f['overview'], a.output / f['overview'])
labels = {'finite_poses': '位姿数值有限', 'configured_bounds': 'XY 均在配置范围内',
          'xy_changes': 'XY 实际发生变化', 'z_fixed': '高度保持固定', 'orientation_fixed': '朝向保持固定',
          'same_seed_reproduces': '相同种子复现', 'different_seed_changes': '不同种子产生不同样本',
          'disabled_randomization_fixed': '关闭随机化后位置固定', 'physics_steps_finite': '12 步物理运行数值有限'}
rows = '\n'.join(f"| {labels[k]} | {'通过' if v else '失败'} |" for k, v in r['checks'].items())
text = f'''# AutoData 域随机化实测

2026-10-16，RTX 5090，现有 autodata 环境。测试对象为已准备的 OpenArm 左臂拾放任务，4 个并行环境 × 64 次 reset，共 256 个位姿样本。结果：**{r['status']}**。

当前启用的是物体 XY 初始位置随机化：相对默认中心 x ±40 mm、y ±60 mm。默认中心为 {r['center_m']} m；高度、朝向、光照、相机、纹理、材质、质量和摩擦系数未配置随机化。本结果不覆盖其他 AutoData 任务。

| 检查 | 结果 |
| --- | --- |
{rows}

同种子比较包含 8 次连续 reset × 4 环境的 XYZ 和四元数，最大误差 {r['same_seed_max_error']:.3g}。固定位置对照同样采集 32 个样本。统计采样均在 reset 后、额外物理步之前；前九次 reset 在采样后额外执行一步以同步渲染；最后单独执行 12 步零动作物理测试。

![实测位置与边际分布](distribution.png)

虚线框是配置边界，颜色表示环境编号；红色十字是关闭随机化后的默认中心。直方图虚线表示配置的均匀分布密度，仅作视觉比较，未进行均匀性显著性检验。

![真实相机渲染](renders.png)

九张图来自环境 0 的独立 reset 后一步，标注偏移来自取图时的物理状态。为避免原相机中手臂遮挡，诊断视角固定在环境坐标 (0.85, 0.65, 1.80) m，朝向 (0.53, 0.12, 1.06) m；该视角仅用于展示，不是原数据集相机。原相机图 reset-*.png 与诊断图 overview-*.png 均保留。诊断图相对第一张的平均绝对像素差为 {pixel_differences}。像素差包含渲染噪声，不能单独证明位姿正确。

本次验证 reset 事件、种子行为、短程物理步和相机渲染；没有运行 cuRobo 轨迹生成，没有评估抓取成功率、训练收益或 sim-to-real 效果。相同种子复现只适用于本次进程和环境配置。

初次启动因未设置生产启动器的 CUDA 库路径失败；修正进程环境后重跑。随后发现仅 reset/render 的图像未更新，v001 的拼图不能用于说明随机化视觉效果；v002 在取图前执行一步同步，另增加固定诊断视角。历史版本保留。最终运行目录：{a.run}；日志在其父目录 console-r04.log。没有修改上游代码或 conda 依赖。

复现命令（需已有准备目录、GPU 和 autodata 环境；输出目录必须不存在）：

```bash
bash workspace-overlays/autodata-domain-randomization/run.sh --output runs/domain-randomization-NEW
MPLCONFIGDIR=/tmp/autodata-dr-mpl /home/tangyuan/miniconda3/envs/autodata/bin/python workspace-overlays/autodata-domain-randomization/report.py --run runs/domain-randomization-NEW --output outputs/autodata-domain-randomization/vNEW
```
'''
(a.output / 'report.md').write_text(text)
checks_html = ''.join(f'<tr><td>{labels[k]}</td><td>{"通过" if v else "失败"}</td></tr>' for k,v in r['checks'].items())
(a.output / 'index.html').write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>AutoData 域随机化实测</title><style>body{{max-width:1100px;margin:40px auto;padding:0 24px;font:17px/1.7 system-ui;color:#182a40;background:#f7f9fc}}img{{width:100%;border-radius:12px}}table{{border-collapse:collapse}}td{{padding:6px 30px;border-bottom:1px solid #ddd}}a{{color:#246caa}}</style><h1>AutoData 域随机化实测</h1><p>2026-10-16 · RTX 5090 · OpenArm 左臂 · 4 环境 · 256 次位姿采样 · {r['status']}</p><p>启用物体 XY 位置随机化：X ±40 mm，Y ±60 mm。高度、朝向及外观参数保持固定。</p><table>{checks_html}</table><h2>位置分布与固定位置对照</h2><img src="distribution.png"><p>虚线为配置边界和均匀分布参考；未进行均匀性显著性检验。</p><h2>真实 reset 渲染</h2><img src="renders.png"><p>图中为环境 0 的固定诊断视角，reset 后一步取图；标签是取图时物理状态的偏移。原相机图另存。</p><p>范围：reset 随机化、种子复现、12 步物理与 RGB 渲染。未评估轨迹生成成功率、训练收益或泛化。</p><p><a href="report.md">完整报告与复现命令</a> · <a href="result.json">结果 JSON</a> · <a href="samples.npz">原始位姿数组</a></p></html>''')
now = datetime.now().astimezone().isoformat()
manifest = {'schema_version': 1, 'artifact_id': 'autodata-domain-randomization', 'version': a.output.name,
            'created_at': now, 'sealed_at': now, 'sources': [str(a.run.resolve())],
            'files': {str(f.relative_to(a.output)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in sorted(a.output.rglob('*')) if f.is_file()},
            'validation': r['checks'], 'delivery': {'local': {'status': 'saved'}}}
(a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'result': r['status'], 'output': str(a.output), 'pixel_differences': pixel_differences}))
