# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only checks; never imports Isaac Sim, torch, or cuRobo."""

import ast
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path

import yaml

root = Path(__file__).resolve().parent
autodata = root.parents[1] / "AutoData"
sys.path.insert(0, str(autodata))
from autodata_interfaces.tasks.task_descriptor import TaskDescriptor
from autodata_interfaces.tasks.subtask_spec import ALGO_PARAMS_REGISTRY
from compat import install_task_compat

package = root / "runtime/openarm_autodata"
configs = package / "tasks/pick_place/autodata_configs"
expected_error = None
if "expected_attached_object" not in {f.name for f in fields(ALGO_PARAMS_REGISTRY["skillgen"])}:
    try:
        TaskDescriptor.from_yaml(configs / "tasks/openarm_bimanual_right_pick_place.yaml")
    except AssertionError as exc:
        expected_error = str(exc)
        assert "expected_attached_object" in expected_error, expected_error
    else:
        raise AssertionError("Expected the original upstream parser to reject the delivery field")
install_task_compat()
for arm in ("left", "right"):
    task = TaskDescriptor.from_yaml(configs / f"tasks/openarm_bimanual_{arm}_pick_place.yaml")
    embodiment = yaml.safe_load((configs / f"embodiments/openarm_bimanual_{arm}_ik_rel.yaml").read_text())
    profile = yaml.safe_load((configs / f"env_profiles/openarm_{arm}_skillgen.yaml").read_text())
    assert task.get_eef_names() == [embodiment["eef_name"]] == [arm]
    assert task.get_expected_attached_object(arm, 0) is None
    assert task.get_expected_attached_object(arm, 1) == "cube"
    assert task.get_generation_policy().max_num_failures == 25
    assert profile["base_env"] == f"Isaac-PickPlace-Cube-OpenArm-Bimanual-{arm.title()}-IK-Rel-v0"

planner = package / "shared/autodata_configs/planners/openarm_right.yml"
kinematics = yaml.safe_load(planner.read_text())["robot_cfg"]["kinematics"]
urdf = (planner.parent / kinematics["urdf_path"]).resolve()
assert urdf.is_file(), urdf
assert (planner.parent / kinematics["asset_root_path"]).resolve().is_dir()
meshes = ET.parse(urdf).findall(".//mesh")
for mesh in meshes:
    path = (urdf.parent / mesh.attrib["filename"]).resolve()
    assert path.is_file(), path

# Check all planner constructor keywords against the actual upstream config annotations.
config_ast = ast.parse((autodata / "autodata_interfaces/motion_planners/curobo/curobo_planner_cfg.py").read_text())
config_class = next(node for node in config_ast.body if isinstance(node, ast.ClassDef) and node.name == "CuroboPlannerCfg")
allowed = {node.target.id for node in config_class.body if isinstance(node, ast.AnnAssign)}
shared_ast = ast.parse((package / "shared/planner_cfg.py").read_text())
shared_class = next(node for node in shared_ast.body if isinstance(node, ast.ClassDef) and node.name == "OpenArmRightPlannerCfg")
allowed.update(node.target.id for node in shared_class.body if isinstance(node, ast.AnnAssign))
planner_ast = ast.parse((package / "tasks/pick_place/planner_cfg.py").read_text())
for node in ast.walk(planner_ast):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "OpenArmRightPlannerCfg":
        assert {kw.arg for kw in node.keywords} <= allowed, {kw.arg for kw in node.keywords} - allowed
for path in [*root.glob("*.py"), *package.rglob("*.py"), *root.glob("runtime/patches/*.py")]:
    compile(path.read_text(), str(path), "exec")
report = {
    "original_parser_rejection": expected_error,
    "task_schema_with_compat": "passed, left and right",
    "explicit_cube_attachment": "passed, left and right",
    "planner_constructor_fields": "passed",
    "urdf_mesh_references": len(meshes),
    "python_syntax": "passed",
    "runtime_generation": "Reported separately in local-runtime-validation.json; this script checks static properties only",
}
(root / "static-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
