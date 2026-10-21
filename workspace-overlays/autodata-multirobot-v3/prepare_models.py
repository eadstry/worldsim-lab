"""Derive local MuJoCo assets without editing the upstream URDFs."""
from pathlib import Path
import argparse, json, hashlib, xml.etree.ElementTree as E
import numpy as np
import mujoco, trimesh

def prepare_openarm(source, output):
    output.mkdir(parents=True, exist_ok=False)
    root = E.parse(source).getroot()
    for mesh in root.iter('mesh'):
        path = (source.parent / mesh.get('filename')).resolve()
        if path.suffix.lower() == '.dae':
            dest = output / (hashlib.sha256(str(path).encode()).hexdigest()[:12] + '.obj')
            if not dest.exists():
                scene = trimesh.load(str(path), force='scene')
                scene.to_geometry().export(dest)
            path = dest.resolve()
        mesh.set('filename', str(path))
    ext = E.SubElement(root, 'mujoco')
    E.SubElement(ext, 'compiler', dict(discardvisual='false', fusestatic='false', balanceinertia='true'))
    E.ElementTree(root).write(output / 'import.urdf')
    model = mujoco.MjModel.from_xml_path(str((output / 'import.urdf').resolve()))
    mujoco.mj_saveLastXML(str(output / 'model.xml'), model)
    (output / 'provenance.json').write_text(json.dumps({'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'mujoco': mujoco.__version__}, indent=2))

def prepare_g1d(source, output):
    output.mkdir(parents=True, exist_ok=False)
    root = E.parse(source).getroot()
    extension = root.find('mujoco')
    if extension is None:
        extension = E.SubElement(root, 'mujoco')
    compiler = extension.find('compiler')
    if compiler is None:
        compiler = E.SubElement(extension, 'compiler')
    compiler.set('meshdir', str((source.parent / 'meshes').resolve()))
    compiler.set('fusestatic', 'false')
    compiler.set('discardvisual', 'false')
    for mesh in root.iter('mesh'):
        mesh.set('filename', Path(mesh.get('filename')).name)
    E.ElementTree(root).write(output / 'import.urdf')
    model = mujoco.MjModel.from_xml_path(str((output / 'import.urdf').resolve()))
    mujoco.mj_saveLastXML(str(output / 'model.xml'), model)
    (output / 'provenance.json').write_text(json.dumps({'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'mujoco': mujoco.__version__, 'derivation': 'Resolve mesh paths and retain fixed links/visuals; no joint changes'}, indent=2))
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--robot', choices=['g1d', 'openarm'], default='openarm')
    a = p.parse_args()
    (prepare_g1d if a.robot == 'g1d' else prepare_openarm)(a.source, a.output)
