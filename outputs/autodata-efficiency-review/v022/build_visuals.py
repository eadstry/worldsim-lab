"""Generate editable SVG architecture figures using only the Python standard library."""
from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parent / 'architecture-images'
OUT.mkdir(exist_ok=True)
COLORS = {'blue': ('#eaf2ff', '#2563eb'), 'green': ('#e5f5ef', '#148269'),
          'purple': ('#f0ebff', '#7954bc'), 'gray': ('#eef2f6', '#516579'),
          'amber': ('#fff3dd', '#a56c16')}


def diagram(name, title, subtitle, columns, footer, links=True):
    width, height = 1200, 640
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{escape(title)}</title>',
         '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="none" stroke="#75879b" stroke-width="1.5"/></marker></defs>',
         '<rect width="1200" height="640" rx="22" fill="#f7f9fc"/>',
         '<style>text{font-family:"Noto Sans CJK SC","WenQuanYi Micro Hei","Microsoft YaHei",sans-serif} .t{font-size:29px;font-weight:700;fill:#122c46}.sub{font-size:17px;fill:#52677c}.head{font-size:21px;font-weight:700}.body{font-size:18px;fill:#233d56}</style>',
         f'<text x="40" y="53" class="t">{escape(title)}</text>',
         f'<text x="40" y="87" class="sub">{escape(subtitle)}</text>']
    n = len(columns)
    gap = 34
    w = (1120 - (n - 1) * gap) / n
    for i, (label, color, cards) in enumerate(columns):
        x = 40 + i * (w + gap)
        bg, fg = COLORS[color]
        s += [f'<rect x="{x}" y="120" width="{w}" height="420" rx="16" fill="white" stroke="#dae3ed"/>',
              f'<rect x="{x}" y="120" width="{w}" height="53" rx="14" fill="{bg}"/>',
              f'<text x="{x+18}" y="154" class="head" fill="{fg}">{escape(label)}</text>']
        for j, (heading, lines) in enumerate(cards):
            y = 194 + j * 110
            s.append(f'<rect x="{x+14}" y="{y}" width="{w-28}" height="93" rx="10" fill="{bg}"/>')
            s.append(f'<text x="{x+27}" y="{y+28}" font-size="19" font-weight="700" fill="{fg}">{escape(heading)}</text>')
            for k, line in enumerate(lines):
                s.append(f'<text x="{x+27}" y="{y+53+k*24}" class="body">{escape(line)}</text>')
        if links and i < n - 1:
            s.append(f'<path d="M{x+w+3},335 H{x+w+gap-6}" stroke="#75879b" stroke-width="2" marker-end="url(#arrow)"/>')
    if name == '03-export.svg':
        s.append('<path d="M990,550 H210" fill="none" stroke="#75879b" stroke-width="2" stroke-dasharray="7 5" marker-end="url(#arrow)"/>')
    s.append(f'<text x="42" y="584" class="sub">{escape(footer)}</text>')
    s.append('<text x="42" y="613" font-size="13" fill="#7a8da0">AUTODATA · ARCHITECTURE NOTES / v022 · 2026-10-16 · 箭头表示关系，不表示耗时比例</text></svg>')
    (OUT / name).write_text('\n'.join(s))


diagram('01-evolution.svg', '三种实现，两条改动轴', '先改保存调度，再单独评估规划迁移；任务与仿真仍是共同主干。', [
 ('A / 原始 v1 路线', 'gray', [('任务与执行', ['AutoData → 仿真 → 录制']), ('规划后端', ['MotionGen / v1']), ('保存方式', ['同步压缩与 HDF5 写入', '返回后继续生成'])]),
 ('B / 保存优化 v1', 'green', [('任务与执行', ['沿用任务与规划契约']), ('规划后端', ['仍为 MotionGen / v1']), ('新增保存模块', ['Bridge → Pool → writer', '共享内存 / 回执 / 合并'])]),
 ('C / v2 实验适配', 'purple', [('任务与执行', ['适配后接回原执行路径']), ('更换规划后端', ['MotionPlanner / v2', '模型、目标与轨迹转换']), ('保存方式', ['沿用异步保存机制', '独立冻结实验入口'])]),
], 'A → B：保存侧工程优化　　B → C：规划侧迁移　　C 不代表当前生产默认配置')

diagram('02-composition.svg', '当前项目：从任务资源到可交付数据', '外层：run_local.py 监督生成进程；telemetry / monitor 记录运行状态。', [
 ('01 / 输入与任务', 'blue', [('运行资源', ['示范 HDF5 / 任务 YAML', '机器人资产 / runtime']), ('AutoData', ['任务阶段与生成策略', '状态读取、目标与动作组织']), ('依赖边界', ['使用对应嵌套框架依赖', '根 Arena 独立锁定'])]),
 ('02 / 规划与执行', 'purple', [('规划后端', ['当前生产封装：v1', '独立实验适配：v2']), ('仿真环境', ['Isaac Lab / Isaac Sim', '物理、观测、相机']), ('录制器', ['收集 EpisodeData', '保持任务与数据格式契约'])]),
 ('03 / 保存与证据', 'green', [('保存策略', ['同步 / 固定上限 / auto', 'workers=0 是当前默认']), ('异步分支', ['Bridge / Pool / writer', '分片 → 排空 → 合并']), ('最终交付', ['HDF5 + 运行记录', '结构回读 + 末态检查'])]),
], '本地扩展位于 workspace-overlays；历史 v2 启动器与 outputs 证据不是上游默认实现。')

