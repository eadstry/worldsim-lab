# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check the recorder/capture alignment and rejection of missing or shifted evidence."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np


class CaptureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/'source.py'
        self.source.write_text('source snapshot\n')
        for name in ('baseline','offset-a','offset-b'):
            folder=self.root/name
            folder.mkdir()
            eef=np.arange(41*3,dtype=float).reshape(41,3)*.001
            cube=eef+.2
            with h5py.File(folder/'episodes.hdf5','w') as f:
                g=f.create_group('data/demo_0')
                g.create_dataset('actions',data=np.zeros((41,7)))
                g.create_dataset('obs/left_tcp_pos_env',data=eef)
                g.create_dataset('states/rigid_object/cube/root_pose',data=cube)
            frames=[{'file':f'frame-{i:04d}.jpg','step':s,'time_s':s/30.,'eef_position_m':eef[s].tolist(),
                     'cube_position_m':cube[s-1].tolist()} for i,s in enumerate((1,20))]
            probe={'frames':frames,'plans':[{'start_step':0,'eef_positions_m':np.zeros((10,3)).tolist()}]}
            (folder/'probe.json').write_text(json.dumps(probe))
            for i in range(3):(folder/f'frame-{i:04d}.jpg').write_bytes(b'frame-file-placeholder')
            (folder/'source-sha256.json').write_text(json.dumps({str(self.source):hashlib.sha256(self.source.read_bytes()).hexdigest()}))

    def tearDown(self):
        self.temp.cleanup()

    def run_recovery(self):
        return subprocess.run([sys.executable,str(Path(__file__).with_name('recover_capture.py')),str(self.root)],
                              capture_output=True,text=True)

    def test_recovers_tail_only_after_crosschecking_live_snapshot(self):
        result=self.run_recovery()
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads((self.root/'baseline/probe-recovered.json').read_text())
        self.assertEqual([x['step'] for x in data['frames']],[1,20,40])
        self.assertEqual(data['frames'][-1]['eef_position_m'],[.120,.121,.122])
        self.assertEqual(data['frames'][-1]['cube_position_m'],[.317,.318,.319])

    def test_rejects_a_shifted_observation(self):
        p=self.root/'baseline/probe.json'
        data=json.loads(p.read_text());data['frames'][1]['eef_position_m'][0]+=.003
        p.write_text(json.dumps(data))
        self.assertNotEqual(self.run_recovery().returncode,0)
        self.assertFalse((self.root/'baseline/probe-recovered.json').exists())

    def test_rejects_a_missing_rendered_frame(self):
        (self.root/'baseline/frame-0002.jpg').unlink()
        self.assertNotEqual(self.run_recovery().returncode,0)


if __name__=='__main__':
    unittest.main()
