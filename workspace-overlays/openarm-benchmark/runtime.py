#!/usr/bin/env python3
"""Bootstrap one Arena process using an explicitly selected checkout and bundle."""

import argparse
import runpy
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--arena-root", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    if remaining[:1] == ["--"]:
        remaining = remaining[1:]
    sys.path[:0] = [
        str(Path(__file__).resolve().parent),
        str(args.arena_root.resolve()),
        str(args.bundle.resolve()),
    ]
    from openarm_benchmark.recording import install_native_recording

    remaining = install_native_recording(args.arena_root, remaining)
    sys.argv = ["policy_runner", *remaining]
    # The external environment is imported by Arena after SimulationApp starts.
    runpy.run_module("isaaclab_arena.evaluation.policy_runner", run_name="__main__")


if __name__ == "__main__":
    main()
