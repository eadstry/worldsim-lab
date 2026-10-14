# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Compatibility for the delivered OpenArm task; call after simulator startup."""

from dataclasses import dataclass, fields


def install_task_compat():
    # These modules contain dataclasses/YAML parsing only and can also be checked on the host.
    from autodata_interfaces.tasks import subtask_spec
    from autodata_interfaces.tasks import generation_policy_spec, task_descriptor, task_descriptor_utils
    from autodata_interfaces.tasks.task_descriptor import TaskDescriptor

    if "max_num_failures" not in {f.name for f in fields(generation_policy_spec.GenerationPolicy)}:
        @dataclass
        class OpenArmGenerationPolicy(generation_policy_spec.GenerationPolicy):
            max_num_failures: int = 25
            num_steps_final_hold: int = 0

        generation_policy_spec.GenerationPolicy = OpenArmGenerationPolicy
        task_descriptor.GenerationPolicy = OpenArmGenerationPolicy
        task_descriptor_utils.GenerationPolicy = OpenArmGenerationPolicy

    if "expected_attached_object" not in {f.name for f in fields(subtask_spec.ALGO_PARAMS_REGISTRY["skillgen"])}:
        @dataclass
        class OpenArmSkillGenParams(subtask_spec.ALGO_PARAMS_REGISTRY["skillgen"]):
            expected_attached_object: str | None = None

        subtask_spec.ALGO_PARAMS_REGISTRY["skillgen"] = OpenArmSkillGenParams

    original = TaskDescriptor.get_expected_attached_object

    def get_expected_attached_object(self, eef_name, subtask_index):
        subtasks = self.subtasks.get(eef_name, [])
        if 0 <= subtask_index < len(subtasks):
            explicit = getattr(subtasks[subtask_index].algo_params, "expected_attached_object", None)
            if explicit is not None:
                return explicit
        return original(self, eef_name, subtask_index)

    TaskDescriptor.get_expected_attached_object = get_expected_attached_object


def install_generation_compat():
    """Preserve completion checks when planning returns without enqueuing an action."""
    import inspect
    import textwrap
    from autodata_interfaces import env as env_exports
    from autodata_interfaces.env import isaaclab_env_interface
    from autodata_core import data_generator

    source = textwrap.dedent(inspect.getsource(isaaclab_env_interface.env_loop))
    anchor = "                asyncio_event_loop.run_until_complete(asyncio.sleep(0))"
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + '''
                completed = stats["num_success"] if guarantee_success else stats["num_attempts"]
                if completed >= num_trials:
                    return True
                if stats["num_failures"] >= generation_policy_params.max_num_failures:
                    raise RuntimeError("OpenArm generation reached its configured failure limit")
''', 1)
    scope = {}
    exec(compile(source, "<openarm-env-loop>", "exec"), vars(isaaclab_env_interface), scope)
    isaaclab_env_interface.env_loop = scope["env_loop"]
    env_exports.env_loop = scope["env_loop"]

    source = textwrap.dedent(inspect.getsource(data_generator.DataGenerator.generate))
    anchor = "    # Recorder lifecycle stays on env by design:"
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''    final_hold_steps = self.datastream.get_generation_policy().num_steps_final_hold
    assert final_hold_steps >= 0
    for _ in range(final_hold_steps):
        exec_success = await multi_waypoint.execute(
            datastream=self.datastream, success_term=success_term,
            env_id=env_id, env_action_queue=env_action_queue,
        )
        buffers.success = buffers.success or exec_success

''' + anchor, 1)
    scope = {}
    exec(compile(source, "<openarm-final-hold>", "exec"), vars(data_generator), scope)
    data_generator.DataGenerator.generate = scope["generate"]


def install():
    install_task_compat()
    import importlib.util
    import os
    import sys
    from pathlib import Path

    from autodata_interfaces.motion_planners.curobo import curobo_planner_cfg  # noqa: F401

    name = "autodata_interfaces.motion_planners.curobo.curobo_planner"
    assert name not in sys.modules, "Planner was imported before OpenArm compatibility setup"
    path = Path(__file__).resolve().parent / "runtime/patches/curobo_planner.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    planner_module = module
    from autodata_interfaces import embodiments
    from autodata_interfaces.embodiments import factory

    name = "autodata_interfaces.embodiments.single_arm_embodiment_adapter"
    path = Path(__file__).resolve().parent / "runtime/patches/single_arm_embodiment_adapter.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    factory.EMBODIMENT_TYPE_REGISTRY["delta_pose_ik_single_arm"] = module.DeltaPoseIKSingleArmAdapter
    factory.DeltaPoseIKSingleArmAdapter = module.DeltaPoseIKSingleArmAdapter
    embodiments.DeltaPoseIKSingleArmAdapter = module.DeltaPoseIKSingleArmAdapter
    # The prepared package restores the original AutoData registration from reference/.
    import openarm_autodata.tasks.pick_place  # noqa: F401
    install_generation_compat()
    from autodata_core import data_generator
    from pathlib import Path
    from telemetry import install as install_telemetry

    telemetry_file = os.environ.get("OPENARM_TELEMETRY_FILE")
    assert telemetry_file, "OPENARM_TELEMETRY_FILE must be set by generate.py"
    install_telemetry(data_generator, planner_module, Path(telemetry_file))
