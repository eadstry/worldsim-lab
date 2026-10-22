"""Export compiled native visual geometry and local frames for Blender rendering."""
import argparse, json
from pathlib import Path
import mujoco, numpy as np
p = argparse.ArgumentParser()
p.add_argument('episode', type=Path)
a = p.parse_args()
summary = json.loads((a.episode / 'verification.json').read_text())
m = mujoco.MjModel.from_xml_path(str((a.episode / 'task.xml').resolve()))
visual_group = 2 if summary['robot'] == 'so101' else 1
geoms = []
arrays = {}
for i in range(m.ngeom):
    if m.geom_group[i] != visual_group or m.geom_dataid[i] < 0:
        continue
    mid = int(m.geom_dataid[i])
    name = 'mesh_' + str(mid)
    if name + '_vertices' not in arrays:
        arrays[name + '_vertices'] = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
        arrays[name + '_faces'] = m.mesh_face[m.mesh_faceadr[mid]:m.mesh_faceadr[mid] + m.mesh_facenum[mid]]
    geoms.append(dict(mesh=name, body=int(m.geom_bodyid[i]), pos=m.geom_pos[i].tolist(), quat=m.geom_quat[i].tolist(), rgba=(m.mat_rgba[m.geom_matid[i]] if m.geom_matid[i] >= 0 else m.geom_rgba[i]).tolist(), body_name=summary['body_names'][int(m.geom_bodyid[i])]))
np.savez_compressed(a.episode / 'visual_meshes.npz', **arrays)
(a.episode / 'visual_geoms.json').write_text(json.dumps(geoms))
