"""Validate every factorial cell, render comparable evidence and seal a local report."""
import argparse
import csv
import datetime
import hashlib
import html
import json
import shutil
import subprocess
import importlib.metadata as metadata
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from metrics import PICK_POSITIONS, TARGET_XY, BLOCK_CENTER, BLOCK_HALF, summarize_cells


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_case(case):
    root=Path(case["output"])
    with h5py.File(root/"episodes.hdf5", "r") as f:
        assert list(f["data"])==["demo_0"]
        d=f["data/demo_0"];o=d["obs"];n=len(d["actions"])
        assert n==case["result"]["frames"]==d.attrs["num_samples"]
        assert all(len(v)==n for v in o.values())
        assert np.isfinite(d["actions"][:]).all()
        assert all(np.isfinite(v[:]).all() for v in o.values())
        state=o["cube_state"][:];final=state[-50:]
        lifted=bool(state[:,2].max()-state[30,2]>.15)
        placed=bool((np.abs(final[:,:2]-TARGET_XY)<.04).all() and
                    (np.abs(final[:,2]-.02)<.015).all() and
                    (np.linalg.norm(final[:,7:10],axis=-1)<.02).all())
        names=json.loads(d.attrs["joint_names"])
        fingers=[i for i,name in enumerate(names) if name.startswith("panda_finger")]
        released=bool((o["joint_pos"][-50:][:,fingers]>.035).all())
        withdrawn=bool((np.linalg.norm(o["tcp_pose"][-50:,:3]-final[:,:3],axis=-1)>.15).all())
        task=lifted and placed and released and withdrawn
        peak=float(o["blocker_contact_n"][:].max())
        safe=task and peak<1.0
        assert task==bool(d.attrs["success"])==case["result"]["success"]
        assert safe==case["result"]["collision_free_success"]
        assert abs(peak-case["result"]["peak_blocker_contact_n"])<1e-3
        paths=dict(cube=state[:,:3],tcp=o["tcp_pose"][:,:3],phase=o["phase"][:],force=o["blocker_contact_n"][:])
    videos={}
    for camera in ("overview","detail"):
        reader=imageio_ffmpeg.read_frames(str(root/(camera+".mp4")),pix_fmt="rgb24")
        meta=next(reader);count=sum(1 for _ in reader)
        assert count==n and abs(meta["fps"]-50)<.01
        videos[camera]=dict(frames=count,size=list(meta["size"]),fps=meta["fps"],sha256=digest(root/(camera+".mp4")))
    evidence=dict(task_success=task,collision_free_success=safe,lift_m=float(state[:,2].max()-state[30,2]),
                  actual_fingers_open=released,tool_withdrawn=withdrawn,peak_blocker_contact_n=peak,
                  dataset_sha256=digest(root/"episodes.hdf5"),videos=videos)
    return evidence,paths


