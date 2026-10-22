import json, tempfile, unittest, zipfile
from pathlib import Path
from seal_delivery import digest, zip_bundle, portable_model
import mujoco, numpy as np

class BundleTests(unittest.TestCase):

    def test_implicit_mesh_name_survives_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'meshes').mkdir()
            (root / 'meshes' / 'shape.obj').write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n')
            source = root / 'source.xml'
            source.write_text('<mujoco><compiler meshdir="meshes"/><asset><mesh file="shape.obj"/></asset><worldbody><geom type="mesh" mesh="shape"/></worldbody></mujoco>')
            portable_model(source, root / 'portable')
            original = mujoco.MjModel.from_xml_path(str(source))
            relocated = mujoco.MjModel.from_xml_path(str(root / 'portable' / 'model.xml'))
            np.testing.assert_array_equal(original.mesh_vert, relocated.mesh_vert)
            self.assertEqual(original.ngeom, relocated.ngeom)

    def test_per_robot_scope_hashes_and_gallery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'bundle'
            stage.mkdir()
            for robot in ['g1d', 'openarm']:
                p = stage / 'datasets' / robot / 'validation.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps(dict(episodes=12, frames=100 if robot == 'g1d' else 200)))
            html = stage / 'docs' / 'gallery.html'
            html.parent.mkdir()
            html.write_text('<article class="card" data-robot="g1d">G</article><article class="card" data-robot="openarm">O</article>36 条演示')
            files = {str(p.relative_to(stage)): dict(bytes=p.stat().st_size, sha256=digest(p)) for p in stage.rglob('*') if p.is_file()}
            (stage / 'manifest.json').write_text(json.dumps(dict(episodes=36, frames=300, files=files)))
            output = root / 'g1d.zip'
            zip_bundle(stage, output, 'g1d')
            with zipfile.ZipFile(output) as archive:
                meta = json.loads(archive.read('manifest.json'))
                self.assertEqual(meta['episodes'], 12)
                self.assertEqual(meta['frames'], 100)
                self.assertNotIn('datasets/openarm/validation.json', archive.namelist())
                self.assertNotIn('>O</article>', archive.read('docs/gallery.html').decode())
                self.assertIsNone(archive.testzip())
            with self.assertRaises(FileExistsError):
                zip_bundle(stage, output, 'g1d')
if __name__ == '__main__':
    unittest.main()
