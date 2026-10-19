# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Executed by build_figures.py with its existing style and footer helpers."""
paired = json.loads((P / 'paired4/report.json').read_text())
pb, pa = paired['runs']
ps = pa['execute_phase_mean_seconds']
pf = pa['execute_phase_fraction']
scenario = json.loads((P / 'acceleration-scenarios.json').read_text())


def timing_table(name, title, rows, headings, widths, size=12):
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.axis('off')
    ax.set_title(title, loc='left', fontsize=18, pad=22)
    table = ax.table(cellText=rows, colLabels=headings, colWidths=widths,
                     cellLoc='left', loc='center', bbox=[0, .07, 1, .84])
    table.auto_set_font_size(False)
    table.set_fontsize(size)
    for (i, j), cell in table.get_celld().items():
        cell.set_facecolor('#e4edf5' if i == 0 else ('#f0f5f8' if i % 2 else 'white'))
        cell.set_edgecolor('#d5dee8')
        cell.PAD = .07
    save(fig, name)


fig, axs = plt.subplots(1, 3, figsize=(16, 7))
for ax, key, title, unit in [
    (axs[0], 'final_ready_seconds', '最终文件就绪时间', '秒 / 8 条合格数据'),
    (axs[1], 'final_ready_successes_per_minute', '最终合格吞吐', '条 / 分钟')]:
    values = [pb[key], pa[key]]
    bs = ax.bar(['同步导出', 'auto 导出'], values, color=['#697586', '#197c88'])
    ax.bar_label(bs, fmt='%.2f', padding=5)
    ax.set_ylim(0, max(values) * 1.25)
    ax.set_title(title, loc='left', fontsize=15)
    ax.set_ylabel(unit)
axs[2].axis('off')
axs[2].set_title('共同条件与检查', loc='left', fontsize=15)
axs[2].text(.01, .93,
    '同一 RTX 5090 / cuRobo v1\n4 环境，seed 101\n各 8 条成功目标\n60 个最终保持步\n\n两组严格终态 8/8 通过\n结构检查通过\n8 组动作序列精确匹配\n\n完整文件吞吐提高 47.2%\n新缓存方案尚未实施',
    va='top', fontsize=13, linespacing=1.7)
fig.suptitle('新增独立配对：主机分段计时补齐内部归因，历史 8 环境继续单列', fontsize=17)
save(fig, '43-paired-runtime')

fig, axs = plt.subplots(2, 1, figsize=(16, 7.5))
group_keys = ['export', 'camera', 'physics', 'record_observation', 'planner_reset', 'action_success', 'remaining']
group_colors = ['#e8aa46', '#197c88', '#6278c2', '#77a47b', '#8b5db7', '#b5a070', '#aab4c0']
for ax, percent in zip(axs, (False, True)):
    for y, row in enumerate((pb, pa)):
        left = 0
        for key, color in zip(group_keys, group_colors):
            group = row['execute_groups'][key]
            value = group['fraction'] * 100 if percent else group['seconds_per_episode']
            ax.barh(y, value, left=left, height=.5, color=color,
                    label=group['label'] if y == 0 else None)
            if group['fraction'] > .08:
                label = f"{value:.1f}%" if percent else f"{value:.1f}s"
                ax.text(left + value / 2, y, label, ha='center', va='center', color='white', fontsize=12)
            left += value
        if not percent:
            ax.text(left + 1, y, f"{row['mean_execute_seconds']:.1f}s", va='center')
    ax.set_yticks([0, 1], ['同步导出', 'auto 导出'])
    ax.invert_yaxis()
    ax.set_xlim(0, 100 if percent else 221)
    ax.set_xlabel('execute 窗口内部占比 / %' if percent else '累计秒数 / 已完成 episode')
    ax.grid(axis='x', alpha=.15)
    ax.set_axisbelow(True)
handles, names = axs[0].get_legend_handles_labels()
axs[0].legend(handles, names, ncol=4, loc='upper right', fontsize=10)
axs[0].set_ylim(1.4, -.85)
fig.suptitle('相机绝对耗时接近，占比升高来自导出阻塞减少后的分母变化', fontsize=17)
save(fig, '44-internal-attribution')

timing_table('45-cpu-gpu-work', '物理推进与控制的分工：主机调度、GPU 工作和阻塞分别理解', [
    ['物理推进', '碰撞、接触、关节与刚体运动\n推进机器人与方块的位置 / 速度', 'GPU PhysX 批量推进 4 环境\n主线程调用含提交与等待', '36.66s / 25.69%'],
    ['控制与状态', '动作处理、控制器命令\n写入仿真与更新状态缓冲', 'CPU 调度 + GPU 张量运算\n不代表全部在 CPU 上计算', '13.15s / 9.21%'],
    ['相机位姿', '机器人 link 世界位姿 × 安装变换\n设置三路相机的位置和方向', 'CPU / GPU 混合\n线程 CPU / 调用墙钟约 99.3%', '36.14s / 25.32%'],
    ['相机实际渲染', '从当前场景生成 RGB\n物理状态决定本帧相机与物体位置', 'GPU RTX 渲染\n主线程比值约 45.6%', '28.97s / 20.30%'],
    ['显式 RGB 副本', '将图像从 GPU 复制到 CPU\n交给 recorder 留存', 'GPU→CPU 传输 + 主机处理\n完成后才能读取该副本', '4.16s / 2.91%'],
], ['环节', '在做什么', 'CPU / GPU 分工', 'auto execute 内部'], [.14, .34, .34, .18])

