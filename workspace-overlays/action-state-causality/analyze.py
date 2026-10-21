"""Compare saved intervention records without importing the simulator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = {"runs": {}, "limits": [
        "Single saved demo per intervention batch; no training or real robot evaluation.",
        "Removing collisions is a diagnostic intervention and invalidates grasping as a task.",
        "Implicit actuator torque estimates do not measure actual solver drive forces.",
        "Historical source replay may diverge after contact despite matching its early states.",
        "Speed and control frequency variants use explicit zero-order-hold resampling.",
    ]}
    for path in sorted(args.run_root.glob("*/summary.json")):
        provenance = json.loads((path.parent / "provenance.json").read_text())
        if provenance["args"].get("no_collisions") and "collision_audit" not in provenance:
            report.setdefault("excluded_runs", {})[path.parent.name] = (
                "Requested collision disable was ineffective on instanceable USD geometry; "
                "no stage audit existed. Do not interpret this as a no-contact condition.")
            continue
        summary = json.loads(path.read_text())
        baseline = summary["baseline"]["request_pre"]["mae_deg"]
        values = {}
        for name, value in summary.items():
            if not isinstance(value, dict) or "request_pre" not in value:
                continue
            data = np.load(path.parent / f"{name}.npz", allow_pickle=False)
            n = len(data["time"])
            for field in ("request", "pre", "applied", "post", "pre_velocity"):
                if data[field].shape != (n, 9) or not np.isfinite(data[field]).all():
                    raise ValueError(f"Invalid record shape or non-finite data: {path}/{name}/{field}")
            independently_computed = float(np.mean(np.abs(data["request"][:, :7]-data["pre"][:, :7]))*180/np.pi)
            if not np.isclose(independently_computed, value["request_pre"]["mae_deg"], rtol=1e-6):
                raise ValueError(f"Saved summary does not match raw arrays: {path}/{name}")
            values[name] = dict(value,
                delta_from_baseline_deg=value["request_pre"]["mae_deg"]-baseline,
                delta_from_baseline_percent=(value["request_pre"]["mae_deg"]/baseline-1)*100)
        if "repeat" in values:
            a = np.load(path.parent / "baseline.npz", allow_pickle=False)
            b = np.load(path.parent / "repeat.npz", allow_pickle=False)
            summary["repeat_state_max_abs_rad"] = float(np.max(np.abs(a["pre"]-b["pre"])))
        physics = path.parent / "physics-substeps.npz"
        if physics.exists():
            with np.load(physics, allow_pickle=False) as raw:
                physics_values = raw["values"]
                baseline_frames = values["baseline"]["frames"]
                for index, label in enumerate(raw["variants"]):
                    label = str(label)
                    speed = {"speed_half": .5, "speed_double": 2.}.get(label, 1.)
                    end = min(len(physics_values), int(round(baseline_frames*4/speed)))
                    request, applied, pre, post, velocity = np.moveaxis(physics_values[:end, index], 1, 0)
                    values[label]["physics_substeps"] = {
                        "count": end,
                        "request_applied_arm_mae_deg": float(np.abs(request[:,:7]-applied[:,:7]).mean()*180/np.pi),
                        "applied_pre_arm_mae_deg": float(np.abs(applied[:,:7]-pre[:,:7]).mean()*180/np.pi),
                        "applied_post_arm_mae_deg": float(np.abs(applied[:,:7]-post[:,:7]).mean()*180/np.pi),
                        "max_arm_speed_rad_s": float(np.abs(velocity[:,:7]).max()),
                    }
        report["runs"][path.parent.name] = dict(variants=values,
            reproduction=summary.get("historical_reproduction"),
            repeat_state_max_abs_rad=summary.get("repeat_state_max_abs_rad"),
            wall_seconds=summary["wall_seconds"])
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    for run, content in report["runs"].items():
        print(run)
        for name, value in content["variants"].items():
            print(f"  {name:22s} pre={value['request_pre']['mae_deg']:.6f} "
                  f"post={value['request_post']['mae_deg']:.6f} "
                  f"delta={value['delta_from_baseline_percent']:+.1f}% "
                  f"finger2={value['finger_2_settled_closed']['median_rad']}")


if __name__ == "__main__":
    main()
