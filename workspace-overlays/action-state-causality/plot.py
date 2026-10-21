"""Export a compact causal comparison figure from verified experiment summaries."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.analysis.read_text())["runs"]
    keys = ["baseline", "kp_double", "kd_half", "speed_half", "speed_double", "gravity_feedforward", "no_cube"]
    labels = ["Baseline", "Arm stiffness x2", "Arm damping x0.5", "Trajectory speed x0.5",
              "Trajectory speed x2", "Gravity feedforward", "Cube removed"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [2, 1]})
    y = np.arange(len(keys))
    for offset, run, color, label in [(-.18, "fixed-r01", "#2878B5", "demo_0"),
                                       (.18, "demo1-r02", "#E58A2B", "demo_1")]:
        values = report[run]["variants"]
        axes[0].barh(y+offset, [values[k]["request_pre"]["mae_deg"] for k in keys],
                     height=.34, color=color, label=label)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Mean absolute arm request - pre-step state (degrees)")
    axes[0].legend(frameon=False)
    axes[0].set_title("Fixed joint requests; one intervention at a time", fontsize=11)
    values = report["fixed-r01"]["variants"]
    axes[1].bar(["Cube present", "Cube removed"],
                [values[k]["finger_2_settled_closed"]["median_rad"] for k in ("baseline", "no_cube")],
                color=["#2878B5", "#55A868"])
    axes[1].set_ylabel("Finger 2 median actual position (rad)")
    axes[1].set_title("Applied close target already at 0 rad", fontsize=10)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("OpenArm action/state sensitivity — GPU replay, two saved trajectories", fontsize=13)
    fig.text(.02, .01, "No production controller changes. Effects are not additive; no real-robot or training validation.", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    fig.savefig(args.output, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
