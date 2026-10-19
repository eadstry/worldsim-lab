# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check accounting closure and produce the paired local timing report."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

LABELS = {
    "physics_step": "物理推进（主机调用）", "render": "sim.render 调度与回调",
    "camera_pose": "相机位姿更新", "rgb_readback_other": "RGB 读取包装其余开销",
    "camera_render": "相机实际渲染（主机调用）", "camera_output_read": "渲染器输出读取",
    "render_scene_transforms": "渲染场景变换同步", "camera_data_other": "相机数据更新其余开销",
    "rgb_cpu_copy": "RGB GPU→CPU 复制（含等待）",
    "observation_other": "其余观测计算", "record_buffer_copy": "记录缓冲复制与追加",
    "record_pre_other": "逐帧记录前处理", "record_post_other": "逐帧记录后处理",
    "action_process": "环境动作处理", "action_apply": "控制器施加动作",
    "scene_write": "场景数据写入仿真", "scene_update": "场景状态更新",
    "action_prepare": "目标位姿转动作", "success_check": "成功条件检查",
    "env_step_other": "env.step 其余开销", "reset_other": "环境重置其余开销",
    "motion_plan": "运动规划", "export_producer_other": "同步导出／异步提交其余开销",
    "export_pack": "导出共享内存打包", "export_poll_or_backpressure": "导出轮询／背压",
    "export_merge": "异步分片合并", "export_drain_other": "异步排空其余开销",
    "scheduler_other": "协程调度及未细分的生成逻辑", "unattributed": "主循环未细分开销",
    "env_close_other": "环境关闭其余开销",
}
GROUPS = {
    "export": ("导出与背压", {"export_producer_other", "export_pack", "export_poll_or_backpressure", "export_drain_other", "export_merge"}),
    "camera": ("相机渲染与图像采集", {"camera_pose", "camera_render", "camera_output_read", "render_scene_transforms", "camera_data_other", "rgb_cpu_copy", "rgb_readback_other", "render"}),
    "physics": ("物理推进与控制", {"physics_step", "action_process", "action_apply", "scene_write", "scene_update"}),
    "record_observation": ("记录缓冲与其余观测", {"record_buffer_copy", "record_pre_other", "record_post_other", "observation_other"}),
    "planner_reset": ("规划与重置", {"motion_plan", "reset_other"}),
    "action_success": ("动作准备与成功检查", {"action_prepare", "success_check"}),
    "remaining": ("调度及其余开销", {"scheduler_other", "unattributed", "env_step_other", "env_close_other"}),
}


def read(path):
    return json.loads(path.read_text())


