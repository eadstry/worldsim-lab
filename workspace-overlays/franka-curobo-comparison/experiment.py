"""Run the preregistered 2x2 paired experiment in one shared GPU queue reservation."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--robot-usd", type=Path, required=True)
    parser.add_argument("--planner-python", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", nargs="+", type=int, choices=(0, 1, 2), default=[0, 1, 2])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    folder = Path(__file__).resolve().parent
    runtime_files = ("capture.py", "metrics.py", "planner_worker.py", "planner_client.py", "run.sh", "experiment.py")
    source_hashes = {name: hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in runtime_files}
    # Order differs between paired positions; each cell appears exactly once per trial.
    order = [("ik", False), ("curobo", True), ("ik", True), ("curobo", False)]
    cases = []
    for trial in args.trials:
        for method, obstacle in (order if trial % 2 == 0 else list(reversed(order))):
            name = f"{method}-{'blocked' if obstacle else 'clear'}-t{trial}"
            cases.append(dict(name=name, method=method, obstacle=obstacle, trial=trial, status="pending"))
    gpu_info=subprocess.run(["nvidia-smi","--query-gpu=name,driver_version,memory.total","--format=csv,noheader"],capture_output=True,text=True,check=True).stdout.strip()
    manifest = dict(protocol="2x2; 3 paired fixed pick positions; compared transfer and pre-place, same final IK contact",
                    gpu_info=gpu_info,
                    source_sha256=source_hashes, cases=cases, started_unix=time.time(),
                    args={key:str(value) if isinstance(value, Path) else value for key,value in vars(args).items()})
    target = args.output / "manifest.json"

    def save():
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest, indent=2))
        temp.replace(target)

    save()
    for case in cases:
        assert all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest for name,digest in source_hashes.items()), "Runtime source changed during queued experiment"
        output = (args.output / case["name"]).resolve()
        command = ["bash", str(folder / "run.sh"), "--home", str(args.home.resolve()),
                   "--robot-usd", str(args.robot_usd.resolve()), "--planner-python", args.planner_python,
                   "--output", str(output), "--method", case["method"], "--trial", str(case["trial"])]
        if case["obstacle"]:
            command.append("--obstacle")
        case.update(status="running", command=command, output=str(output))
        occupancy=subprocess.run(["nvidia-smi","--query-compute-apps=pid,used_memory","--format=csv,noheader,nounits"],capture_output=True,text=True,check=True)
        case["foreign_gpu_before"] = occupancy.stdout.strip().splitlines()
        save()
        started = time.perf_counter()
        with (args.output / f"{case['name']}.log").open("x") as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600, env=dict(os.environ))
            except subprocess.TimeoutExpired:
                case.update(status="execution_timeout", process_wall_s=time.perf_counter()-started)
                save()
                # Abort the reservation so queue process-group cleanup also stops any worker.
                raise
        case.update(returncode=result.returncode, process_wall_s=time.perf_counter()-started)
        if result.returncode == 0 and (output / "summary.json").is_file():
            case.update(status="completed", result=json.loads((output/"summary.json").read_text()))
        else:
            case["status"] = "execution_error"
        save()
        print(json.dumps({key:case.get(key) for key in ("name", "status", "process_wall_s")}), flush=True)
        if case["status"] == "execution_error":
            # Do not continue over a broken runtime or leave a CUDA worker competing with the next case.
            raise RuntimeError(f"Startup/execution failure: {case['name']}; remaining cases stay pending")
    manifest["finished_unix"] = time.time()
    save()


if __name__ == "__main__":
    main()
