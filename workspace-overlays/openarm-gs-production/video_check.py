# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Decode the whole rendered video and compare it with the replay receipt."""
import argparse
import hashlib
import json
from pathlib import Path

import imageio_ffmpeg

p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
a=p.parse_args();receipt=json.loads((a.directory/'replay-check.json').read_text())
reader=imageio_ffmpeg.read_frames(str(a.directory/'task.mp4'),pix_fmt='rgb24')
metadata=next(reader);count=sum(1 for _ in reader)
assert count==receipt['frames'],(count,receipt['frames'])
assert list(metadata['size'])==receipt['resolution'],metadata
assert abs(metadata['fps']-receipt['fps'])<1e-6,metadata
assert receipt['replay_final_success'] and receipt['recorded_success']
digest=hashlib.sha256((a.directory/'task.mp4').read_bytes()).hexdigest()
assert digest==receipt['video_sha256']
result={'status':'passed','decoded_frames':count,'metadata':metadata,'sha256':digest}
(a.directory/'video-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
