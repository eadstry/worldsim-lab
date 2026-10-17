# SPDX-License-Identifier: Apache-2.0
"""Launch upstream generation with periodic initialization diagnostics."""
import argparse
import faulthandler
import os
from pathlib import Path
import runpy

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--input_file', type=Path, required=True)
parser.add_argument('--generation_num_trials', type=int, default=1)
parser.add_argument('--num_envs', type=int, default=1)
parser.add_argument('--output_file', type=Path, required=True)
args, _ = parser.parse_known_args()
assert args.generation_num_trials == 1 and args.num_envs == 1, 'Use one episode per process'
assert args.input_file.is_file(), f'Missing input: {args.input_file}'
assert not args.output_file.exists(), f'Output already exists: {args.output_file}'
faulthandler.enable()
faulthandler.dump_traceback_later(60, repeat=True)
runpy.run_path(str(Path(os.environ['ARENA_ROOT']) / 'submodules/IsaacLab/scripts/imitation_learning/isaaclab_mimic/generate_dataset.py'), run_name='__main__')
