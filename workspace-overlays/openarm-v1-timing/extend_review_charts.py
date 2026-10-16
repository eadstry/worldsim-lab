# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Extend the designated v013 chart book with measured v1 timing and plans.

Preparation writes a new unsealed version. Rendering, review and sealing are
separate steps; it never overwrites the source or uploads a deliverable.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from pathlib import Path


NEW = [
    ("43-paired-runtime", "新增配对实验的条件与质量"),
    ("44-internal-attribution", "执行等待内部的实际工作"),
    ("45-cpu-gpu-work", "物理控制和相机各自做什么"),
    ("46-step-dependencies", "环境并行与阶段依赖"),
    ("47-camera-reuse", "相机刷新和图像副本如何复用"),
    ("48-speed-priorities", "按实测占比选择加速方案"),
    ("49-conditional-envelope", "条件情景与收益边界"),
    ("50-ablation-protocol", "下一轮怎样验证加速与等价性"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare(source, paired, destination):
    assert not destination.exists(), "Use a fresh version directory"
    old_manifest = json.loads((source / "manifest.json").read_text())
    assert all(sha(source / name) == digest for name, digest in old_manifest["files"].items())
    pair_manifest = json.loads((paired / "manifest.json").read_text())
    assert all(sha(paired / name) == digest for name, digest in pair_manifest["files"].items())
    shutil.copytree(source, destination)
    for name in ("manifest.json", "verification.json"):
        (destination / name).unlink()
    shutil.copytree(paired, destination / "paired4")
    shutil.copy2(Path(__file__).with_name("review_timing_figures.py"), destination / "build_timing_figures.py")
    shutil.copy2(Path(__file__), destination / "extend_review_charts.py")
    data = json.loads((paired / "report.json").read_text())
    before, after = data["runs"]
    assert before["successes"] == after["successes"] == 8
    assert data["validation_passed"] and data["pair_data_check"]["all_action_sequences_match_as_multiset"]
    t = after["mean_execute_seconds"]
    phases = after["execute_phase_mean_seconds"]
    scenarios = [
        ("位姿整批刷新 6 次变 1 次", phases["camera_pose"] * 5 / 6),
        ("RGB 副本 6 批变 3 批", phases["rgb_cpu_copy"] / 2),
        ("上面两项同时成立", phases["camera_pose"] * 5 / 6 + phases["rgb_cpu_copy"] / 2),
        ("相机渲染调用耗时减半", phases["camera_render"] / 2),
        ("物理推进调用耗时减半", phases["physics_step"] / 2),
        ("全部 RGB 复制完全隐藏", phases["rgb_cpu_copy"]),
    ]
    scenario_rows = [{"scenario": name, "saved_execute_seconds": saved,
                      "remaining_execute_seconds": t - saved,
                      "execute_time_reduction_fraction": saved / t,
                      "conditional_execute_speedup": t / (t - saved)} for name, saved in scenarios]
    dump(destination / "acceleration-scenarios.json", {
        "baseline_execute_seconds": t, "kind": "conditional arithmetic only, not measured speedup or final-file prediction",
        "assumptions": ["Target category cost scales linearly with the assumed operation reduction",
                        "All removed latency lies on the measured execute window's critical path",
                        "Other phase costs, work counts, caches and queue interactions stay unchanged",
                        "Reset/event/observation semantics permit the proposed reuse"],
        "scenarios": scenario_rows})

    notes = json.loads((destination / "slide-notes.json").read_text())
    notes.update({
        "43-paired-runtime": [
            "当前实验：2026-10-15，v1 同步 / auto 各 4 环境、8 条成功目标、seed 101。",
            "支持结论：两组 8/8 严格终态通过、动作序列精确匹配；最终文件吞吐提升 47.2%。",
            "读图讲解：这是独立的 4 环境配对，不能与前面 8 环境历史实验混成同一组。"],
        "44-internal-attribution": [
            "当前测量：同步作用域互斥计时；统计完成 episode 的 execute 窗口，取消样本排除。",
            "支持结论：execute 减少 54.82 秒，其中导出相关减少 54.77 秒；相机绝对耗时接近。",
            "读图讲解：主机 API 墙钟包括阻塞；并发窗口会重叠，百分比不是 GPU kernel 占比。"],
        "45-cpu-gpu-work": [
            "当前依据：运行日志确认 cuda:0、PhysX 与 RTX；已记录主线程墙钟及线程 CPU 时间。",
            "支持结论：GPU 批量物理与渲染已启用，控制、位姿设置和 CPU 图像副本仍有主机成本。",
            "读图讲解：先说明每个环节做什么，再区分 CPU 调度、GPU 工作和主机等待。"],
        "46-step-dependencies": [
            "当前依据：实际 step 调用顺序和计数；4 个环境共享整批动作屏障与一条主循环。",
            "支持结论：环境内部可批量并行；同帧物理、相机刷新和采集有数据依赖，重叠未测。",
            "读图讲解：此图是依赖关系示意，不是 GPU 时间线；计数不能证明 kernel 同时运行。"],
        "47-camera-reuse": [
            "当前测量：正常 step 两次观测、六批 RGB 副本、六次全相机刷新；实际渲染约三次。",
            "方案目标：按有效状态版本复用相机位姿与单帧 RGB；保留 reset / 事件后的更新。",
            "读图讲解：6→1 与 6→3 是待验证的调用目标；GPU 渲染本来已有缓存，不能再算减半。"],
        "48-speed-priorities": [
            "当前基线：auto 的位姿 25.32%、渲染 20.30%、物理推进 25.69%、RGB 复制 2.91%。",
            "方案顺序：先去重复位姿与图像副本，再用设备追踪定位渲染或物理；传输重叠后置。",
            "读图讲解：本版本的 TiledCamera 已是 Camera 别名；仅换类名没有新增并行收益。"],
        "49-conditional-envelope": [
            "当前计算：以 auto 的 142.71 秒 execute 为分母，假定目标成本线性缩放且其余不变。",
            "支持范围：位姿 6→1 情景减少 21.1%，两项合计减少 22.6%；都是算术情景而非实测。",
            "读图讲解：不能外推最终文件吞吐；该口径还有排空、合并以及并发窗口重叠。"],
        "50-ablation-protocol": [
            "当前状态：新增缓存、渲染和流水线方案均未实施；本页是下一轮实验协议。",
            "验证要求：单项消融、交替顺序重复，核对动作、帧归属、重置观测、终态与内存峰值。",
            "读图讲解：先证明输出等价再比较最终合格吞吐；诊断 profiler 与吞吐运行分开。"],
    })
    # Keep the older 8-env analyses scoped explicitly instead of presenting
    # their historical lack of instrumentation as a claim about the new pair.
    notes["40-gpu-chain"][0] = "历史依据：8 环境动作队列与冻结导出源码；新增 4 环境实测在后续页面单列。"
    notes["41-camera-copies"][0] = "历史依据：冻结相机配置与当前 RL step；新增 4 环境插桩已核对加载文件与调用数。"
    notes["41-camera-copies"][1] = "支持结论：新配对确认六批 RGB 副本与约三次渲染；历史 8 环境依赖身份仍需区分。"
    notes["42-gpu-validation"][0] = "证据边界：历史 8 环境没有内部分段；后续新增 4 环境主机计时，仍无 kernel 追踪。"
    notes["42-gpu-validation"][1] = "支持结论：主机分段已可量化，设备重叠与缓存优化收益仍需独立消融验证。"
    dump(destination / "slide-notes.json", notes)
    order = json.loads((destination / "chart-order.json").read_text())
    insertion = next(i for i, row in enumerate(order) if row["id"] == "42-gpu-validation") + 1
    order[insertion:insertion] = [{"id": key, "section": "三、v1 效率与耗时解释"} for key, _ in NEW]
    assert len(order) == 51 and set(notes) == {r["id"] for r in order}
    dump(destination / "chart-order.json", order)

    # Preserve every original guide body, replacing its page number and notes.
    guide = (source / "charts-guide.md").read_text()
    old_bodies = {}
    for chunk in guide.split("## 第 ")[1:]:
        key = chunk.splitlines()[0].rsplit(" · ", 1)[1]
        paras = chunk.split("\n\n")[4:]
        old_bodies[key] = "\n\n".join(p for p in paras if not p.strip().startswith("下一页："))
    bodies = new_guide_bodies(before, after, scenario_rows)
    pages = ["# 图册逐页讲解稿", "", "45 页主线 + 6 页附录；历史 8 环境与新增 4 环境配对分别标注。", ""]
    for i, row in enumerate(order, 1):
        key = row["id"]
        body = bodies.get(key, old_bodies.get(key, ""))
        pages += [f"## 第 {i:02d} 页 · {row['section']} · {key}", "", *sum(([line, ""] for line in notes[key]), []), body.strip(), ""]
        if i < len(order):
            pages += [f"下一页：{order[i]['id']}", ""]
    (destination / "charts-guide.md").write_text("\n".join(pages))

    for path in destination.glob("build_*.py"):
        text = path.read_text().replace("v013", "v014")
        if path.name == "build_figures.py":
            anchor = "assert set(FIGURES)==set(PAGE)"
            assert text.count(anchor) == 1
            text = text.replace(anchor, "exec(compile((P/'build_timing_figures.py').read_text(), str(P/'build_timing_figures.py'), 'exec'), globals())\n\n" + anchor)
            text = text.replace("主线 37 页", "主线 45 页").replace("43 figures", "51 figures")
            text = text.replace("'font.family':'Noto Sans CJK JP'", "'font.family':'WenQuanYi Micro Hei'")
            text = text.replace("相机路径：重复观测可能重复回传与复制，需核验实际加载版本", "历史相机路径与新增配对实测：重复计算需要按状态版本复用")
        elif path.name == "build_charts.py":
            text = text.replace("37 页主线 + 6 页附录", "45 页主线 + 6 页附录")
            text = text.replace("所有数字来自已有实验，本版没有新增运行。", "历史 8 环境与新增 4 环境插桩配对分开呈现；新增加速方案尚待消融验证。")
            text = text.replace("43 slides", "51 slides")
            text = text.replace('<nav><a href="gpu-analysis.html">', '<nav><a href="acceleration-analysis.html">内部实测与加速方案</a> · <a href="gpu-analysis.html">')
        path.write_text(text)

    analysis = make_analysis(before, after, data, scenario_rows)
    (destination / "acceleration-analysis.md").write_text(analysis)
    (destination / "acceleration-analysis.html").write_text(render_analysis(analysis))
    for filename in ("report.md", "gpu-analysis.md", "execution-analysis.md"):
        text = (destination / filename).read_text().replace("v013", "v014")
        text = text.replace("37 页主线 + 6 页附录", "45 页主线 + 6 页附录")
        update = "\n\n## 新增 4 环境插桩配对与加速方案\n\n本版引入 2026-10-15 的独立 4 环境配对：同步与 auto 各 8/8 严格终态通过，8 组完整动作序列精确匹配，最终文件吞吐提升 47.2%。这组结果不替换历史 8 环境数据，也不代表已测得 GPU kernel 占比。\n\n详见 [内部计时与加速方案](acceleration-analysis.html) 和图册新增八页；原始结果、计时脚本与校验记录在 paired4/ 中。下面的新增分析优先去除重复相机刷新和重复 CPU 图像副本，缓存优化尚未实施。\n\n"
        first_end = text.index("\n\n")
        text = text[:first_end] + update + text[first_end:]
        (destination / filename).write_text(text)
    # Teach the existing Markdown renderers to link the new local report.
    for path in destination.glob("build_*.py"):
        if path.name in ("build_report.py", "build_gpu_report.py", "build_execution_report.py"):
            text = path.read_text().replace("(?:https://|source/)", "(?:https://|source/|acceleration-)")
            path.write_text(text)
    root = Path(__file__).resolve().parents[2]
    isaac = root / "AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source"
    snippets = [
        ("tiled-current", isaac / "isaaclab/isaaclab/sensors/camera/tiled_camera.py", 1, 42),
        ("physx-device", isaac / "isaaclab_physx/isaaclab_physx/physics/physx_manager.py", 570, 615),
        ("camera-render-current", isaac / "isaaclab/isaaclab/sensors/camera/camera.py", 535, 578),
    ]
    extra_sources = []
    for slug, path, first, last in snippets:
        lines = path.read_text().splitlines()
        code = ''.join(f'<span id="L{i}"><a href="#L{i}">{i}</a>  {html.escape(lines[i-1])}</span>\n'
                       for i in range(first, min(last, len(lines)) + 1))
        (destination / "source" / f"{slug}.html").write_text(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>当前源码定位</title>'
            '<style>body{font:16px/1.7 system-ui;padding:28px;background:#f7f9fc}pre{background:white;padding:20px;overflow:auto}span{display:block}span:target{background:#ffe59a}</style>'
            '<a href="../acceleration-analysis.html">返回加速方案</a><h1>当前本地源码</h1><p>' + html.escape(str(path)) + '</p><p>SHA256: ' + sha(path) + '</p><pre>' + code + '</pre></html>')
        extra_sources.append({"path": str(path), "sha256": sha(path), "ranges": [[first, last]],
                              "viewer": f"source/{slug}.html", "kind": "current local dependency source; not historical 8-env identity proof"})
    dump(destination / "acceleration-source-evidence.json", extra_sources)
    (destination / "CHANGELOG.md").write_text("# v014\n\n新增八页图册，共 51 页（45 页主线与 6 页附录）。引入独立 4 环境 v1 同步/auto 插桩配对，保留历史 8 环境与 v2 数据。补充主机内部占比、CPU/GPU 分工、阶段依赖、状态版本缓存、加速优先级、条件情景和消融协议。未运行新的缓存或渲染优化实验；没有将主机延迟当 GPU kernel 时间。保留 v013，沿用本地交付策略。\n")
    dump(destination / "extension-provenance.json", {
        "base": str(source), "base_manifest_sha256": sha(source / "manifest.json"),
        "paired": str(paired), "paired_manifest_sha256": sha(paired / "manifest.json"),
        "base_files": old_manifest["files"], "base_data_preserved": ["data.json", "data.csv", "internal-timing.csv", "backend-comparison.csv", "execution-analysis.json"],
        "source_thread": {"title": "可视化分析改进前后生产效率", "id": "01a13d99-75d6-7922-aac2-4200004d11b9", "status_at_read": "idle"},
        "new_chart_ids": [key for key, _ in NEW], "delivery_policy": "local_only",
        "web_sources": [
            {"url": "https://docs.pytorch.org/tutorials/intermediate/pinmem_nonblock.html", "role": "D2H asynchronous completion and pinned-memory conditions", "checked_on": "2026-10-15"},
            {"url": "https://docs.nvidia.com/cuda/archive/13.0.1/cuda-c-best-practices-guide/index.html", "role": "Conditional copy/compute overlap and stream dependencies", "checked_on": "2026-10-15"},
            {"url": "https://docs.nvidia.com/nsight-systems/UserGuide/index.html", "role": "CPU/CUDA/graphics timeline attribution", "checked_on": "2026-10-15"}],
        "scope": "Integrates completed paired GPU evidence; this chart update runs no new simulation or optimization experiment"})
    print(destination)


def new_guide_bodies(before, after, scenarios):
    return {
        "43-paired-runtime": "两组运行在同一台 RTX 5090 上依次进行，使用同一 v1 冻结启动器、输入与任务、seed 101、4 环境、8 条成功目标及 60 个最终保持步。完整动作数组按 SHA256 匹配 8 组，严格终态和文件结构检查均通过。最终文件就绪为 515.77→350.30 秒，包含异步排空和合并；该单轮配对支持本条件下的收益，不支持跨批次或跨机器的固定倍数。\n\n初始 8 环境试跑在完成首条前被 SIGKILL，最后采样 RSS 约 50.9 GB，OOM-kill 计数增加 1。因此正式对照统一采用 4 环境，不能用本页替换前面 8 环境历史图。",
        "44-internal-attribution": "主线程同步调用按嵌套作用域互斥计时；每次 execute 在入口与返回时读取相同计时器的差值，回答的是该动作等待时主程序在做什么。多环境等待窗口互相重叠，均值可在单个窗口内部拆分，但不能累加成整批墙钟。\n\n同步组 execute 为 197.53 秒，auto 为 142.71 秒。减少的 54.82 秒中，导出与背压归因减少 54.77 秒。相机绝对耗时约 70.72→71.41 秒，物理与控制约 51.20→49.80 秒，新增高占比主要来自导出分母缩小。queue.join 仍占约 98.6%，不意味着 GPU 或 CPU 空闲。",
        "45-cpu-gpu-work": "日志确认环境设备 cuda:0、PhysX 后端和 IsaacRtxRenderer。物理子步处理关节与刚体动力学、接触和碰撞；控制侧还要处理目标、写入动作与更新状态。相机位姿计算把机器人 link 的世界位姿与相机安装变换组合，再设置三个相机；渲染生成 RGB，随后显式复制到 CPU 供 recorder 使用。\n\nauto 中物理推进 36.66 秒、相机位姿 36.14 秒、相机渲染 28.97 秒。线程 CPU / 对应调用墙钟分别约 22.9%、99.3%、45.6%；这说明主线程占用特征不同，但差额还可包含其他线程工作、I/O 和调度，不能全部叫 GPU 等待。",
        "46-step-dependencies": "4 个环境的动作等齐后，一次 env.step 批量推进它们；内部每步执行 4 个 1/120 秒物理子步。相机需要与新物理状态对齐，CPU 记录必须等待对应帧数据就绪。环境与 GPU 算子内部并行，不证明物理和同帧渲染在不同流上重叠。\n\n本次两组均有 2,778 个全局 batch step，11,112 次 physics_step；含重置调用时，相机 renderer.render 8,367 次、RGB CPU copy 16,701 次。正常每步为 3 次批量相机渲染和 6 批 CPU 图像副本。图中箭头表示依赖，不是用时或设备追踪。",
        "47-camera-reuse": "建议先将全相机位姿刷新从每个 rgb_image 内提到一次有效状态版本的公共准备阶段，并复用相机父 link 索引、安装变换和固定 tensor。普通未变状态路径目标为 6 次全相机刷新降为 1 次，即 18 次相机设置降为 3 次；reset、事件或相机修改时必须失效。\n\n再为每路 RGB 缓存一份已完成的 CPU 帧，第二次观测只在状态与帧版本一致时复用。保留第二次 observation.compute 及其 history 语义，仅复用可证明不变的昂贵 term。缓存键至少包含环境 reset epoch、物理状态版本、相机位姿版本与帧标识；不能仅看 step_id 或用一帧延迟替代。CPU recorder 的按环境所有权和 clone 语义保留，缓存严格有界。",
        "48-speed-priorities": "P0 为位姿刷新去重及固定索引/变换复用，覆盖 25.32% 的当前 execute 主机延迟；P1 为同状态 RGB 副本复用，显式复制仅占 2.91%，收益应保守。P2 先用 CPU/CUDA/图形时间线核对真正的设备工作、提交空隙和同步，再评估 renderer 的批量提交与渲染质量参数。\n\n本地 tiled_camera.py 将 TiledCamera 定义为 Camera 的弃用别名，说明仅更换类名不是新增优化。可研究的应是实际 renderer 对跨相机视图的提交和缓冲管理。跨帧异步 D2H 需要预分配有界 pinned 缓冲、事件完成检查与所有权移交；直接加 non_blocking=True 不足以保证 CPU 已能读数据。\n\n物理求解优化保持 dt、decimation、solver 与接触阈值不变作为第一轮约束。增大 dt、降低相机帧率或分辨率、去掉某路相机均会改变输出契约，应作为另一个质量/成本实验，不能混入等价加速。8 环境已 OOM，不能盲目扩大 num_envs。",
        "49-conditional-envelope": "设基线 execute 为 T，目标环节耗时为 C，假设该成本线性缩放为原来的 r，其余成本与调用次数完全不变，则情景 T'=T−C(1−r)。位姿刷新 6→1 对应 36.14×5/6≈30.11 秒，情景 execute 约 112.59 秒，时间减少 21.1%。位姿与 RGB 复制两项合计情景约 110.51 秒，时间减少 22.6%。\n\n这些是待验证假设下的算术情景；线程调度、缓存失效、设备重叠和 API 依赖都可使真实收益不同。最终文件就绪还包含主循环结束后的约 31.35 秒，且 execute 窗口本身跨环境重叠，因此不能把情景加速倍数直接套到最终吞吐。",
        "50-ablation-protocol": "先做一个 reset/事件/帧一致性小测，再依次比较 A0 auto、A1 仅位姿缓存、A2 仅 RGB 缓存、A3 两者组合。所有版本采用 4 环境、seed 101、8 条成功目标、相同三路 640×480 uint8 RGB 和 gzip-2。至少 3 对交替顺序重复；用于扩展结论时再加入多个 seed。\n\n检查全动作数组、末态阈值、录制前后观测 history、每环境 frame_id 和 reset_epoch、缓存失效后第一帧、图像不可变性与进程内存峰值。RGB 噪声容差由原基线重复测得，不随优化结果放宽。所有 GPU/CPU 缓冲有界，采集完成前不交给 CPU writer；质量通过后以最终就绪的合格条数/分钟评价。\n\n诊断运行单独收集 NVTX 与 CUDA/图形 API 时间线，确认当前 Nsight 与 CUDA/Blackwell 组合受支持；吞吐运行关闭 profiler，以免采样扰动结果。后续渲染批量化、异步传输、成功判定与 FK 批处理各自单独消融。",
    }


def make_analysis(before, after, data, scenarios):
    t = after["mean_execute_seconds"]
    lines = ["# v1 内部耗时与加速方案", "",
        "优先减少相机位姿的重复刷新，再复用同状态下的 CPU 图像副本。当前 auto 路径中，相机相关占 execute 的 50.04%，其中位姿更新为 25.32%、实际渲染为 20.30%、显式 RGB 拷贝为 2.91%。这些是主机调用延迟的归因；物理与渲染的 GPU 重叠程度仍需设备时间线测量。", "",
        "## 新配对的实验范围", "",
        "2026-10-15 在同一 RTX 5090 上依次运行冻结 v1 同步导出和 auto 导出；4 环境、seed 101、各 8 条成功目标、60 个最终保持步。两组 8/8 严格终态与结构验证通过，8 组完整动作序列精确匹配。原图中的 8 环境历史实验继续单列；初始 8 环境插桩试跑 OOM 退出，没有完成样本，不参与比较。", "",
        f"最终文件就绪 {before['final_ready_seconds']:.2f}→{after['final_ready_seconds']:.2f} 秒，吞吐提升 {(data['throughput_speedup']-1)*100:.1f}%。execute 均值 {before['mean_execute_seconds']:.2f}→{t:.2f} 秒；减少的 54.82 秒中，导出相关减少 54.77 秒。异步提交已显著减少同步导出的影响；这次缓存方案尚未实施。", "",
        "| 环节 | 同步秒/episode | 占 execute | auto 秒/episode | 占 execute |", "|---|---:|---:|---:|---:|"]
    for key, group in after["execute_groups"].items():
        a = before["execute_groups"][key]
        lines.append(f"| {group['label']} | {a['seconds_per_episode']:.2f} | {a['fraction']*100:.2f}% | {group['seconds_per_episode']:.2f} | {group['fraction']*100:.2f}% |")
    lines += ["", "## CPU 与 GPU 在完成什么", "",
        "GPU PhysX 批量推进 4 个环境的碰撞、接触、关节与刚体运动；控制路径还负责动作处理、控制器指令、写入和状态更新。相机位姿根据机器人 link 世界位姿与安装变换计算；该路径在本次运行有明显主线程占用。RTX 渲染生成图像，再将对应 RGB 复制到 CPU 供 recorder 保存。", "",
        "同一 batch 中环境与 GPU 算子可并行，而同帧物理、相机刷新、渲染和采集之间有依赖。本次没有 CUDA/图形队列时间线，不能从调用墙钟推导它们同时执行。主线程 CPU 时间与墙钟的差额也不全是 GPU 等待。", "",
        "## 加速优先级", "",
        "| 优先级 | 方案 | 实测依据 | 保留的语义与验收 |", "|---|---|---|---|",
        "| P0 | 全相机位姿按有效状态版本刷新一次；复用 link 索引、安装变换及固定 tensor | 位姿 36.14 秒，占 25.32%；正常 step 6 次全相机刷新 | reset、场景事件、相机变更立即失效；不能沿用过期位置 |",
        "| P1 | 两次观测间复用同一已完成 CPU RGB 帧，保留两次 compute | RGB 副本正常每步 6 批，实际渲染约 3 次；显式复制仅 4.16 秒 | 检查 state/frame/reset epoch、历史更新、帧归属和不可变性；按环境持有、有界缓存 |",
        "| P2 | 追踪 CPU/CUDA/图形时间线后，减少 renderer 的跨相机提交和变换同步开销 | 实际渲染 28.97 秒，占 20.30% | 本地 TiledCamera 已是 Camera 别名；更换类名不构成加速。保留成像标定、帧序和渲染质量 |",
        "| P3 | 根据物理时间线定位提交、同步或求解成本，再检查控制与小张量操作 | 物理推进 36.66 秒，占 25.69%；控制/更新另约 9.21% | 第一轮保持 dt=1/120、decimation=4、solver/接触阈值不变；质量通过再计吞吐 |",
        "| 后置 | 有界 pinned-memory 双缓冲和异步 D2H；共享内存打包或判定/FK 批处理另做消融 | 显式 RGB 复制仅 2.91%；auto 导出相关仅 2.55% | CPU 消费前等事件，源帧/缓冲不可提前复用；不能只加 non_blocking=True |", "",
        "第一轮不调整相机数量、分辨率、录制频率、物理步长或成功阈值。它们可以降低成本，但会改变数据与物理契约，需要单独比较质量。也不直接增加环境数：8 环境试跑已有 OOM 记录，需先解决存储所有权与峰值内存。", "",
        "## 缓存设计要点", "",
        "正常路径将 6 次全相机位姿刷新减少到 1 次，对应 18→3 次相机设置；RGB CPU 副本目标为 6→3 批。保留第二次 observation.compute，仅对状态未改变的昂贵相机 term 复用。缓存键覆盖 reset_epoch、物理状态版本、相机位姿版本和 frame_id；事件或任一环境重置时保守失效。缓存一份单帧结果，不能缓存整条 CUDA 轨迹，也不能将缓冲的可变视图交给仍在保存的消费者。", "",
        "调用数下降不代表渲染次数再减半：本次 3 次批量相机渲染/step 已体现渲染缓存，主要额外成本是位姿重复处理和 CPU 副本。新缓存仍需检查每一步、每环境的图像与状态对齐。", "",
        "## 收益的条件情景", "",
        "以 auto 的 142.71 秒 execute 为分母，假设目标成本线性缩放、删除的时间完全处于该窗口关键路径、其他阶段与任务不变。下表仅为算术情景，未进行缓存或求解优化实测。", "",
        "| 假设 | 情景节省秒数 | 情景 execute 秒数 | execute 时间减少 |", "|---|---:|---:|---:|"]
    for s in scenarios:
        lines.append(f"| {s['scenario']} | {s['saved_execute_seconds']:.2f} | {s['remaining_execute_seconds']:.2f} | {s['execute_time_reduction_fraction']*100:.2f}% |")
    lines += ["", "并发 execute 窗口重叠，最终文件还有约 31.35 秒主循环后的排空、合并和关闭。因此不能直接把这些比例换算为最终文件吞吐提升，也不能把所有情景叠加；GPU 工作可能因重排而移到别的主机调用边界。", "",
        "## 下一轮验证", "",
        new_guide_bodies(before, after, scenarios)["50-ablation-protocol"], "",
        "## 资料与源码依据", "",
        "- [本次配对原报告](paired4/index.html)，含原始分段摘要、运行日志元数据、动作匹配与检查结果。",
        "- [相机任务源码](source/camera.html#L20) 与 [两次观测计算](source/rl-step.html#L243)。",
        "- [本版本 TiledCamera 别名](source/tiled-current.html#L1)；优先依据实际安装源码，不能将旧版本教程当作本地新能力。",
        "- [GPU PhysX 设置](source/physx-device.html#L575) 与 [相机实际渲染调用](source/camera-render-current.html#L552)。",
        "- PyTorch 的 [异步复制说明](https://docs.pytorch.org/tutorials/intermediate/pinmem_nonblock.html) 要求 D2H 后在 CPU 访问前确认完成；pinned memory 与 non_blocking 需要配合正确的生命周期。",
        "- NVIDIA 的 [CUDA 最佳实践](https://docs.nvidia.com/cuda/archive/13.0.1/cuda-c-best-practices-guide/index.html) 说明复制/计算重叠依赖设备能力、pinned 内存与流的独立性；同帧数据依赖仍需正确同步。",
        "- [Nsight Systems 用户指南](https://docs.nvidia.com/nsight-systems/UserGuide/index.html) 支持 CPU、CUDA 与图形 API 的时间线关联，适合区分提交空隙、设备工作和同步。", ""]
    return "\n".join(lines)


def render_analysis(text):
    import markdown
    body = markdown.markdown(text, extensions=["tables", "fenced_code"])
    style = "body{font:16px/1.85 system-ui,sans-serif;max-width:1250px;margin:32px auto;padding:24px;background:#f7f9fc;color:#24384d}h2{margin-top:42px;color:#197c88}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid #cbd5e1;text-align:left}th{background:#e4edf5}a{color:#245da0}code{overflow-wrap:anywhere}"
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v1 内部耗时与加速方案</title><style>' + style + '</style><body><nav><a href="charts.html">图册</a> · <a href="charts.pdf">PDF</a> · <a href="index.html">完整报告</a></nav>' + body + '</body></html>'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("paired", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.source.resolve(), args.paired.resolve(), args.destination.resolve())
