# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only process routing checks using a fake simulator-free production root."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LaunchTests(unittest.TestCase):
    def test_gate_and_ownership_reach_the_supervised_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'isaaclab/managers').mkdir(parents=True)
            (root / 'isaaclab/__init__.py').write_text('')
            (root / 'isaaclab/managers/recorder_manager.py').write_text(
                'class RecorderManager:\n    def add_to_episodes(self): pass\n')
            (root / 'isaaclab/managers/__init__.py').write_text('from .recorder_manager import RecorderManager\n')
            (root / 'async_export.py').write_text(
                'def owned_recording_method(method):\n    method.owned = True\n    return method\n')
            (root / 'compat.py').write_text('')
            (root / 'run_local.py').write_text(
                'import subprocess,sys\nfrom pathlib import Path\n'
                'raise SystemExit(subprocess.call([sys.executable,"-u",str(Path(__file__).with_name("generate.py")),*sys.argv[1:]]))\n')
            (root / 'generate.py').write_text(
                'import compat,sys,json\nfrom pathlib import Path\n'
                'from isaaclab.managers import RecorderManager\n'
                'source="def generate():\\n    env.recorder_manager.set_success_to_episodes(ids,flags)\\n"\n'
                'code=compat.compile(source,"<openarm-final-hold>","exec")\n'
                'assert "recorded_terminal_success" in code.co_consts[0].co_names\n'
                'Path(sys.argv[1]).write_text(json.dumps({"owned":getattr(RecorderManager.add_to_episodes,"owned",False)}))\n')
            for filename, expected in [('terminal_launch.py', False), ('owned_launch.py', True)]:
                output = root / (filename + '.json')
                completed = subprocess.run([sys.executable, str(Path(__file__).with_name(filename)),
                                            '--production-root', str(root), str(output)],
                                           capture_output=True, text=True, timeout=15)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(json.loads(output.read_text())['owned'], expected)


if __name__ == '__main__':
    unittest.main()
