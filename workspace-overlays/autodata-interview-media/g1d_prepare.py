# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Compile the downloaded, unedited official URDF to inspect native joints."""
import argparse,json
import xml.etree.ElementTree as ET
from pathlib import Path
import mujoco
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
r=ET.parse(a.input);compiler=r.find('mujoco/compiler');compiler.set('meshdir',str((a.input.parent/'meshes').resolve()));compiler.set('fusestatic','false')
for mesh in r.iter('mesh'):mesh.set('filename',Path(mesh.attrib['filename']).name)
derived=a.output/'mujoco-import.urdf';r.write(derived)
m=mujoco.MjModel.from_xml_path(str(derived.resolve()))
mujoco.mj_saveLastXML(str(a.output/'official.xml'),m)
d=mujoco.MjData(m);mujoco.mj_forward(m,d)
r=dict(nq=m.nq,nv=m.nv,bodies=[dict(name=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i),pos=d.xpos[i].tolist()) for i in range(m.nbody)],joints=[dict(name=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_JOINT,i),range=m.jnt_range[i].tolist(),type=int(m.jnt_type[i])) for i in range(m.njnt)])
(a.output/'inspection.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
