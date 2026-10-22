"""Create portable datasets/media/model bundles with per-file hashes and ZIP CRC checks."""
import argparse, hashlib, json, os, re, shutil, zipfile, xml.etree.ElementTree as E
from pathlib import Path

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

def tree(source, dest):
    for path in sorted(source.rglob('*')):
        if path.is_file() and '.git' not in path.parts and ('__pycache__' not in path.parts):
            copy(path, dest / path.relative_to(source))

def portable_model(source, dest):
    root = E.parse(source).getroot()
    compiler = root.find('compiler')
    meshdir = (source.parent / compiler.get('meshdir', '.')).resolve()
    compiler.set('meshdir', 'meshes')
    manifest = []
    for mesh in root.findall('asset/mesh'):
        path = meshdir / mesh.get('file')
        mesh.set('name', mesh.get('name', path.stem))
        sha = digest(path)
        name = sha[:12] + '-' + path.name
        copy(path, dest / 'meshes' / name)
        mesh.set('file', name)
        manifest.append(dict(file=name, sha256=sha))
    dest.mkdir(parents=True, exist_ok=True)
    E.ElementTree(root).write(dest / 'model.xml')
    (dest / 'mesh-manifest.json').write_text(json.dumps(manifest, indent=2))

def relocate_task(source, dest, meshdir):
    root = E.parse(source).getroot()
    compiler = root.find('compiler')
    original = (source.parent / compiler.get('meshdir', '.')).resolve()
    compiler.set('meshdir', os.path.relpath(meshdir, dest.parent))
    for mesh in root.findall('asset/mesh'):
        path = original / mesh.get('file')
        mesh.set('name', mesh.get('name', path.stem))
        mesh.set('file', digest(path)[:12] + '-' + path.name)
    E.ElementTree(root).write(dest)

