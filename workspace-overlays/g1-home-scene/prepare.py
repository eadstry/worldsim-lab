# SPDX-License-Identifier: Apache-2.0
"""Build a non-destructive static-house USD variant for the original G1 task."""
import argparse
import hashlib
import json
from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

REVISION = 'f2c633749e7fdf3f981dfd1dd83fc253786713ac'
DINING = '/root/livingRoom1/livingRoom1_diningtable_1587793_yflib019'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--galileo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.home.is_file() and args.galileo.is_file()
    expected = 'd38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6'
    assert hashlib.sha256(args.home.read_bytes()).hexdigest() == expected, 'Home asset revision/hash mismatch'
    args.output.mkdir(parents=True, exist_ok=False)
    stage = Usd.Stage.CreateNew(str((args.output / 'home-g1.usda').resolve()))
    root = UsdGeom.Xform.Define(stage, '/HomeTask')
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    home = stage.DefinePrim('/HomeTask/Home')
    home.GetReferences().AddReference(str(args.home.resolve()), '/root')
    UsdGeom.Xformable(home).MakeMatrixXform().Set(Gf.Matrix4d().SetTranslate(Gf.Vec3d(-22.4, 4.35, -0.795)))
    # Static household variant: preserve furniture collision while avoiding unrelated
    # articulated furniture dynamics and reset ownership in the manipulation task.
    stats = dict(frozen_bodies=0, disabled_joints=0, disabled_lights=0)
    for prim in list(Usd.PrimRange(home)):
        if prim.IsInstance():
            prim.SetInstanceable(False)
    for prim in list(Usd.PrimRange(home)):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
            stats['frozen_bodies'] += 1
        if prim.IsA(UsdPhysics.Joint):
            UsdPhysics.Joint(prim).CreateJointEnabledAttr(False)
            stats['disabled_joints'] += 1
        if prim.HasAPI(UsdLux.LightAPI):
            prim.SetActive(False)
            stats['disabled_lights'] += 1
    # The dining table includes chairs. Clear only this group for the task fixtures.
    stage.OverridePrim('/HomeTask/Home' + DINING.removeprefix('/root')).SetActive(False)
    UsdGeom.Imageable(stage.GetPrimAtPath('/HomeTask/Home/ceiling')).MakeInvisible()
    stage.OverridePrim('/HomeTask/Home/Cam1').SetActive(False)
    fixtures = stage.DefinePrim('/HomeTask/Fixtures')
    fixtures.GetReferences().AddReference(str(args.galileo.resolve()), '/Lab')
    UsdGeom.Xformable(fixtures).MakeMatrixXform().Set(Gf.Matrix4d().SetTranslate(Gf.Vec3d(4.420, 1.408, -0.795)))
    for child in list(fixtures.GetChildren()):
        if child.GetName() not in ('TaskAssets', 'Looks'):
            child.SetActive(False)
    stage.OverridePrim('/HomeTask/Fixtures/TaskAssets/power_drill_physics').SetActive(False)
    dome = UsdLux.DomeLight.Define(stage, '/HomeTask/DiagnosticDome')
    dome.CreateIntensityAttr(1000.0)
    key = UsdLux.RectLight.Define(stage, '/HomeTask/DiagnosticKey')
    key.CreateIntensityAttr(1000.0)
    key.CreateWidthAttr(4.0)
    key.CreateHeightAttr(4.0)
    UsdGeom.Xformable(key).AddTranslateOp().Set(Gf.Vec3d(0.0, -0.6, 2.0))
    stage.GetRootLayer().Save()
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(
        repository='Yootta/World-SimReady-Home-mini', revision=REVISION,
        home=str(args.home.resolve()), home_sha256=digest(args.home),
        galileo=str(args.galileo.resolve()), galileo_sha256=digest(args.galileo),
        layer=str((args.output / 'home-g1.usda').resolve()),
        layer_sha256=digest(args.output / 'home-g1.usda'),
        home_translation=[-22.4, 4.35, -0.795],
        floor_z=-0.795, removed_house_furniture=[DINING], ceiling='invisible for diagnostics',
        household_physics='Static collisions; household joints disabled',
        retained_task_geometry=['original shelf', 'original table'],
        diagnostic_lighting={'dome_intensity': 1000, 'rect_intensity': 1000}, **stats,
    )
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
