# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Isolate CPU frame ownership from asynchronous export for the ablation."""
import terminal_gate
import terminal_launch

original_guard = terminal_gate.guarded_source


def owned_guard(source):
    # Called only after SimulationApp starts and before environment creation.
    from isaaclab.managers.recorder_manager import RecorderManager
    from async_export import owned_recording_method
    RecorderManager.add_to_episodes = owned_recording_method(RecorderManager.add_to_episodes)
    print('Benchmark independent CPU frame ownership enabled', flush=True)
    return original_guard(source)


if __name__ == '__main__':
    terminal_gate.guarded_source = owned_guard
    # Keep the same entrypoint in the independently supervised generator child.
    terminal_launch.__file__ = __file__
    terminal_launch.main()