fig, ax = plt.subplots(figsize=(16, 7))
ax.axis('off')
ax.set_xlim(0, 16)
ax.set_ylim(0, 7)
ax.text(.1, 6.55, '批量环境内部并行；同帧阶段按状态依赖推进', fontsize=20, fontweight='bold')
steps = [
    ('动作等齐\n4 环境汇合', '#697586'),
    ('批量物理\n4 个子步', '#6278c2'),
    ('相机位姿\n与状态对齐', '#197c88'),
    ('实际渲染\n对应场景', '#197c88'),
    ('CPU 副本\n录制与返回', '#8b5db7'),
]
for i, (label, color) in enumerate(steps):
    x = 1.45 + i * 3.25
    ax.text(x, 4.8, label, ha='center', va='center', color='white', fontsize=14,
            bbox=dict(boxstyle='round,pad=.65', fc=color, ec='none'))
    if i < len(steps) - 1:
        ax.annotate('', xy=(x + 2.35, 4.8), xytext=(x + 1.05, 4.8),
                    arrowprops=dict(arrowstyle='->', lw=1.8, color='#697586'))
ax.text(.3, 3.25, '环境维度：同一 GPU 批量推进多个环境，GPU 算子内部存在数据并行。', fontsize=15)
ax.text(.3, 2.55, '阶段维度：本帧相机读取依赖物理结果；CPU 消费依赖图像传输完成。', fontsize=15)
ax.text(.3, 1.85, '实际每 batch step：4 次物理推进、约 3 次相机渲染、6 批 RGB CPU 副本。', fontsize=15)
ax.text(.3, .95, '箭头只表示依赖；未采集 GPU 时间线，不能据此断言设备阶段完全串行或已经重叠。', fontsize=12, color='#526276')
save(fig, '46-step-dependencies')

explanation_slide('47-camera-reuse', '首选去重方案：保留两次观测，只复用同状态下的昂贵相机结果', [
    ('当前正常路径', '每步两次观测计算\n每次读取三路 RGB\n\n每个 RGB term 刷新全相机\n6 次全相机刷新\n→ 18 次相机位姿设置\n\n6 批 RGB CPU 副本\n实际渲染已约为 3 次'),
    ('待验证的快路径', '有效状态版本内\n统一刷新三路相机\n\n6 次全相机刷新 → 1 次\n18 次位姿设置 → 3 次\n\n同帧 CPU RGB 副本复用\n6 批 → 3 批\n固定索引和变换也复用'),
    ('缓存失效与所有权', 'reset_epoch / state_revision\n相机 pose_revision / frame_id\n\n重置与事件后立即失效\n保留第二次 compute/history\n不接受过期帧或一帧延迟\n\n每路只持有有界单帧\nrecorder 按环境持有不变'),
])

timing_table('48-speed-priorities', '按实测占比选择优化，以最终合格吞吐评价', [
    ['P0', '位姿刷新去重\n复用固定索引 / 变换', '25.32%\n主线程占用明显', '保持 reset / 事件 / 位姿失效语义'],
    ['P1', '同状态 RGB CPU 副本复用\n保留完整观测计算', '2.91% 显式复制\n未含任意观测的全部成本', '帧序、history、不可变性、内存有界'],
    ['P2', '设备时间线后定位 renderer\n实际跨相机提交和状态同步', '20.30% 渲染调用\n不等于隔离 GPU kernel 时间', '本版本 TiledCamera 已是别名\n不能只换类名期待加速'],
    ['P3', '定位物理提交 / 求解 / 等待\n批量成功判定与小张量操作', '物理推进 25.69%\n控制 / 更新另 9.21%', '先保持 dt、子步、接触与成功阈值'],
    ['后置', '有界 pinned 缓冲 + 异步 D2H\n打包与规划/FK 分别消融', '复制 2.91%\nauto 导出相关 2.55%', '事件完成后 CPU 才读；禁止提前复用\n不盲目增加环境数或 writer'],
], ['顺序', '方案', '实测依据', '正确性与收益边界'], [.08, .29, .25, .38], size=12)

fig, ax = plt.subplots(figsize=(16, 7))
rows = scenario['scenarios']
labels = [row['scenario'] for row in rows]
values = [row['execute_time_reduction_fraction'] * 100 for row in rows]
bs = ax.barh(labels, values, color=['#197c88', '#8b5db7', '#197c88', '#6278c2', '#6278c2', '#aab4c0'])
ax.invert_yaxis()
ax.set_xlim(0, 29)
ax.set_xlabel('条件情景下 execute 时间减少 / %；未实测')
ax.set_title('条件情景估算：以当前 142.71 秒 execute 为分母，尚待实测', loc='left', fontsize=18)
ax.grid(axis='x', alpha=.15)
ax.set_axisbelow(True)
for bar, row, value in zip(bs, rows, values):
    ax.text(value + .35, bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}%  /  余 {row['remaining_execute_seconds']:.2f}s", va='center', fontsize=11)
save(fig, '49-conditional-envelope')

explanation_slide('50-ablation-protocol', '下一轮：输出等价通过之后，才比较最终合格吞吐', [
    ('单项消融与重复', 'A0 现有 auto\nA1 只去重位姿刷新\nA2 只复用 CPU RGB\nA3 两项组合\n\n4 环境、8 条成功目标\n同 seed / 分辨率 / 压缩\n至少 3 对交替顺序重复'),
    ('逐帧正确性', '完整 actions 与严格终态\nframe_id 与 reset_epoch\n重置 / 事件后的第一帧\n两次 compute 的 history\nCPU 帧不可变与归属\nGPU / CPU 缓冲有界\n\n图像容差来自基线重复'),
    ('计时与设备诊断', '记录主循环与最终就绪\n分段闭合 / 内存峰值\n主线程 CPU / 设备时间线\n\nNVTX + CUDA / 图形追踪\n先核对本地工具兼容性\n\nprofiler 与吞吐运行分开\n以合格条数 / 分钟判断'),
])