def comparison_video(cases, output):
    order=[("ik",False),("curobo",False),("ik",True),("curobo",True)]
    chosen=[next(c for c in cases if (c["method"],c["obstacle"],c["trial"])==(m,b,0)) for m,b in order]
    readers=[];metadata=[];last=[None]*4
    for case in chosen:
        reader=imageio_ffmpeg.read_frames(str(Path(case["output"])/"overview.mp4"),pix_fmt="rgb24",input_params=["-threads","2"])
        metadata.append(next(reader));readers.append(reader)
    writer=imageio_ffmpeg.write_frames(str(output/"comparison.mp4"),(960,600),fps=50,codec="libx264",
        macro_block_size=1,pix_fmt_in="rgb24",output_params=["-crf","21","-threads","2"])
    writer.send(None)
    length=max(c["result"]["frames"] for c in chosen)
    try:
        for frame in range(length):
            sheet=Image.new("RGB",(960,600),"white");draw=ImageDraw.Draw(sheet)
            for i,(reader,case,meta) in enumerate(zip(readers,chosen,metadata)):
                raw=next(reader,None)
                if raw is not None:
                    last[i]=Image.frombytes("RGB",tuple(meta["size"]),raw).resize((480,270))
                assert last[i] is not None
                x,y=(i%2)*480,(i//2)*300
                sheet.paste(last[i],(x,y+30))
                condition="obstacle" if case["obstacle"] else "clear"
                suffix=" (last frame held)" if raw is None else ""
                status="PASS" if case["result"]["collision_free_success"] else ("CONTACT" if case["result"]["peak_blocker_contact_n"]>=1 else "FAIL")
                draw.text((x+8,y+8),f'{case["method"].upper()} / {condition} / {status} / t={frame/50:.2f}s'+suffix,fill="black")
            writer.send(np.asarray(sheet))
            if frame==min(540,length-1):
                sheet.save(output/"comparison.png")
    finally:
        writer.close()
        for reader in readers:
            reader.close()
    return dict(frames=length,fps=50,padding="shorter cases hold their final frame; original videos remain unmodified")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",nargs="+",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    manifests=[json.loads((p/"manifest.json").read_text()) for p in args.runs]
    assert all(m["source_sha256"]==manifests[0]["source_sha256"] for m in manifests),"Mixed runtime revisions"
    cases=[c for m in manifests for c in m["cases"]]
    source_folder=Path(__file__).resolve().parent
    assert all(digest(source_folder/name)==value for name,value in manifests[0]["source_sha256"].items()),"Current runtime source differs from experiment"
    assert all(c["result"]["source_sha256"]==manifests[0]["source_sha256"]["capture.py"] for c in cases if c["status"]=="completed")
    assert all((c["method"],c["obstacle"],c["trial"])==(c["result"]["method"],c["result"]["obstacle"],c["result"]["trial"]) for c in cases if c["status"]=="completed")
    identities=[(c["method"],c["obstacle"],c["trial"]) for c in cases]
    expected={(m,b,t) for m in ("ik","curobo") for b in (False,True) for t in range(3)}
    assert len(cases)==12 and len(set(identities))==12 and set(identities)==expected
    assert all(c["status"]=="completed" for c in cases),"Incomplete cases: no aggregate success claim"
    args.output.mkdir(parents=True,exist_ok=False)
    evidence={};traces={}
    for case in cases:
        evidence[case["name"]],traces[case["name"]]=validate_case(case)
    for trial in range(3):
        paired=[c for c in cases if c["trial"]==trial]
        q=paired[0]["result"]["initial_robot_joint_pos"]
        cube=paired[0]["result"]["initial_cube_state"]
        for c in paired:
            np.testing.assert_allclose(c["result"]["initial_robot_joint_pos"],q,atol=1e-6,rtol=0)
            np.testing.assert_allclose(c["result"]["initial_cube_state"],cube,atol=1e-6,rtol=0)
    cells=summarize_cells(cases)
    summary=dict(cells=cells,paired_initial_states_verified=True,trial_pick_xy=PICK_POSITIONS,
                 target_xy=TARGET_XY,obstacle_center=BLOCK_CENTER.tolist(),obstacle_dimensions=(2*BLOCK_HALF).tolist(),
                 runtime_source_sha256=manifests[0]["source_sha256"],case_evidence=evidence,
                 limitations=["Three fixed paired states, not a population success-rate estimate",
                     "cuRobo uses local floor/table/blocker proxies; full home mesh is not imported into the planner",
                     "Obstacle contact criterion is >=1 N; it does not certify absence of every possible self/table contact",
                     "Each independent cuRobo worker is initialized/warmed, then makes its first actual attached-object requests",
                     "Physics is simulated; no real robot evaluation or learned policy inference"])
    prepared=json.loads((Path(cases[0]["result"]["home"]).parent/"manifest.json").read_text())
    assert digest(prepared["home"])==prepared["home_sha256"]
    assert digest(prepared["layer"])==prepared["layer_sha256"]
    planner_python=manifests[0]["args"]["planner_python"]
    meta_script="import json,importlib.metadata as m,importlib.util as u;print(json.dumps(dict(versions={k:m.version(k) for k in ['nvidia-curobo','torch']},curobo_file=u.find_spec('curobo').origin)))"
    planner_metadata=json.loads(subprocess.check_output([planner_python,"-c",meta_script],text=True))
    curobo_root=Path(planner_metadata["curobo_file"]).parent
    model_paths=[curobo_root/"content/configs/robot/franka.yml",
                 curobo_root/"content/configs/robot/spheres/franka_mesh.yml",
                 curobo_root/"content/assets/robot/franka_description/franka_panda.urdf",
                 curobo_root/"wrap/reacher/motion_gen.py"]
    runtime_metadata=dict(gpu=manifests[0].get("gpu_info"),
        simulation={k:metadata.version(k) for k in ("isaacsim","isaaclab","torch","h5py")},
        planner=planner_metadata,planner_model_sha256={str(p):digest(p) for p in model_paths},
        original_scene=prepared,
        all_case_gpu_preflight_empty=all(not c.get("foreign_gpu_before",["unknown"]) for c in cases))
    summary["runtime"]=runtime_metadata
    rows=[]
    for c in cases:
        r=c["result"]
        rows.append(dict(name=c["name"],method=c["method"],obstacle=c["obstacle"],trial=c["trial"],
            success=r["success"],collision_free_success=r["collision_free_success"],planning_failed=r["planning_failed"],
            peak_obstacle_contact_n=r["peak_blocker_contact_n"],contact_steps=r["blocker_contact_steps"],
            simulated_seconds=r["seconds"],process_wall_s=c["process_wall_s"],
            planning_s=sum(p.get("synchronized_request_s",0) for p in r["planning"]),
            transfer_plan_s=sum(p.get("synchronized_request_s",0) for p in r["planning"] if p.get("phase")=="transfer"),
            preplace_plan_s=sum(p.get("synchronized_request_s",0) for p in r["planning"] if p.get("phase")=="lower_prepare"),
            initialization_s=r["planner_initialization_s"],worker_startup_s=r["planner_startup_wall_s"],joint_path_rad=r["trajectory"]["joint_path_rad"],
            tcp_path_m=r["trajectory"]["tcp_path_m"],control_compute_s=r["control_compute_s"],
            output=c["output"]))
    with (args.output/"cases.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig=plt.figure(figsize=(11,4.5),constrained_layout=True)
    axes=[fig.add_subplot(121),fig.add_subplot(122,projection="3d")]
    labels=[f'{c["method"].upper()}\n'+("blocked" if c["obstacle"] else "clear") for c in cells]
    x=np.arange(4)
    axes[0].bar(x-.18,[c["task_successes"] for c in cells],width=.36,label="Task complete",color="#68a8db")
    axes[0].bar(x+.18,[c["collision_free_successes"] for c in cells],width=.36,label="Complete, no obstacle contact",color="#39a875")
    axes[0].set(xticks=x,xticklabels=labels,ylim=(0,3.6),yticks=range(4),ylabel="Successful cases out of 3")
    axes[0].legend(fontsize=8,loc="upper left")
    for method,color in (("ik","#d97831"),("curobo","#2582b9")):
        c=next(c for c in cases if c["method"]==method and c["obstacle"] and c["trial"]==0)
        trace=traces[c["name"]]
        # All transport/pre-place movement after the common lift and before release.
        mask=(trace["phase"]>=4)&(trace["phase"]<=6)
        axes[1].plot(trace["cube"][mask,0],trace["cube"][mask,1],trace["cube"][mask,2],label=method.upper(),color=color,lw=2)
    corner=BLOCK_CENTER-BLOCK_HALF
    axes[1].bar3d(*corner,*(2*BLOCK_HALF),alpha=.18,color="#426ad0",shade=True)
    axes[1].set(xlabel="X (m)",ylabel="Y (m)",zlabel="Z (m)",title="Actual payload motion, blocked trial 0")
    axes[1].view_init(elev=23,azim=-57)
    axes[1].legend(fontsize=8)
    fig.savefig(args.output/"results.png",dpi=170)
    fig.savefig(args.output/"results.svg")
    plt.close(fig)
    summary["comparison_video"]=comparison_video(cases,args.output)
    for case in cases:
        if case["trial"]==0:
            label=f'{case["method"]}_{"blocked" if case["obstacle"] else "clear"}'
            shutil.copyfile(Path(case["output"])/"detail.mp4",args.output/f"{label}_detail.mp4")
    (args.output/"summary.json").write_text(json.dumps(summary,indent=2))
    table=["| 方法 | 新增障碍物 | 完成尝试 | 任务完成 | 无障碍物接触完成 | 平均规划请求 ms | 模型构建/预热 s | 平均仿真时长 s |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in cells:
        planning=f'{c["mean_planning_s"]*1000:.1f}' if c["mean_planning_s"] is not None else "不适用"
        initialization=f'{c["mean_initialization_s"]:.2f}' if c["method"]=="curobo" else "不适用"
        table.append(f'| {c["method"].upper()} | {"有" if c["obstacle"] else "无"} | {c["completed"]}/{c["planned"]} | {c["task_successes"]}/3 | {c["collision_free_successes"]}/3 | {planning} | {initialization} | {c["mean_sim_seconds"]:.2f} |')
    body="\n".join(table)
    lookup={(c["method"],c["obstacle"]):c for c in cells}
    headline=(f'无新增障碍时，IK 与 cuRobo 分别完成 {lookup[("ik",False)]["task_successes"]}/3、{lookup[("curobo",False)]["task_successes"]}/3；'
              f'有障碍时，无障碍物接触完成分别为 {lookup[("ik",True)]["collision_free_successes"]}/3、{lookup[("curobo",True)]["collision_free_successes"]}/3。')
    report=f'''# Franka 家庭场景：IK 与 cuRobo、有无障碍物对比

日期：2026-10-17。真实执行 12 次仿真，每组 3 个固定配对初始位置。结果只描述这些状态。

{headline}

## 实测结果

{body}

![结果与实际物体轨迹](results.png)

[四组同步对比视频](comparison.mp4) · [逐次结果 CSV](cases.csv) · [验证证据](summary.json)

单路近景：[IK 无障碍](ik_clear_detail.mp4) · [cuRobo 无障碍](curobo_clear_detail.mp4) · [IK 有障碍](ik_blocked_detail.mp4) · [cuRobo 有障碍](curobo_blocked_detail.mp4)

## 实验设计与控制变量

场景为 Yootta/World-SimReady-Home-mini 的 scene000430，固定 revision f2c633749e7fdf3f981dfd1dd83fc253786713ac。
原数据集：[Hugging Face](https://huggingface.co/datasets/Yootta/World-SimReady-Home-mini)。
使用派生静态住宅：停用餐桌椅子、桌面装饰、天花板及原灯光，冻结家具动态与关节，保留家具静态碰撞并补光。原始 USDZ 不改写，四组使用相同派生场景。
Franka Panda 安装于原生餐桌，方块 4 cm、50 g。物理积分 .005 s，四次积分构成 50 Hz 控制步。
三组抓取 XY 为 {list(PICK_POSITIONS)}，目标 XY 为 {TARGET_XY}；四种方法/障碍条件的初始机器人和物体状态已逐项核对，误差不超过 1e-6。
蓝色障碍物尺寸为 16×4×32 cm，中心为 {BLOCK_CENTER.tolist()}，是固定的物理碰撞体。
场景、机械臂 PD、物体质量/摩擦、相机和成功阈值保持相同。机械臂与物体只在初始化设置状态，之后通过关节目标与接触物理运动。

IK 使用局部 DLS 控制。cuRobo 方案在横移和下降至桌面上方 7.5 cm 的预放置阶段查询 MotionGen，再执行其关节轨迹；最后 4.9 cm 下降、松爪与撤回仍共用 IK 接触控制。
规划器采用现有 v1 API 环境，4 TrajOpt seeds、4 graph seeds、32 IK seeds、32 优化节点、20 mm 碰撞激活距离，最多 4 次尝试、20 秒请求上限。
搬运物体用保守的 35 mm 碰撞球表示，只改变规划碰撞模型，不给仿真方块添加约束。
cuRobo URDF 与仿真在每次请求前进行 FK 核对，位置误差须小于 3 mm、转角误差小于 .03 rad。

## 成功、碰撞与计时口径

任务完成要求物体曾抬高超过 15 cm，并在最后连续 50 步位于目标 XY ±4 cm、桌面上 z=.02±.015 m 内，速度低于 .02 m/s；保存后另查实际松爪与 TCP 撤回超过 15 cm。
无障碍物接触完成还要求新增障碍物与机器人/方块接触力全程小于 1 N。每个物理子步读取过滤接触力，保存每控制步峰值；它不等于全场景所有类型碰撞都已验收。
独立读回所有 HDF5 状态，核对有限数、成功标签与接触峰值，并重新解码两路视频检查每帧数量及 50 Hz 帧率。
完成的规划失败保留在分母；启动/接口错误属于执行失败，不能冒充任务失败率。

规划请求计时前后 CUDA 同步，包含本次 FK/负载碰撞模型更新和规划；模型构建/预热单列，不含 Python 与库导入，完整工作进程启动时间另存 CSV。每个独立进程中的实际请求仍可能首次触发带物体代码路径，不能称为完全稳态内核计时。
GPU：{runtime_metadata['gpu']}。每次样本开始前 GPU 计算进程列表均为空：{runtime_metadata['all_case_gpu_preflight_empty']}；这不证明全部 CPU/驱动负载都被隔离。
IK 没有对应的全局规划调用，因此该列为不适用。逐步控制计算与包含启动/视频/IPC 的墙钟时间见 CSV，不能把它们当成同一个计时指标。
cuRobo 轨迹只会放慢，不加速至超过原规划时间，并保留目标末端保持段；仿真时长的差异随每次结果记录。
同步视频按相同 50 Hz 起点对齐，较短样本末尾保持最终画面；原视频保留，不改写原始轨迹。

## 范围与限制

cuRobo 本次建模范围为桌面、地面与新增障碍物的近场代理几何，桌面安装位置留出固定底座孔。住宅完整网格保留在物理仿真，但没有全部导入规划器；这不是整屋导航或完整家具避障测试。
这是脚本抓取配合规划的仿真数据生产对照，不涉及训练策略或真实机器人。3 个固定状态不足以推断总体成功率或统计显著性。
机器人模型、原始 USDZ 和上游源码不改写，依赖不更新、不安装；原始数据集为 CC-BY-NC-SA-4.0，资产未重新分发。

## 复现与溯源

正式实验之前进行了接口和流程试跑。仅规划横移的版本在横移段无接触，但共用 IK 下放仍碰到障碍，因此正式方案把规划覆盖到预放置，末段接触保持共用控制。试跑数据与最终 12 次尝试分开保存，不混入本表。

源码入口：workspace-overlays/franka-curobo-comparison/README.md。配置、运行目录、逐次状态与源文件哈希见 provenance.json；HDF5 与两路原视频本机另存。
本报告未上传飞书、ChatGPT 或发布站点。代码自审与自动检查不等同于独立审阅批准。
'''
    (args.output/"report.md").write_text(report)
    html_table="<table>"+"".join("<tr>"+"".join(f"<td>{html.escape(v.strip())}</td>" for v in row.strip("|").split("|"))+"</tr>" for row in table if "---" not in row)+"</table>"
    (args.output/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>Franka cuRobo 对比</title><style>body{max-width:1100px;margin:40px auto;font:17px/1.7 sans-serif;color:#203048}td{padding:10px;border-bottom:1px solid #ddd}img,video{max-width:100%}a{color:#1760a0}</style><h1>Franka：IK × cuRobo × 障碍物</h1><p>12 次实际仿真，3 个固定配对状态；范围与口径见完整报告。</p>'+html_table+'<video controls src="comparison.mp4" poster="comparison.png"></video><img src="results.png"><p><a href="report.md">完整报告</a> · <a href="cases.csv">逐次 CSV</a> · <a href="summary.json">验证结果</a></p>')
    (args.output/"provenance.json").write_text(json.dumps(dict(manifests=manifests,evidence=evidence,runtime=runtime_metadata,
        runtime_source_sha256=manifests[0]["source_sha256"]),indent=2))
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    manifest=dict(schema_version=1,artifact_id="franka-curobo-home-comparison",version=args.output.name,
        created_at=now,sealed_at=now,sources=[str(p.resolve()) for p in args.runs],
        files={str(p.relative_to(args.output)):digest(p) for p in sorted(args.output.rglob("*")) if p.is_file()},
        validation=dict(all_12_attempts_completed=True,paired_initial_states=True,state_and_video_readback=True),
        delivery=dict(local=dict(status="saved")))
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(dict(output=str(args.output.resolve()),cells=cells),indent=2))


if __name__=="__main__":
    main()
