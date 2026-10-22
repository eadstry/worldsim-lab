"""Resolve concave native collision meshes into convex parts, keeping visual CAD intact."""
import argparse, copy, json, xml.etree.ElementTree as E
from pathlib import Path
import coacd, numpy as np, trimesh
p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('out', type=Path)
p.add_argument('--robot', required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
r = E.parse(a.source).getroot()
comp = r.find('compiler')
meshdir = (a.source.parent / comp.get('meshdir', '.')).resolve()
comp.set('meshdir', str(meshdir))
assets = r.find('asset')
meshes = {m.get('name', Path(m.get('file', 'none')).stem): m for m in assets.findall('mesh')}
cache = {}
report = []
for b in r.find('worldbody').iter('body'):
    name = b.get('name', '')
    if not ('hand' in name and name.startswith('right_') if a.robot == 'g1d' else 'gripper' in name or 'jaw' in name if a.robot == 'so101' else 'right_ee' in name):
        continue
    for g in list(b.findall('geom')):
        if g.get('group') in ['1', '2'] or g.get('mesh') is None:
            continue
        mn = g.get('mesh')
        mesh = meshes[mn]
        if mn not in cache:
            path = meshdir / mesh.get('file')
            tri = trimesh.load(path, force='mesh')
            v = np.asarray(tri.vertices) * np.fromstring(mesh.get('scale', '1 1 1'), sep=' ')
            faces = np.asarray(tri.faces)
            coacd.set_log_level('error')
            parts = coacd.run_coacd(coacd.Mesh(v, faces), threshold=0.05, max_convex_hull=20, preprocess_mode='auto', resolution=500, mcts_nodes=15, mcts_iterations=70, mcts_max_depth=3, seed=19)
            cache[mn] = []
            for k, (pv, pf) in enumerate(parts):
                dest = (a.out / f'{mn}-{k}.obj').resolve()
                trimesh.Trimesh(pv, pf, process=False).export(dest)
                partname = mn + '_convex_' + str(k)
                E.SubElement(assets, 'mesh', dict(name=partname, file=str(dest)))
                cache[mn].append(partname)
            print(name, mn, len(parts), flush=True)
            report.append(dict(body=name, source=str(path), parts=len(parts)))
        b.remove(g)
        for part in cache[mn]:
            new = copy.deepcopy(g)
            new.set('mesh', part)
            new.set('name', g.get('name', name) + '_' + part)
            b.append(new)
E.ElementTree(r).write(a.out / 'model.xml')
(a.out / 'collision-provenance.json').write_text(json.dumps(report, indent=2))