diagram('03-export.svg', '异步保存：数据向右走，完成回执向左返回', '生成主进程管理多个环境；CPU writer 只处理保存，不运行新的仿真环境。', [
 ('生成侧 / Bridge', 'blue', [('录制', ['帧、动作、状态', '组成 EpisodeData']), ('移交', ['导出接口交给 Bridge', '打包后释放不再需要的源帧']), ('继续生成', ['提交可以先返回', '预算不足时仍然等待'])]),
 ('协调侧 / ExportPool', 'green', [('共享内存', ['保存数据与描述信息', '在途字节预算限制积压']), ('任务调度', ['提交到 writer 队列', '按上限与资源准入扩容']), ('回执与回收', ['收到 saved 后更新计数', '释放共享内存、归还预算'])]),
 ('保存侧 / writer', 'gray', [('读取与压缩', ['按描述读取共享内存', 'CPU 压缩与磁盘写入']), ('独立分片', ['每个 writer 写各自分片', '完成后返回 saved']), ('最终收尾', ['主流程排空并合并', '关闭后记录 output_ready'])]),
], '虚线回执：writer ┄ saved ┄→ ExportPool ┄ 更新计数 ┄→ Bridge；入队成功 ≠ 文件就绪')

diagram('04-contract.svg', '组合契约：规划后端与保存策略分别选择', '本图展示接口关系；不表示两种规划器会在同一次任务中串联执行。', [
 ('任务输入', 'blue', [('任务阶段', ['抓取 / 搬运 / 放置']), ('规划输入契约', ['当前状态 + 目标位姿', '机器人模型 + 碰撞场景']), ('配置与语义', ['关节名 / 坐标系', '接触与附着物状态'])]),
 ('后端二选一', 'purple', [('v1 路线', ['MotionGen', '原规划封装']), ('v2 实验路线', ['MotionPlanner', '输入转换 + 结果恢复']), ('共同返回契约', ['任务可消费的轨迹', '成功 / 失败状态'])]),
 ('执行与保存', 'green', [('执行', ['动作队列 → env.step', '物理与观测更新']), ('录制', ['EpisodeData']), ('保存另行选择', ['同步 或 异步 writer', '最终输出与质量检查'])]),
], '已覆盖：v1 同步、v1 异步、v2 异步的历史实验；其余组合不能据此视为已验收。')

diagram('05-curobo.svg', 'cuRobo：共同基础、新增方向与实际使用范围', '能力升级需要任务、配置和验证共同支撑，不能由版本名推导生产收益。', [
 ('v1 / 已有基础', 'blue', [('GPU 运动生成', ['IK / 碰撞检查', '几何规划 / 轨迹优化']), ('高层入口', ['MotionGenConfig', 'Pose → plan_single']), ('项目角色', ['任务规划基线', '保存优化的共同后端'])]),
 ('v2 / 重点能力', 'purple', [('动力学感知轨迹', ['B-spline 表示', '平滑性与力矩限制']), ('深度场景建图', ['GPU 原生 TSDF / ESDF', '由深度观测构造距离场']), ('高自由度扩展', ['运动学 / 逆动力学', '全身自碰撞计算'])]),
 ('当前项目 / 使用边界', 'amber', [('已经接入', ['新版规划 API 与转换层', '已有历史整轮运行']), ('仍沿用', ['USD 几何碰撞场景', '原任务执行与异步保存']), ('尚未专项验证', ['力矩约束 / 深度融合', '全身规划 / 稳定性能优势'])]),
], 'v2 库级能力来自官方说明；右列是本地冻结适配器与实验记录支持的范围。', False)

diagram('06-adapter.svg', 'v2 适配器：把新版规划接回原任务', '输入保持语义，内部更换求解，输出恢复契约。', [
 ('输入转换', 'blue', [('机器人', ['convert_robot', '关节重排、夹爪锁定']), ('场景', ['USD 几何 → 碰撞场景', '动态障碍位姿更新']), ('目标', ['世界坐标 → 基坐标', 'GoalToolPose'])]),
 ('v2 求解', 'purple', [('配置', ['MotionPlannerCfg.create', '固定种子、容差与采样设置']), ('阶段处理', ['接触碰撞 / 物体附着', '按任务配置控制 refinement']), ('调用', ['plan_pose', '读取成功状态与轨迹'])]),
 ('结果恢复', 'green', [('轨迹', ['get_interpolated_plan', '检查并重排关节名字']), ('末端路径', ['FK 与坐标恢复', '任务需要的路径重采样']), ('原任务执行', ['动作执行 → 录制 → 保存', '重新检查物理末态'])]),
], '本地实现依据冻结 v2 提交；内部 API 引用和局部包装会增加后续升级维护成本。')
