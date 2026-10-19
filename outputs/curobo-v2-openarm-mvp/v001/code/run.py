# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Run one backend's fixed-attempt single-arm SkillGen experiment in its selected Python."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['v1', 'v2'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--attempts', type=int, default=5)
    parser.add_argument('--seed', type=int, default=101)
    args = parser.parse_args()
    assert args.attempts > 0
    root = Path(__file__).resolve().parent
    cfg = json.loads((root / '.local/machine.json').read_text())
    assert Path(sys.prefix).resolve() == Path(cfg[args.backend + '_python']).resolve().parents[1]
    assert not args.output.exists()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    production = Path(cfg['production_snapshot']) if args.backend == 'v1' else root / '.local/production-v2'
    sys.path[:0] = [str(root), str(production), str(production / 'runtime'), cfg['autodata_root']]
    import yaml
    task_source = production / 'runtime/openarm_autodata/tasks/pick_place/autodata_configs/tasks/openarm_bimanual_left_pick_place.yaml'
    task = yaml.safe_load(task_source.read_text())
    task['generation_policy'].update(seed=args.seed, num_trials=args.attempts, guarantee_success=False,
                                     keep_failed=True, max_num_failures=args.attempts + 1)
    task_path = args.output.with_suffix('.task.yaml')
    assert not task_path.exists()
    task_path.write_text(yaml.safe_dump(task, sort_keys=False))
    os.environ.update(MVP_BACKEND=args.backend, MVP_SEED=str(args.seed),
                      MVP_METRICS_FILE=str(args.output.resolve().with_suffix('.metrics.jsonl')),
                      PYTHONDONTWRITEBYTECODE='1')
    if args.backend == 'v2':
        from curobo._src import runtime
        runtime.cache_dir = str(root / '.local/cache/v2/curobo')
    import compat
    install = compat.install

    def install_with_metrics():
        install()
        from autodata_interfaces.motion_planners.curobo.curobo_planner import CuroboPlanner
        from metrics import install as install_metrics
        install_metrics(CuroboPlanner)
    compat.install = install_with_metrics
    import generate
    sys.argv = [str(production / 'generate.py'), '--autodata-root', cfg['autodata_root'],
                '--arm', 'left', '--final-hold-steps', '60', '--input_file', cfg['input'],
                '--output_file', str(args.output.resolve()), '--num_envs', '1',
                '--generation_num_trials', str(args.attempts), '--task_descriptor', str(task_path.resolve()),
                '--log-interval', '10']
    generate.main()


if __name__ == '__main__':
    main()
