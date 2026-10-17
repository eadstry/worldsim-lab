"""Use the maintained OpenPI wrapper with hash-preserving wheel URL mirroring."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib

ORIGINAL = "https://files.pythonhosted.org/packages/"
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/packages/"
ARENA_COMMIT = "98866596fd024d96c874fe6fb95ae916d1133629"


def rewrite_lock(raw):
    """Prove that only package download URLs change, including every locked hash."""
    mirrored = raw.replace(ORIGINAL, MIRROR)
    before, after = tomllib.loads(raw), tomllib.loads(mirrored)

    def restore(value):
        if isinstance(value, str):
            return ORIGINAL + value[len(MIRROR):] if value.startswith(MIRROR) else value
        if isinstance(value, list):
            return [restore(x) for x in value]
        if isinstance(value, dict):
            return {k: restore(v) for k, v in value.items()}
        return value

    if restore(after) != before:
        raise ValueError("Lock semantics changed beyond the allowed download URL prefix")
    if not raw.count(ORIGINAL):
        raise ValueError("No expected package URLs found; refusing an unknown lock layout")
    return mirrored, raw.count(ORIGINAL)


def patch_context(context, expected_commit, evidence):
    context = context.resolve(strict=True)
    commit = subprocess.check_output(["git", "-C", str(context), "rev-parse", "HEAD"], text=True).strip()
    if commit != expected_commit or not (context / "scripts/serve_policy.py").is_file():
        raise ValueError("Build context is not the wrapper's pinned OpenPI checkout")
    lock = context / "uv.lock"
    raw = lock.read_text()
    rewritten, count = rewrite_lock(raw)
    receipt = {
        "openpi_commit": commit, "mirror": MIRROR, "changed_urls": count,
        "original_lock_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "mirrored_lock_sha256": hashlib.sha256(rewritten.encode()).hexdigest(),
        "validation": "Parsed TOML identical after reversing only the allowed URL prefix; versions and hashes unchanged",
    }
    # Evidence must be a fresh task directory; never overwrite another attempt.
    with (evidence / "download-routing.json").open("x") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    (evidence / "original-uv.lock").write_text(raw)
    lock.write_text(rewritten)


def docker_shim(argv):
    if argv and argv[0] == "build":
        patch_context(Path(argv[-1]), os.environ["OPENPI_MIRROR_COMMIT"],
                      Path(os.environ["OPENPI_MIRROR_EVIDENCE"]))
    real = os.environ["OPENPI_MIRROR_DOCKER"]
    os.execv(real, [real, *argv])


def main():
    if sys.argv[1:2] == ["--docker-shim"]:
        docker_shim(sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arena-root", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    args, wrapper_args = parser.parse_known_args()
    arena = args.arena_root.resolve(strict=True)
    head = subprocess.check_output(["git", "-C", str(arena), "rev-parse", "HEAD"], text=True).strip()
    if head != ARENA_COMMIT:
        raise ValueError("Unexpected Arena revision; preserve the reviewed dependency pin")
    wrapper = arena / "isaaclab_arena_openpi/docker/run_openpi_server.sh"
    pin = (wrapper.parent / "OPENPI_COMMIT").read_text().strip()
    evidence = args.evidence_directory.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    real_docker = shutil.which("docker")
    if not real_docker:
        raise ValueError("Docker CLI is missing")
    env = dict(os.environ, OPENPI_MIRROR_COMMIT=pin, OPENPI_MIRROR_DOCKER=real_docker,
               OPENPI_MIRROR_EVIDENCE=str(evidence), OPENPI_MIRROR_PYTHON=sys.executable,
               OPENPI_MIRROR_SCRIPT=str(Path(__file__).resolve()))
    # The PTY sends interrupts to the wrapper and Docker too. Wait for their cleanup.
    previous = {s: signal.signal(s, lambda *_: None) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        with tempfile.TemporaryDirectory(prefix="openpi-download-shim-") as temp:
            shim = Path(temp) / "docker"
            shim.write_text('#!/bin/sh\nexec "$OPENPI_MIRROR_PYTHON" "$OPENPI_MIRROR_SCRIPT" --docker-shim "$@"\n')
            shim.chmod(0o700)
            env["PATH"] = temp + os.pathsep + env.get("PATH", "")
            return subprocess.call([str(wrapper), *wrapper_args], cwd=arena, env=env)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