def analyze(directory):
    plan = read(directory / "experiment.json")
    results = []
    for variant in plan["variants"]:
        output = directory / variant["name"] / "episodes.hdf5"
        profile = read(output.with_suffix(".internal-summary.json"))
        run = read(output.with_suffix(".run.json"))
        status = read(output.with_suffix(".status.json"))
        telemetry = [json.loads(line) for line in output.with_suffix(".telemetry.jsonl").read_text().splitlines()]
        complete = [r for r in telemetry if r["event"] == "episode_finished"]
        episodes = [r for r in profile["episodes"] if r["outcome"] == "episode_finished"]
        assert run["status"] == "succeeded" and profile["final"]
        assert run["config"]["num_envs"] == plan["num_envs"]
        assert run["config"]["generation_num_trials"] == plan["target_successes"]
        assert run["config"]["final_hold_steps"] == plan["final_hold_steps"]
        assert str(run["config"]["export_workers"]) == variant["workers"]
        assert run["config"]["input_file"] == plan["source_input"]
        assert len(episodes) == len(complete) and len(episodes) > 0
        assert {r["episode_id"] for r in episodes} == {r["episode_id"] for r in complete}
        for window in (profile["generation"], profile["through_output_ready"]):
            error = abs(sum(window["exclusive_wall_seconds"].values()) - window["wall_seconds"])
            assert error < 1e-5, f"Master timing does not close: {error}"
        parts = Counter()
        for episode in episodes:
            assert episode["execute_calls"] > 0
            error = abs(sum(episode["exclusive_during_execute_seconds"].values()) - episode["execute_wall_seconds"])
            assert error < 1e-5, f"Execute timing does not close: {error}"
            assert 0 <= episode["queue_join_seconds"] <= episode["execute_wall_seconds"]
            # The outer wrapper includes telemetry progress emission and its own
            # bookkeeping; retain rather than silently hide this measured delta.
            parts.update(episode["exclusive_during_execute_seconds"])
        first = next(r for r in telemetry if r["event"] == "episode_started")
        ready = next(r for r in reversed(telemetry) if r["event"] == "output_ready")
        successes = sum(r["success"] is True for r in complete)
        final_seconds = ready["elapsed_seconds"] - first["elapsed_seconds"]
        n = len(episodes)
        total_execute = sum(r["execute_wall_seconds"] for r in episodes)
        steps = sum(r["execution_steps"] for r in complete)
        result = {"name": variant["name"], "workers": variant["workers"], "episodes": n,
                  "successes": successes, "failures": n - successes,
                  "final_ready_seconds": final_seconds,
                  "final_ready_successes_per_minute": successes * 60 / final_seconds,
                  "launcher_wall_seconds": variant["launcher_wall_seconds"],
                  "producer_peak_rss_gib": status["resource_summary"]["peak_rss_bytes"] / 1024**3,
                  "mean_episode_seconds": sum(r["duration_seconds"] for r in complete) / n,
                  "mean_execute_seconds": total_execute / n,
                  "mean_telemetry_execute_seconds": sum(r["telemetry_execute_seconds"] for r in episodes) / n,
                  "mean_execution_steps": sum(r["execution_steps"] for r in complete) / n,
                  "mean_queue_join_seconds": sum(r["queue_join_seconds"] for r in episodes) / n,
                  "queue_join_fraction_of_execute": sum(r["queue_join_seconds"] for r in episodes) / total_execute,
                  "execute_phase_mean_seconds": {k: v / n for k, v in parts.items()},
                  "execute_phase_fraction": {k: v / total_execute for k, v in parts.items()},
                  "execute_phase_ms_per_step": {k: v * 1000 / steps for k, v in parts.items()},
                  "generation": profile["generation"], "through_output_ready": profile["through_output_ready"],
                  "calls": profile["calls"], "inclusive_wall_seconds": profile["inclusive_wall_seconds"],
                  "physical_validation_passed": variant["physical_validation_returncode"] == 0,
                  "schema_validation_passed": variant["schema_validation_returncode"] == 0,
                  "accounting_closure_passed": True,
                  "file_bytes": output.stat().st_size, "profile": str(output.with_suffix('.internal-summary.json'))}
        result["execute_groups"] = {
            key: {"label": label, "seconds_per_episode": sum(parts[k] for k in phases) / n,
                  "fraction": sum(parts[k] for k in phases) / total_execute}
            for key, (label, phases) in GROUPS.items()}
        assert abs(sum(g["fraction"] for g in result["execute_groups"].values()) - 1) < 1e-8
        step_calls = profile["calls"]["env_step_other"]
        result["call_rates"] = {
            "batch_env_steps": step_calls,
            "observation_computes_per_batch_step_including_resets": profile["calls"]["observation_other"] / step_calls,
            "rgb_copies_per_batch_step_including_resets": profile["calls"]["rgb_cpu_copy"] / step_calls,
            "camera_renders_per_batch_step_including_resets": profile["calls"]["camera_render"] / step_calls,
            "camera_pose_update_calls_per_batch_step_including_resets": profile["calls"]["camera_pose"] / step_calls,
        }
        results.append(result)
    before, after = results
    pair_check_path = directory / "pair-data-check.json"
    pair_check = read(pair_check_path) if pair_check_path.exists() else None
    report = {"experiment": str(directory / "experiment.json"), "runs": results,
              "throughput_speedup": after["final_ready_successes_per_minute"] / before["final_ready_successes_per_minute"],
              "validation_passed": all(r["physical_validation_passed"] and r["schema_validation_passed"] for r in results),
              "pair_data_check": pair_check}
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ["# v1 改进前后内部耗时对照实验", "",
             f"本次 {plan['num_envs']} 环境配对测试中，平均 execute 累计时间由 {before['mean_execute_seconds']:.2f} 秒变为 {after['mean_execute_seconds']:.2f} 秒；其中等待窗口内的导出与背压由 {before['execute_groups']['export']['seconds_per_episode']:.2f} 秒变为 {after['execute_groups']['export']['seconds_per_episode']:.2f} 秒。改进后相机渲染与图像采集占 execute 内部的 {after['execute_groups']['camera']['fraction']*100:.1f}%，物理推进与控制占 {after['execute_groups']['physics']['fraction']*100:.1f}%。", "",
             f"改进前为冻结 v1 的同步导出；改进后为同一 v1 的自动扩展多进程异步导出，并包含该路径既有的 CPU 记录缓冲所有权优化。两组使用相同计时钩子、输入 SHA256、任务 YAML、seed=101、{plan['num_envs']} 个环境、{plan['target_successes']} 个成功目标和 60 个最终保持步，按改进前→改进后依次运行。", "",
             "这是固定 seed 的一次配对实验。测量的是主机调用的墙钟延迟，没有新增 CUDA 同步；GPU 工作可能在后续读取时才产生阻塞，因此各行不能解释为隔离的 GPU kernel 用时。", "",
             "## 运行结果", "", "| 指标 | 改进前：同步导出 | 改进后：auto 导出 |", "|---|---:|---:|"]
    for label, key in (("成功数", "successes"), ("失败数", "failures"),
                       ("最终文件就绪秒数（首 episode 起）", "final_ready_seconds"),
                       ("最终文件吞吐（成功数/分钟）", "final_ready_successes_per_minute"),
                       ("平均 episode 秒数", "mean_episode_seconds"),
                       ("平均 execute 累计秒数", "mean_execute_seconds"),
                       ("平均执行步数", "mean_execution_steps"),
                       ("平均 queue.join 秒数（嵌套）", "mean_queue_join_seconds")):
        if key in ("successes", "failures"):
            lines.append(f"| {label} | {before[key]} | {after[key]} |")
        else:
            lines.append(f"| {label} | {before[key]:.3f} | {after[key]:.3f} |")
    lines.append(f"| 生产主进程峰值 RSS GiB（采样） | {before['producer_peak_rss_gib']:.2f} | {after['producer_peak_rss_gib']:.2f} |")
    if pair_check:
        lines += ["", f"动作序列精确匹配 {pair_check['exact_action_sequence_matches']} 组（按完整 actions 数组 SHA256 匹配，不依赖导出编号）。三路 RGB 均为 640×480 uint8、gzip level 2；像素内容未作逐帧比较。"]
    lines += ["", f"最终文件吞吐比值：{report['throughput_speedup']:.3f} 倍；变化 {(report['throughput_speedup']-1)*100:+.1f}%。",
              f"物理与文件结构验证：{'两组均通过' if report['validation_passed'] else '存在未通过项，不能视为通过验收'}。", "",
              f"平均 execute 减少 {before['mean_execute_seconds']-after['mean_execute_seconds']:.2f} 秒，其中导出与背压归因减少 {before['execute_groups']['export']['seconds_per_episode']-after['execute_groups']['export']['seconds_per_episode']:.2f} 秒。相机与物理控制的绝对耗时变化较小，加速主要来自同步导出对其他环境阻塞的减少；相机占比升高主要是总时间缩短所致。", "",
              "## execute 内部归因", "",
              f"每次 execute 从入口到返回期间，对主线程实际执行的同步环节做互斥计时；包括其他环境在该等待窗口内的规划、重置和导出。这里回答的是“等待时主程序在做什么”。{plan['num_envs']} 个环境的窗口会重叠，表中各行可在单个窗口内相加，但不能跨环境相加得到整批墙钟。", "",
              "| 汇总环节 | 改进前秒/episode | 内部占比 | 改进后秒/episode | 内部占比 |", "|---|---:|---:|---:|---:|"]
    for key, (label, _) in GROUPS.items():
        a,b = before["execute_groups"][key],after["execute_groups"][key]
        lines.append(f"| {label} | {a['seconds_per_episode']:.3f} | {a['fraction']*100:.2f}% | {b['seconds_per_episode']:.3f} | {b['fraction']*100:.2f}% |")
    lines += ["", "### 各调用的详细耗时", "",
              "| 环节 | 改进前秒/episode | 内部占比 | 改进后秒/episode | 内部占比 |", "|---|---:|---:|---:|---:|"]
    keys = sorted(before["execute_phase_mean_seconds"].keys() | after["execute_phase_mean_seconds"].keys(),
                  key=lambda k: -(before["execute_phase_mean_seconds"].get(k, 0) + after["execute_phase_mean_seconds"].get(k, 0)))
    csv_rows = []
    for k in keys:
        a, b = before["execute_phase_mean_seconds"].get(k, 0), after["execute_phase_mean_seconds"].get(k, 0)
        pa, pb = before["execute_phase_fraction"].get(k, 0), after["execute_phase_fraction"].get(k, 0)
        lines.append(f"| {LABELS.get(k,k)} | {a:.3f} | {pa*100:.2f}% | {b:.3f} | {pb*100:.2f}% |")
        csv_rows.append([k, LABELS.get(k,k), a, pa, b, pb])
    lines += [f"| 合计 | {before['mean_execute_seconds']:.3f} | 100% | {after['mean_execute_seconds']:.3f} | 100% |", "",
              f"queue.join 等待分别占 execute 的 {before['queue_join_fraction_of_execute']*100:.2f}% 和 {after['queue_join_fraction_of_execute']*100:.2f}%。这是包含仿真等工作的逻辑等待，已被上表归因覆盖，不能再加到上表。", "",
              "## 主循环独占墙钟分解", "",
              "从主仿真循环进入到退出，不重复计算并发 episode，子环节从父环节扣除。包括最终目标达成时仍在进行的 episode；不包含启动和循环退出后的异步排空。", "",
              "| 环节 | 改进前总秒数 | 占循环墙钟 | 改进后总秒数 | 占循环墙钟 |", "|---|---:|---:|---:|---:|"]
    a = before["generation"]; b = after["generation"]
    for k in sorted(a["exclusive_wall_seconds"].keys() | b["exclusive_wall_seconds"].keys(),
                    key=lambda k: -(a["exclusive_wall_seconds"].get(k,0)+b["exclusive_wall_seconds"].get(k,0))):
        av,bv=a["exclusive_wall_seconds"].get(k,0),b["exclusive_wall_seconds"].get(k,0)
        lines.append(f"| {LABELS.get(k,k)} | {av:.3f} | {av/a['wall_seconds']*100:.2f}% | {bv:.3f} | {bv/b['wall_seconds']*100:.2f}% |")
    lines += [f"| 合计 | {a['wall_seconds']:.3f} | 100% | {b['wall_seconds']:.3f} | 100% |", "",
              "## 主线程 CPU 时间", "",
              "线程 CPU 时间记录主线程实际被 CPU 调度执行的时长。墙钟减去线程 CPU 时间包含 GPU 或其他线程等待、I/O 和调度延迟，不能全部命名为 GPU 等待；其他 CPU 线程和导出进程的计算不在该线程计数中。", "",
              "| 主循环指标 | 改进前 | 改进后 |", "|---|---:|---:|",
              f"| 主线程 CPU 秒数 | {sum(a['exclusive_thread_cpu_seconds'].values()):.3f} | {sum(b['exclusive_thread_cpu_seconds'].values()):.3f} |",
              f"| 主线程 CPU 时间 / 循环墙钟 | {sum(a['exclusive_thread_cpu_seconds'].values())/a['wall_seconds']*100:.2f}% | {sum(b['exclusive_thread_cpu_seconds'].values())/b['wall_seconds']*100:.2f}% |", "",
              "| 调用环节 | 改进前线程 CPU / 该环节墙钟 | 改进后线程 CPU / 该环节墙钟 |", "|---|---:|---:|"]
    for phase in ("export_producer_other", "camera_pose", "camera_render", "rgb_cpu_copy", "physics_step", "record_buffer_copy"):
        aw,bw=a['exclusive_wall_seconds'].get(phase,0),b['exclusive_wall_seconds'].get(phase,0)
        ac,bc=a['exclusive_thread_cpu_seconds'].get(phase,0),b['exclusive_thread_cpu_seconds'].get(phase,0)
        lines.append(f"| {LABELS[phase]} | {ac/aw*100 if aw else 0:.2f}% | {bc/bw*100 if bw else 0:.2f}% |")
    lines += ["",
              "## 相机调用的实际来源", "",
              "当前 ManagerBasedRLEnv.step 在启用 recorder 时，先计算一次观测供记录，再在步骤末尾计算一次观测。每次观测读取三路 RGB；rgb_image 每次读取又更新所有三台相机的位姿。因此正常批次步内会计算两次观测、复制六批 RGB、执行六次全相机位姿更新。相机渲染缓存避免每次重复读取都重新渲染，但重复位姿计算和 CPU 拷贝仍有成本。", "",
              f"实际调用数按批次环境步折算（含少量重置调用）：改进前观测计算 {before['call_rates']['observation_computes_per_batch_step_including_resets']:.3f} 次，RGB 复制 {before['call_rates']['rgb_copies_per_batch_step_including_resets']:.3f} 次，相机渲染 {before['call_rates']['camera_renders_per_batch_step_including_resets']:.3f} 次；改进后分别为 {after['call_rates']['observation_computes_per_batch_step_including_resets']:.3f}、{after['call_rates']['rgb_copies_per_batch_step_including_resets']:.3f}、{after['call_rates']['camera_renders_per_batch_step_including_resets']:.3f} 次。", "",
              "相机位姿和重复图像读取是后续可检查的优化方向；本实验仅测量，没有修改它们，也没有验证缓存合并后的图像与时序等价性。", "",
              "## 计时完整性和范围", "",
              "- 初始 8 环境试跑在完成首个 episode 前被 SIGKILL，最后采样进程 RSS 约 50.9 GB，cgroup OOM-kill 计数增加 1。正式两组统一使用 4 环境，试跑数据不参与对照；不能将本次百分比直接当作原图 8 环境的内部占比。",
              "- 两组主循环与最终就绪窗口的互斥计时和均与墙钟闭合，误差小于 10 微秒；每个已完成 episode 的 execute 内部分解也逐一闭合。",
              "- 相机惰性渲染在 Camera.data 读取时触发，已分别记录 renderer.render、renderer.read_output、场景变换同步及显式 GPU→CPU 复制。`rgb_readback_other` 仅为上述子环节之外的包装开销；`scene_update` 仍可能包含传感器相关工作。",
              "- `record_buffer_copy` 包含 RecorderManager.add_to_episodes 的递归处理、张量复制与追加。",
              "- `scheduler_other` 仍包含没有细分的轨迹准备和协程开销，不等同于纯空闲。",
              "- 异步 worker 的写入与主线程重叠，不加入主线程互斥占比；写入、排空和合并保留在原始导出日志。最终文件吞吐包含排空和关闭。",
              "- 钩子自身有开销，两组完全一致；未进行无钩子重跑，因此不声称测量零扰动。外层 execute 计时与原始 telemetry 的差额保存在 report.json。",
              "- 没有改变依赖环境、上游文件、历史数据或 CPU 调频策略。单次固定顺序无法排除缓存和系统漂移。", "",
              "## 原始证据", "", f"- 实验配置与源码哈希：{directory / 'experiment.json'}",
              f"- 数值结果：{directory / 'report.json'}",
              f"- 原始日志：{directory / 'before_sync'} 和 {directory / 'after_auto'}", ""]
    (directory / "report.md").write_text("\n".join(lines))
    with (directory / "execute-phases.csv").open("w") as stream:
        writer=csv.writer(stream)
        writer.writerow(["phase","label","before_seconds_per_episode","before_fraction","after_seconds_per_episode","after_fraction"])
        writer.writerows(csv_rows)
    print(json.dumps({"report":str(directory / 'report.md'),"throughput_speedup":report['throughput_speedup'],"validation_passed":report['validation_passed']}))


if __name__ == "__main__":
    analyze(Path(sys.argv[1]).resolve())
