# SPDX-License-Identifier: Apache-2.0
"""Check scene entry metadata, input ownership and deterministic sampling."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from pxr import Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade
import prepare_batch


class PreparationTests(unittest.TestCase):
    def test_sampling_deterministic_and_bounded(self):
        active = ['lighting', 'camera', 'material', 'pose_mild']
        random.seed(7)
        expected_next = random.random()
        random.seed(7)
        a = prepare_batch.sample(104, active)
        self.assertEqual(random.random(), expected_next)
        self.assertEqual(a, prepare_batch.sample(104, active))
        self.assertNotEqual(a, prepare_batch.sample(105, active))
        self.assertTrue(all(abs(v) <= .005 for v in a['camera']['local_translation_m']))
        self.assertTrue(all(abs(v) <= 2 for v in a['camera']['local_rpy_deg']))
        self.assertTrue(.95 <= a['camera']['focal_scale'] <= 1.05)
        self.assertEqual(prepare_batch.sample(100, []), {})

    def test_variants_preserve_entry_units_physics_and_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            base = folder / 'base.usda'
            stage = Usd.Stage.CreateNew(str(base))
            root = UsdGeom.Xform.Define(stage, '/HomeTask').GetPrim()
            stage.SetDefaultPrim(root)
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            floor_path = '/HomeTask/Home/ground/ground_livingRoom1_YF_yaguangzhuan_333289'
            floor = UsdGeom.Mesh.Define(stage, floor_path).GetPrim()
            UsdPhysics.CollisionAPI.Apply(floor).CreateCollisionEnabledAttr(True)
            physics_mat = UsdShade.Material.Define(stage, '/HomeTask/OriginalPhysics')
            physics = UsdPhysics.MaterialAPI.Apply(physics_mat.GetPrim())
            physics.CreateStaticFrictionAttr(.58)
            physics.CreateDynamicFrictionAttr(.48)
            physics.CreateRestitutionAttr(.13)
            UsdShade.MaterialBindingAPI.Apply(floor).Bind(physics_mat)
            UsdGeom.Xform.Define(stage, '/HomeTask/Home/wall')
            UsdLux.DomeLight.Define(stage, '/HomeTask/DiagnosticDome').CreateIntensityAttr(1000)
            UsdLux.RectLight.Define(stage, '/HomeTask/DiagnosticKey').CreateIntensityAttr(1000)
            stage.GetRootLayer().Save()
            hdr = folder / 'placeholder.hdr'
            hdr.write_bytes(b'writer-only fixture; not rendered')
            initial_hash = hashlib.sha256(base.read_bytes()).hexdigest()
            command = [sys.executable, str(Path(prepare_batch.__file__).resolve()), '--base-layer', str(base),
                       '--hdr', str(hdr), '--output', str(folder / 'output')]
            subprocess.run(command, check=True, capture_output=True)
            plans = json.loads((folder / 'output/plans.json').read_text())
            self.assertEqual(len(plans), 8)
            for path in plans:
                plan = json.loads(Path(path).read_text())
                variant = Usd.Stage.Open(plan['scene'])
                self.assertEqual(str(variant.GetDefaultPrim().GetPath()), '/HomeTask')
                self.assertEqual(UsdGeom.GetStageUpAxis(variant), 'Z')
                self.assertEqual(UsdGeom.GetStageMetersPerUnit(variant), 1.0)
                self.assertTrue(UsdPhysics.CollisionAPI(variant.GetPrimAtPath(floor_path)).GetCollisionEnabledAttr().Get())
                if 'material' in plan['sampled']:
                    bound, _ = UsdShade.MaterialBindingAPI(variant.GetPrimAtPath(floor_path)).ComputeBoundMaterial()
                    self.assertEqual(str(bound.GetPath()), '/HomeTask/DRFloor')
                    original, _ = UsdShade.MaterialBindingAPI(variant.GetPrimAtPath(floor_path)).ComputeBoundMaterial(materialPurpose='physics')
                    self.assertEqual(str(original.GetPath()), '/HomeTask/OriginalPhysics')
                    physical = UsdPhysics.MaterialAPI(original.GetPrim())
                    self.assertAlmostEqual(physical.GetStaticFrictionAttr().Get(), .58, places=6)
                    self.assertAlmostEqual(physical.GetDynamicFrictionAttr().Get(), .48, places=6)
                    self.assertAlmostEqual(physical.GetRestitutionAttr().Get(), .13, places=6)
                if 'lighting' in plan['sampled']:
                    light = UsdLux.DomeLight(variant.GetPrimAtPath('/HomeTask/DiagnosticDome'))
                    self.assertAlmostEqual(light.GetIntensityAttr().Get(), plan['sampled']['lighting']['dome_intensity'], places=3)
            self.assertEqual(hashlib.sha256(base.read_bytes()).hexdigest(), initial_hash)
            # Refuse to overwrite even a prepared, successful experiment directory.
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(hashlib.sha256(base.read_bytes()).hexdigest(), initial_hash)


if __name__ == '__main__':
    unittest.main()
