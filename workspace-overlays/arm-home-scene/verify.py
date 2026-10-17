"""Check recorded physical states, final placement, image streams and encoded videos."""
import argparse
import hashlib
import json
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    path = args.run / "episodes.hdf5"
    report = {"dataset": str(path.resolve())}
    with h5py.File(path, "r") as f:
        assert list(f["data"]) == ["demo_0"]
        d = f["data/demo_0"]
        actions = d["actions"][:]
        obs = d["obs"]
        state = obs["cube_state"][:]
        frames = len(actions)
        assert all(len(v) == frames for v in obs.values())
        assert np.isfinite(actions).all()
        assert all(np.isfinite(obs[k][:]).all() for k in ("joint_pos", "joint_vel", "cube_state", "tcp_pose"))
        initial_z = state[30, 2]
        lift = float(state[:, 2].max() - initial_z)
        final = state[-50:]
        speed = np.linalg.norm(final[:, 7:10], axis=-1)
        xy = np.abs(final[:, :2] - [0.5, -0.2])
        z = np.abs(final[:, 2] - 0.02)
        assert lift > 0.15
        assert (xy < 0.04).all() and (z < 0.015).all() and (speed < 0.02).all()
        assert (obs["joint_pos"][-50:, -2:] > 0.035).all(), "Fingers not open at end"
        separation = np.linalg.norm(obs["tcp_pose"][-50:, :3] - final[:, :3], axis=-1)
        assert (separation > 0.15).all(), "Gripper has not withdrawn"
        assert bool(d.attrs["success"])
        report.update(frames=frames, success=True, measured_lift_m=lift,
                      final_max_speed_m_s=float(speed.max()), final_stable_seconds=1.0,
                      final_min_tool_separation_m=float(separation.min()), finite_actions_and_states=True,
                      max_cube_step_displacement_m=float(np.linalg.norm(np.diff(state[:, :3], axis=0), axis=-1).max()))
        video_report = {}
        for camera in ("overview", "detail"):
            rgb = obs[camera + "_rgb"]
            for index in (100, frames // 2, frames - 1):
                assert rgb[index].std() > 2, f"Blank {camera} frame"
            reader = imageio_ffmpeg.read_frames(str(args.run / (camera + ".mp4")), pix_fmt="rgb24")
            meta = next(reader)
            count = sum(1 for _ in reader)
            assert count == frames and abs(meta["fps"] - 50) < 0.01
            assert tuple(meta["size"]) == (rgb.shape[2], rgb.shape[1])
            video_report[camera] = dict(frames=count, fps=meta["fps"], size=list(meta["size"]))
        report["videos"] = video_report
    report["dataset_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.run / "verification.json").write_text(json.dumps(report, indent=2))
    panels = ["00-approach.png", "03-lift.png", "05-lower.png", "08-settle.png"]
    sheet = Image.new("RGB", (960, 584), "white")
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(panels):
        x, y = (i % 2) * 480, (i // 2) * 292
        with Image.open(args.run / name) as im:
            sheet.paste(im.resize((480, 270)), (x, y))
        draw.text((x + 8, y + 273), name.removesuffix(".png"), fill="black")
    sheet.save(args.run / "contact-sheet.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
