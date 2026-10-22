# Copyright (c) 2026.
# SPDX-License-Identifier: Apache-2.0

"""Render the delivered GS assets in Isaac Sim, without importing AutoData.

This is a USD composition/RGB smoke test, not an AutoData environment rollout.
Run with Isaac Sim's python.sh through the shared task queue.
"""
import argparse
import faulthandler
import hashlib
import json
from pathlib import Path
import zipfile
import traceback


def prepare(package, output):
    """Verify every manifest entry before extracting into an independent directory."""
    with zipfile.ZipFile(package) as archive:
        roots = {Path(n).parts[0] for n in archive.namelist()}
        if len(roots) != 1:
            raise ValueError('Expected one package root')
        root = roots.pop()
        manifest = json.loads(archive.read(root + '/MANIFEST.json'))
        for entry in archive.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe ZIP member: ' + entry.filename)
        for entry in manifest['files']:
            data = archive.read(root + '/' + entry['path'])
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Manifest mismatch: ' + entry['path'])
        archive.extractall(output / 'assets')
    return output / 'assets' / root / 'AutoData/openarm_autodata', manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    base, manifest = prepare(args.package, args.output)
    faulthandler.dump_traceback_later(60, repeat=True)
    print('Package hashes verified', flush=True)
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': True, 'width': 1280, 'height': 960,
                         'renderer': 'RaytracedLighting'})
    exit_code = 1
    try:
        import numpy as np
        import yaml
        from PIL import Image
        import omni.usd
        import omni.replicator.core as rep
        from pxr import Gf, UsdGeom, UsdLux

        cfg_path = Path(__file__).resolve().parent / 'configs/openarm_autodata/tasks/pick_place/configs/scenes/gs_table.yaml'
        cfg = yaml.safe_load(cfg_path.read_text())
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, '/World')
        stage.SetDefaultPrim(world.GetPrim())
        assets = base / 'assets'

        def add(name, relative, position, quat=(0, 0, 0, 1), scale=None):
            path = assets / relative
            print('Composing ' + name, flush=True)
            prim = stage.DefinePrim('/World/' + name, 'Xform')
            if not prim.GetReferences().AddReference(str(path)):
                raise RuntimeError('Failed reference: ' + str(path))
            xf = UsdGeom.Xformable(prim)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp(opSuffix='preview').Set(Gf.Vec3d(*position))
            xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble, opSuffix='preview').Set(Gf.Quatd(quat[3], Gf.Vec3d(*quat[:3])))
            if scale:
                xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble, opSuffix='preview').Set(Gf.Vec3d(*scale))

        add('Table', cfg['table_usd'], cfg['table_position'], cfg['table_orientation'])
        add('Nightstand', 'nightstand/nightstand_fixed.usda', cfg['nightstand_position'],
            cfg['nightstand_orientation'], cfg['nightstand_scale'])
        add('Robot', 'openarm_v2/usd/openarm_v20_bimanual/openarm_v20_bimanual.usda', cfg['robot_position'])
        add('Cube', 'blue_cube/blue_cube.usd', cfg['cube_spawn_left'])
        # Same relative pad transform as scene_layout.py; current layout has zero pitch/yaw.
        pad = cfg['mousepad']
        if pad['yaw'] != 0 or pad.get('pitch', 0) != 0:
            raise ValueError('This smoke test supports the delivered zero pad yaw/pitch only')
        q = cfg['table_orientation']
        rotation = Gf.Rotation(Gf.Quatd(q[3], Gf.Vec3d(*q[:3])))
        pos = Gf.Vec3d(*cfg['table_position']) + rotation.TransformDir(Gf.Vec3d(*pad['position']))
        add('Mousepad', pad['usd'], pos, q, (1, 1, 1.66))
        errors = [str(e) for e in stage.GetCompositionErrors()]
        if errors:
            raise RuntimeError('USD composition errors: ' + repr(errors))
        light = UsdLux.DomeLight.Define(stage, '/World/PreviewLight')
        light.CreateIntensityAttr(1800)
        print('Creating camera', flush=True)
        camera = rep.create.camera(position=(-1.0, -1.65, 2.05), look_at=(0.55, 0.05, 0.95), focal_length=24)
        product = rep.create.render_product(camera, (1280, 960))
        rgb = rep.AnnotatorRegistry.get_annotator('rgb')
        rgb.attach(product)
        print('Warming renderer', flush=True)
        for _ in range(90):
            app.update()
        for _ in range(16):
            rep.orchestrator.step(rt_subframes=4, pause_timeline=True)
        data = np.asarray(rgb.get_data())
        if data.shape[:2] != (960, 1280) or data[..., :3].std() < 2:
            raise RuntimeError('Invalid or blank RGB output: ' + str(data.shape))
        Image.fromarray(data).save(args.output / 'example.png')
        types = {}
        splats = []
        for prim in stage.Traverse():
            typ = prim.GetTypeName()
            types[typ] = types.get(typ, 0) + 1
            if 'Gaussian' in typ or 'ParticleField' in typ:
                splats.append({'path': str(prim.GetPath()), 'type': typ})
        if not splats:
            raise RuntimeError('No Gaussian prim found in composed scene')
        faulthandler.cancel_dump_traceback_later()
        stage.GetRootLayer().Export(str(args.output / 'scene.usda'))
        result = {'status': 'passed', 'scope': 'USD composition and RTX RGB only; no physics or AutoData rollout',
                  'robot_pose': 'Authored USD pose, not task initial joint configuration',
                  'package_sha256': hashlib.sha256(args.package.read_bytes()).hexdigest(),
                  'verified_files': len(manifest['files']), 'source_commit': manifest['source_commit'],
                  'config': str(cfg_path), 'composition_errors': errors, 'gaussian_prims': splats,
                  'prim_type_counts': types, 'rgb_shape': list(data.shape), 'rgb_std': float(data[..., :3].std()),
                  'table_surface_z_m': cfg['table_height'], 'mousepad_center_m': list(pos),
                  'image': 'example.png'}
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
        exit_code = 0
    except BaseException:
        traceback.print_exc()
        raise
    finally:
        app.close(exit_code=exit_code)


if __name__ == '__main__':
    main()
