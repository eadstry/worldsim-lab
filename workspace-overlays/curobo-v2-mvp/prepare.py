# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Prepare process-local v2 hooks; never modify source checkouts or the original environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"Integration anchor changed: {old}"
    return text.replace(old, new, 1)


def main() -> None:
    root = Path(__file__).resolve().parent
    cfg = json.loads((root / '.local/machine.json').read_text())
    source = Path(cfg['production_snapshot'])
    target = root / '.local/production-v2'
    assert not target.exists(), 'Use a new snapshot instead of overwriting a prepared backend'
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__'))
    config_source = Path(cfg['autodata_root']) / 'autodata_interfaces/motion_planners/curobo/curobo_planner_cfg.py'
    text = config_source.read_text()
    text = replace_once(text, 'from curobo.geom.sdf.world import CollisionCheckerType',
                        'from enum import Enum\nclass CollisionCheckerType(Enum):\n    MESH = "mesh"\n    PRIMITIVE = "primitive"')
    text = replace_once(text, 'from curobo.geom.types import WorldConfig', 'from curobo.scene import Scene as WorldConfig')
    text = replace_once(text, 'from curobo.util_file import get_robot_configs_path, get_world_configs_path, join_path, load_yaml',
                        'from curobo.content import get_robot_configs_path, get_scene_configs_path as get_world_configs_path\nfrom curobo.config_io import join_path, load_yaml')
    compile(text, '<mvp-v2-config>', 'exec')
    (target / 'v2_config.py').write_text(text)
    path = target / 'runtime/openarm_autodata/shared/planner_cfg.py'
    text = path.read_text().replace('from curobo.util_file import load_yaml', 'from curobo.config_io import load_yaml')
    text = replace_once(text, 'from curobo.geom.types import WorldConfig', 'from curobo.scene import Scene as WorldConfig')
    path.write_text(text)
    path = target / 'compat.py'
    text = replace_once(path.read_text(), '    from autodata_interfaces.motion_planners.curobo import curobo_planner_cfg  # noqa: F401', '''    config_name = "autodata_interfaces.motion_planners.curobo.curobo_planner_cfg"
    config_path = Path(__file__).resolve().with_name("v2_config.py")
    config_spec = importlib.util.spec_from_file_location(config_name, config_path)
    config_module = importlib.util.module_from_spec(config_spec)
    sys.modules[config_name] = config_module
    config_spec.loader.exec_module(config_module)
    from autodata_interfaces.motion_planners.curobo import curobo_planner_cfg  # noqa: F401''')
    text = replace_once(text, 'Path(__file__).resolve().parent / "runtime/patches/curobo_planner.py"',
                        repr(str(root / 'v2_planner.py')))
    path.write_text(text)
    path = target / 'telemetry.py'
    text = path.read_text()
    start = text.index('    # Count actual outer cuRobo attempts,')
    end = text.index("    telemetry.emit('instrumentation_ready'", start)
    text = text[:start] + '    solver_instrumented = False  # v1 private attempts do not map to v2.\n' + text[end:]
    path.write_text(text)
    manifest = {'v2_commit': cfg['v2_commit'], 'source_config_sha256': hashlib.sha256(config_source.read_bytes()).hexdigest(),
                'files': {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in target.rglob('*.py')}, 'legacy_solver_iteration_instrumentation': False}
    (root / '.local/preparation.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Prepared independent v2 OpenArm snapshot')


if __name__ == '__main__':
    main()
