#!/usr/bin/env python3
"""Compare completed AutoData/Arena GPU probes, never infer success from process exit alone."""
import argparse
import json
from pathlib import Path

FIELDS = ('task_contract_hash', 'action_shape', 'physics_dt', 'step_dt', 'reset_pose_range',
          'success_function', 'success_params', 'observations', 'processed_arm_probe',
          'gripper_targets', 'success_cases', 'physics_steps_completed')


def compare(left, right):
    checks = {'both_passed': left.get('status') == right.get('status') == 'passed',
              'correct_backends': left.get('backend') == 'autodata' and right.get('backend') == 'arena',
              'same_openarm_source': left.get('package_paths', {}).get('openarm_autodata') ==
                                     right.get('package_paths', {}).get('openarm_autodata')}
    checks.update({key: key in left and key in right and left[key] == right[key] for key in FIELDS})
    return {'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
            'scope': 'matching task interfaces and predicate cases; not full-trajectory or learned-policy equivalence'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('autodata', type=Path)
    parser.add_argument('arena', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.autodata.read_text()), json.loads(args.arena.read_text()))
    snapshots = [json.loads(path.with_name('resolved_config.json').read_text()) for path in (args.autodata, args.arena)]
    result['checks']['same_working_tree_sources'] = snapshots[0]['source_hashes'] == snapshots[1]['source_hashes']
    result['status'] = 'passed' if all(result['checks'].values()) else 'failed'
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
