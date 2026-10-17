# SPDX-License-Identifier: Apache-2.0
"""Prepare reproducible, episode-scoped domain randomization ablations."""
import argparse
import hashlib
import json
import random
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

PROFILES = [
    ('baseline', 1, 100, []),
    ('lighting', 1, 101, ['lighting']),
    ('camera', 1, 102, ['camera']),
    ('material', 1, 103, ['material']),
    ('combined_s1', 1, 104, ['lighting', 'camera', 'material', 'pose_mild']),
    ('combined_s2', 2, 105, ['lighting', 'camera', 'material', 'pose_mild']),
    ('pose_wide', 1, 106, ['pose_wide']),
]


def material(stage, path, color, roughness, targets):
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + '/Surface')
    shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
    for target in targets:
        prim = stage.GetPrimAtPath(target)
        assert prim.IsValid(), target
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat, bindingStrength=UsdShade.Tokens.strongerThanDescendants)


def sample(seed, active):
    rng = random.Random(seed)
    result = {}
    if 'lighting' in active:
        result['lighting'] = dict(dome_intensity=rng.uniform(650, 1100),
                                  key_intensity=rng.uniform(700, 1300),
                                  temperature_k=rng.uniform(4000, 6500), yaw_deg=rng.uniform(0, 360))
    if 'camera' in active:
        result['camera'] = dict(local_translation_m=[rng.uniform(-.005, .005) for _ in range(3)],
                                local_rpy_deg=[rng.uniform(-2, 2) for _ in range(3)],
                                focal_scale=rng.uniform(.95, 1.05))
    if 'material' in active:
        gray = rng.uniform(.35, .65)
        wall = rng.uniform(.65, .85)
        result['material'] = dict(floor_color=[gray * 1.02, gray, gray * .96],
                                  wall_color=[wall, wall * .98, wall * .94],
                                  floor_roughness=rng.uniform(.45, .9), wall_roughness=rng.uniform(.6, .95))
    if 'pose_mild' in active:
        result['pose'] = dict(xy_half_range_m=.035, yaw_half_range_deg=3.)
    if 'pose_wide' in active:
        result['pose'] = dict(xy_half_range_m=.08, yaw_half_range_deg=10.)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-layer', type=Path, required=True)
    parser.add_argument('--hdr', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.base_layer.is_file() and args.hdr.is_file()
    args.output.mkdir(parents=True, exist_ok=False)
    base_sha = hashlib.sha256(args.base_layer.read_bytes()).hexdigest()
    hdr_sha = hashlib.sha256(args.hdr.read_bytes()).hexdigest()
    plans = []
    for name, seed, dr_seed, active in PROFILES:
        folder = args.output / name
        folder.mkdir()
        layer = folder / 'scene.usda'
        stage = Usd.Stage.CreateNew(str(layer.resolve()))
        stage.GetRootLayer().subLayerPaths.append(str(args.base_layer.resolve()))
        stage.SetDefaultPrim(stage.GetPrimAtPath('/HomeTask'))
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        values = sample(dr_seed, active)
        if 'lighting' in values:
            value = values['lighting']
            dome = UsdLux.DomeLight(stage.GetPrimAtPath('/HomeTask/DiagnosticDome'))
            dome.CreateTextureFileAttr(Sdf.AssetPath(str(args.hdr.resolve())))
            dome.CreateTextureFormatAttr('latlong')
            dome.CreateIntensityAttr(value['dome_intensity'])
            UsdGeom.Xformable(dome).AddRotateZOp().Set(value['yaw_deg'])
            key = UsdLux.RectLight(stage.GetPrimAtPath('/HomeTask/DiagnosticKey'))
            key.CreateIntensityAttr(value['key_intensity'])
            key.CreateEnableColorTemperatureAttr(True)
            key.CreateColorTemperatureAttr(value['temperature_k'])
        if 'material' in values:
            value = values['material']
            material(stage, '/HomeTask/DRFloor', value['floor_color'], value['floor_roughness'],
                     ['/HomeTask/Home/ground/ground_livingRoom1_YF_yaguangzhuan_333289'])
            material(stage, '/HomeTask/DRWall', value['wall_color'], value['wall_roughness'], ['/HomeTask/Home/wall'])
        stage.GetRootLayer().Save()
        plan = dict(schema_version=1, name=name, generation_seed=seed, randomization_seed=dr_seed,
                    active=active, sampled=values, scene=str(layer.resolve()),
                    scene_sha256=hashlib.sha256(layer.read_bytes()).hexdigest(),
                    base_layer=str(args.base_layer.resolve()), base_layer_sha256=base_sha,
                    hdr=str(args.hdr.resolve()), hdr_sha256=hdr_sha,
                    scope='One fixed sample per generated episode; reset pose sampled by simulator; diagnostic cameras fixed')
        path = folder / 'plan.json'
        path.write_text(json.dumps(plan, indent=2))
        plans.append(str(path.resolve()))
    (args.output / 'plans.json').write_text(json.dumps(plans, indent=2))
    print('\n'.join(plans))


if __name__ == '__main__':
    main()
