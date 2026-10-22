"""Keep the cuRobo CUDA/torch environment isolated from the Isaac Sim runtime."""
import json
import os
import subprocess
import time
from pathlib import Path


class PlannerClient:
    def __init__(self, python, output, obstacle):
        startup_started = time.perf_counter()
        self.output = Path(output)
        self.log = self.output.with_suffix(".log").open("x")
        env = dict(os.environ)
        cuda = Path(python).parent.parent / "lib/python3.12/site-packages/nvidia/cu13"
        env["LD_LIBRARY_PATH"] = str(cuda / "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
        env["CUDA_HOME"] = str(cuda)
        command = [python, "-u", str(Path(__file__).with_name("planner_worker.py")), "--output", str(self.output)]
        if obstacle:
            command.append("--obstacle")
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT,
                                        text=True, env=env)
        self.index = 0
        self.ready = self._wait("ready.json", 180)
        self.ready["worker_startup_wall_s"] = time.perf_counter() - startup_started

    def _wait(self, name, timeout):
        started = time.monotonic()
        while not (self.output / name).exists():
            assert self.process.poll() is None, f"cuRobo worker exited: {self.log.name}"
            if time.monotonic() - started > timeout:
                raise TimeoutError(f"cuRobo request timeout: {self.log.name}")
            time.sleep(.02)
        return json.loads((self.output / name).read_text())

    def plan(self, request):
        self.index += 1
        self.process.stdin.write(json.dumps(dict(request, id=self.index)) + "\n")
        self.process.stdin.flush()
        return self._wait(f"response-{self.index:04d}.json", 90)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"op":"close"}\n')
            self.process.stdin.flush()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.log.close()