def zip_bundle(stage, dest, robot=None):
    if dest.exists():
        raise FileExistsError(dest)
    paths = []
    overrides = {}
    original = json.loads((stage / 'manifest.json').read_text())
    for path in sorted(stage.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(stage)
        if str(rel) == 'manifest.json':
            continue
        if robot and rel.parts[0] in ['datasets', 'production'] and (rel.parts[1] != robot):
            continue
        if robot and rel.parts[0] == 'presentation' and (not rel.name.startswith(robot + '-')) and (rel.name != 'manifest.json'):
            continue
        if robot and rel.parts[0] == 'presentation' and (rel.name == 'manifest.json'):
            overrides[str(rel)] = json.dumps([item for item in json.loads(path.read_text()) if item['robot'] == robot], indent=2).encode()
        if robot and rel.suffix == '.html' and ('gallery' in rel.name):
            page = path.read_text()
            page = re.sub('<article class="card" data-robot="([^"]+)".*?</article>', lambda match: match.group(0) if match.group(1) == robot else '', page, flags=re.S)
            validation = json.loads((stage / 'datasets' / robot / 'validation.json').read_text())
            name = {'g1d': '宇树 G1-D', 'openarm': 'OpenArm', 'so101': 'SO101'}[robot]
            page = page.replace('36 条演示', '12 条演示').replace('三套独立数据', '独立本体数据').replace('三种机器人，两类任务。', name + '，两类任务。').replace('20,484 帧', f"{validation['frames']:,} 帧")
            page = re.sub('<option value="(g1d|openarm|so101)">.*?</option>', lambda match: match.group(0) if match.group(1) == robot else '', page)
            overrides[str(rel)] = page.encode()
        paths.append((path, rel))
    manifest = dict(original)
    manifest['files'] = {str(rel): dict(original['files'][str(rel)]) for _, rel in paths}
    if robot:
        validation = json.loads((stage / 'datasets' / robot / 'validation.json').read_text())
        manifest.update(robot=robot, episodes=validation['episodes'], frames=validation['frames'])
    for name, data in overrides.items():
        manifest['files'][name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    partial = dest.with_name(dest.name + '.partial')
    if partial.exists():
        raise FileExistsError(partial)
    with zipfile.ZipFile(partial, 'w', allowZip64=True) as archive:
        for path, rel in paths:
            stored = path.suffix.lower() in ['.mp4', '.png', '.npz', '.usdz', '.parquet']
            if str(rel) in overrides:
                archive.writestr(str(rel), overrides[str(rel)], compress_type=zipfile.ZIP_DEFLATED)
            else:
                archive.write(path, str(rel), compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED, compresslevel=None if stored else 4)
        archive.writestr('manifest.json', json.dumps(manifest, indent=2), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(partial) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest['files']) | {'manifest.json'}
        for name, expected in manifest['files'].items():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    h.update(block)
            assert h.hexdigest() == expected['sha256'], name
    partial.rename(dest)
    return dict(file=dest.name, bytes=dest.stat().st_size, sha256=digest(dest), files=len(paths) + 1)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--gallery', type=Path, required=True)
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--scene-blend', type=Path, required=True)
    p.add_argument('--g1-official', type=Path, required=True)
    p.add_argument('--openarm-official', type=Path, required=True)
    p.add_argument('--so101-official', type=Path, required=True)
    p.add_argument('--date', default='20261021')
    a = p.parse_args()
    a.root = a.root.resolve()
    delivery = a.root / 'delivery'
    delivery.mkdir(exist_ok=True)
    stage = delivery / f'autodata-multirobot-v3-hd36-{a.date}'
    stage.mkdir(exist_ok=False)
    scripts = Path(__file__).resolve().parent
    for robot in ['g1d', 'openarm', 'so101']:
        validation = json.loads((a.root / 'datasets' / robot / 'validation.json').read_text())
        assert validation['episodes'] == 12 and validation['all_numeric_rows_exact']
        tree(a.root / 'datasets' / robot, stage / 'datasets' / robot)
        domains = []
        for index in range(12):
            episode = a.root / 'production' / robot / f'episode-{index:02d}'
            info = json.loads((episode / 'verification.json').read_text())
            assert info['success']
            media = json.loads((episode / 'media-verification.json').read_text())
            assert media['sha256'] == digest(episode / 'overview.mp4')
            for name in ['trajectory.npz', 'verification.json', 'generation_job.json', 'overview.mp4', 'poster-initial.png', 'poster-grasp.png', 'poster-final.png', 'media-verification.json', 'task.xml']:
                copy(episode / name, stage / 'production' / robot / episode.name / name)
            relocate_task(episode / 'task.xml', stage / 'production' / robot / episode.name / 'task.xml', stage / 'assets' / 'models' / robot / 'meshes')
            domains.append(dict(episode_index=index, simulation=info, render=media['render']))
        domainmeta = dict(schema_version=1, conditions=['baseline', 'warm_light', 'cool_light', 'layout_and_camera', 'material', 'background_replacement'], episodes=domains)
        (stage / 'datasets' / robot / 'meta' / 'domain_randomization.json').write_text(json.dumps(domainmeta, indent=2))
        model = a.root / 'assets' / ('g1d-collision' if robot == 'g1d' else 'openarm-collision' if robot == 'openarm' else 'so101-collision') / ('model-r2.xml' if robot == 'openarm' else 'model.xml')
        portable_model(model, stage / 'assets' / 'models' / robot)
        copy(a.root / 'production' / robot / 'simulation-progress.json', stage / 'provenance' / f'{robot}-attempts.json')
        import mujoco, numpy as np
        original = mujoco.MjModel.from_xml_path(str((a.root / 'production' / robot / 'episode-00' / 'task.xml').resolve()))
        relocated = mujoco.MjModel.from_xml_path(str((stage / 'production' / robot / 'episode-00' / 'task.xml').resolve()))
        for field in ['jnt_range', 'mesh_vert', 'geom_pos', 'geom_quat', 'body_pos', 'body_quat', 'actuator_forcerange']:
            np.testing.assert_array_equal(getattr(original, field), getattr(relocated, field))
    for path in scripts.glob('*.py'):
        copy(path, stage / 'source' / path.name)
    for version in ['v1', 'v2', 'v3', 'v4', 'render-final', 'render-bulk', 'render-hero']:
        source = a.root / 'source-snapshots' / version
        if source.exists():
            tree(source, stage / 'source-snapshots' / version)
    for name in ['action-state-replay-final.json', 'geometry-alignment.json', 'portable-model-validation.json', 'asset-provenance.json']:
        copy(a.root / name, stage / 'provenance' / name)
    if (a.root / 'presentation').exists():
        tree(a.root / 'presentation', stage / 'presentation')
    copy(a.scene, stage / 'assets' / 'worldsimready-mini' / 'scene000430.usdz')
    copy(a.scene_blend, stage / 'assets' / 'worldsimready-mini' / 'home.blend')
    tree(a.g1_official, stage / 'assets' / 'official-g1d')
    tree(a.openarm_official, stage / 'assets' / 'official-openarm')
    tree(a.so101_official, stage / 'assets' / 'official-so101')
    so_license = a.so101_official.parents[1] / 'LICENSE'
    if so_license.exists():
        copy(so_license, stage / 'assets' / 'official-so101' / 'LICENSE')
    report = a.report.read_text().replace('../../workspace-overlays/autodata-multirobot-v3/', '../../source/')
    (stage / 'docs' / 'autodata').mkdir(parents=True, exist_ok=True)
    (stage / 'docs' / 'autodata' / a.report.name).write_text(report)
    gallery = a.gallery.read_text().replace('../../runs/multirobot-v3/', '../../')
    (stage / 'docs' / 'autodata' / a.gallery.name).write_text(gallery)
    files = {str(path.relative_to(stage)): dict(bytes=path.stat().st_size, sha256=digest(path)) for path in sorted(stage.rglob('*')) if path.is_file()}
    (stage / 'manifest.json').write_text(json.dumps(dict(format='LeRobot v3.0', episodes=36, frames=20484, resolution=[1920, 1080], fps=30, files=files), indent=2))
    bundles = []
    for robot in ['g1d', 'openarm', 'so101']:
        bundles.append(zip_bundle(stage, delivery / f'{robot}-lerobot-v3-hd12-{a.date}.zip', robot))
        print('SEALED', robot, flush=True)
    bundles.append(zip_bundle(stage, delivery / f'autodata-multirobot-lerobot-v3-hd36-{a.date}.zip'))
    (delivery / 'delivery.json').write_text(json.dumps(bundles, indent=2))
    print(json.dumps(bundles, indent=2), flush=True)
if __name__ == '__main__':
    main()
