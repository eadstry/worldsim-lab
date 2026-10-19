# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Build a local, sealed report with standard matplotlib figures; no upload."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def package(run_directory, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    import markdown

    report = json.loads((run_directory / "report.json").read_text())
    plan = json.loads((run_directory / "experiment.json").read_text())
    assert plan["state"] == "complete"
    assert all(r["accounting_closure_passed"] for r in report["runs"])
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("report.json", "report.md", "experiment.json", "execute-phases.csv"):
        shutil.copy2(run_directory / name, destination / name)
    for name in ("pair-data-check.json", "execution-notes.json"):
        if (run_directory / name).exists():
            shutil.copy2(run_directory / name, destination / name)
    evidence = destination / "evidence"
    evidence.mkdir()
    source_files = [run_directory / name for name in ("experiment.json", "report.json")]
    for variant in plan["variants"]:
        variant_directory = evidence / variant["name"]
        variant_directory.mkdir()
        for suffix in (".internal-summary.json", ".run.json", ".telemetry-summary.json", ".validation.json"):
            source = run_directory / variant["name"] / ("episodes" + suffix)
            shutil.copy2(source, variant_directory / source.name)
            source_files.append(source)
    suite = Path(__file__).resolve().parent
    code = destination / "reproduction"
    code.mkdir()
    for source in suite.glob("*.py"):
        shutil.copy2(source, code / source.name)
    shutil.copy2(suite / "README.md", code / "README.md")

    font = FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    plt.rcParams.update({"font.family":font.get_name(), "font.size":11, "axes.unicode_minus":False,
                         "svg.fonttype":"none", "figure.facecolor":"#f7f9fc", "axes.facecolor":"#f7f9fc"})
    before, after = report["runs"]
    keys = ["export", "camera", "physics", "record_observation", "planner_reset", "action_success", "remaining"]
    colors = ["#d89029", "#267d95", "#6377c3", "#77a47b", "#9a74b0", "#b5a070", "#acb6c2"]
    figure, axes = plt.subplots(2,1,figsize=(13,7), gridspec_kw={"height_ratios":[1,1]})
    for axis, percent in zip(axes, (False, True)):
        for y, row in enumerate((before,after)):
            left = 0
            for key,color in zip(keys,colors):
                group=row["execute_groups"][key]
                value=group["fraction"]*100 if percent else group["seconds_per_episode"]
                axis.barh(y,value,left=left,color=color,height=.48,label=group["label"] if y==0 else None)
                if group["fraction"]>=.085:
                    label=f"{group['fraction']*100:.1f}%" if percent else f"{value:.1f}s"
                    axis.text(left+value/2,y,label,ha="center",va="center",color="white",fontsize=11)
                left+=value
            if not percent:
                axis.text(left+1,y,f"{row['mean_execute_seconds']:.1f}s",va="center",fontsize=12)
        axis.set_yticks([0,1],["改进前 同步导出","改进后 auto 导出"])
        axis.invert_yaxis()
        axis.set_xlabel("execute 内部占比（%）" if percent else "累计秒数 / 已完成 episode")
        axis.spines[["top","right","left"]].set_visible(False)
        axis.grid(axis="x",alpha=.15)
        axis.set_axisbelow(True)
        axis.set_xlim(0,100 if percent else max(r["mean_execute_seconds"] for r in report["runs"])*1.13)
    figure.suptitle(f"v1 内部耗时对照  |  {plan['num_envs']} 环境 × {plan['target_successes']} 成功目标  |  seed {plan['seed']}",fontsize=17,x=.10,ha="left")
    handles, labels=axes[0].get_legend_handles_labels()
    figure.legend(handles,labels,loc="lower center",ncol=4,frameon=False,bbox_to_anchor=(.52,.005))
    figure.text(.10,.12,"主机调用延迟；并发 execute 窗口互相重叠，不代表 GPU kernel 占用。",fontsize=10,color="#566574")
    figure.tight_layout(rect=[0,.15,1,.92],h_pad=1.8)
    figure.savefig(destination / "comparison.png",dpi=180)
    figure.savefig(destination / "comparison.svg")
    plt.close(figure)

    body=markdown.markdown((destination / "report.md").read_text(),extensions=["tables"])
    image='<figure><img src="comparison.svg" alt="v1 改进前后内部耗时与百分比对照" /></figure>'
    first_end=body.index("</h1>")+len("</h1>")
    body=body[:first_end]+image+body[first_end:]
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v1 内部耗时对照实验</title><style>
body{font-family:"Noto Sans CJK SC",sans-serif;background:#f7f9fc;color:#253844;margin:0 auto;padding:36px;max-width:1200px;line-height:1.75}h1,h2,h3{line-height:1.4}h1{font-size:30px}h2{margin-top:40px;font-size:23px}table{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0}th,td{padding:9px 12px;border-bottom:1px solid #d5dee8;text-align:left}th{background:#e5edf5}tr:nth-child(even){background:#eef3f8}figure{margin:25px 0}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}li{overflow-wrap:anywhere}@media(max-width:700px){body{padding:16px}table{font-size:12px}th,td{padding:6px}}
</style><body>'''+body+"</body></html>"
    (destination / "index.html").write_text(html)
    timestamp=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    files={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest={"schema_version":1,"artifact_id":"autodata-v1-internal-timing","version":destination.name,
              "created_at":timestamp,"sealed_at":timestamp,"material_cutoff":"2026-10-15 Asia/Shanghai",
              "sources":[str(p) for p in source_files],"files":files,
              "validation":{"real_gpu_runs":2,"num_envs":plan["num_envs"],"target_successes_per_run":plan["target_successes"],
                            "accounting_closure":True,"physical_and_schema_passed":report["validation_passed"]},
              "limitations":plan["limitations"],"delivery":{"local":{"status":"saved"},"external":{"status":"not_requested","published":False}}}
    (destination / "manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(destination)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory",type=Path)
    parser.add_argument("destination",type=Path)
    arguments=parser.parse_args()
    package(arguments.run_directory.resolve(),arguments.destination.resolve())
