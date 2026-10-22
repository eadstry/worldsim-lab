"""Create a separate static-house reference layer with the native dining table."""
import argparse
import hashlib
import json
from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

REVISION = "f2c633749e7fdf3f981dfd1dd83fc253786713ac"
HOME_SHA256 = "d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6"
DINING = "/HomeTask/Home/livingRoom1/livingRoom1_diningtable_1587793_yflib019"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(args.home.read_bytes()).hexdigest() == HOME_SHA256
    args.output.mkdir(parents=True, exist_ok=False)
    output = (args.output / "home-franka.usda").resolve()
    stage = Usd.Stage.CreateNew(str(output))
    root = UsdGeom.Xform.Define(stage, "/HomeTask")
    stage.SetDefaultPrim(root.GetPrim())
    # The asset spawner authors init_state on the default prim. Keep that root
    # identity so its placement does not overwrite the native-coordinate offset.
    home = UsdGeom.Xform.Define(stage, "/HomeTask/Home")
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    home.GetPrim().GetReferences().AddReference(str(args.home.resolve()), "/root")
    # Native table top z=.75 m. Robot origin sits on its left edge.
    translation = (-22.35, 4.75, -0.75)
    home.MakeMatrixXform().Set(Gf.Matrix4d().SetTranslate(Gf.Vec3d(*translation)))
    stats = dict(frozen_bodies=0, disabled_joints=0, disabled_lights=0)
    for prim in list(Usd.PrimRange(home.GetPrim())):
        if prim.IsInstance():
            prim.SetInstanceable(False)
    for prim in list(Usd.PrimRange(home.GetPrim())):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
            stats["frozen_bodies"] += 1
        if prim.IsA(UsdPhysics.Joint):
            UsdPhysics.Joint(prim).CreateJointEnabledAttr(False)
            stats["disabled_joints"] += 1
        if prim.HasAPI(UsdLux.LightAPI):
            prim.SetActive(False)
            stats["disabled_lights"] += 1
    removed = []
    removed = [str(prim.GetPath()) for prim in Usd.PrimRange(stage.GetPrimAtPath(DINING))
               if prim.GetName().startswith(("ornament_", "diningChair"))]
    for path in removed:
        prim = stage.GetPrimAtPath(path)
        if prim:
            prim.SetActive(False)
    for path in ("/HomeTask/Home/ceiling", "/HomeTask/Home/Cam1"):
        prim = stage.GetPrimAtPath(path)
        if prim:
            prim.SetActive(False)
    stage.GetRootLayer().Save()
    manifest = dict(
        repository="Yootta/World-SimReady-Home-mini", revision=REVISION,
        home=str(args.home.resolve()), home_sha256=HOME_SHA256,
        layer=str(output), layer_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        translation=translation, native_tabletop_z=0.0, native_floor_z=-0.75,
        task_surface="original diningTable002/mesh059; original collisions retained",
        removed=removed, household_physics="static collision; unrelated joints disabled", **stats,
    )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
