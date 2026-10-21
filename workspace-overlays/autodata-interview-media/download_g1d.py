# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Download an immutable official Unitree G1-D URDF and its referenced meshes."""
import argparse, concurrent.futures, hashlib, json, subprocess, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--revision',help='Explicit immutable official commit; omitted to resolve master once');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
repo='https://github.com/unitreerobotics/unitree_ros.git'
sha=a.revision or subprocess.check_output(['git','ls-remote',repo,'refs/heads/master'],text=True).split()[0]
assert len(sha)==40 and all(c in '0123456789abcdef' for c in sha),'Use a full immutable commit SHA'
base=f'https://raw.githubusercontent.com/unitreerobotics/unitree_ros/{sha}/'
def fetch(path,target):
 data=urllib.request.urlopen(base+path,timeout=120).read();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 assert not data.startswith(b'version https://git-lfs'),f'LFS pointer: {path}'
 return dict(path=str(target.relative_to(a.output)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),url=base+path)
prefix='robots/g1_d_description/'
records=[fetch(prefix+'g1_d.urdf',a.output/'g1_d.urdf')]
r=ET.parse(a.output/'g1_d.urdf').getroot();meshes=sorted({x.attrib['filename'] for x in r.iter('mesh')})
assert all(not Path(m).is_absolute() and '..' not in Path(m).parts and Path(m).parts[0]=='meshes' for m in meshes),'Unexpected mesh path outside the model directory'
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 records+=list(ex.map(lambda m:fetch(prefix+m,a.output/m),meshes))
for n in ['LICENSE','README.md']:
 try:records.append(fetch(n,a.output/n))
 except Exception as e:print(n,type(e).__name__)
manifest=dict(repository=repo,commit=sha,robot=r.attrib['name'],files=records,links=len(r.findall('link')),joints=[dict(name=j.attrib['name'],type=j.attrib['type']) for j in r.findall('joint')])
(a.output/'download-manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(dict(commit=sha,files=len(records),bytes=sum(x['bytes'] for x in records),robot=manifest['robot']),indent=2))
