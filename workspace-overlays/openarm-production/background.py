# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Batch-scoped local HDR selection, simulator readback and dataset provenance."""
import hashlib
import json
import math
import random
from pathlib import Path


def select_background(config_path, seed):
    """Resolve and validate the entire pool before launching the simulator."""
    if config_path is None:
        return None
    config_path = Path(config_path).resolve()
    raw = config_path.read_bytes()
    cfg = json.loads(raw)
    if set(cfg) - {'candidates', 'intensity', 'color', 'ground_visible'}:
        raise ValueError('Unknown background configuration fields')
    pool = cfg.get('candidates', [])
    if not isinstance(pool, list) or not pool:
        raise ValueError('Background candidates must be a nonempty list')
    resolved, names = [], set()
    for entry in pool:
        if set(entry) - {'name', 'path', 'texture_format'}:
            raise ValueError('Unknown HDR candidate fields')
        name = entry['name']
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Candidate names must be nonempty and unique')
        names.add(name)
        path = (config_path.parent / entry['path']).resolve()
        if not path.is_file() or path.suffix.lower() not in {'.hdr', '.exr'}:
            raise ValueError(f'Missing or unsupported HDR file: {path}')
        fmt = entry.get('texture_format', 'latlong')
        if fmt not in {'automatic', 'latlong', 'mirroredBall', 'angular', 'cubeMapVerticalCross'}:
            raise ValueError(f'Unsupported texture format: {fmt}')
        resolved.append(dict(name=name, path=str(path), texture_format=fmt))
    intensity = float(cfg.get('intensity', 1800.0))
    color = [float(v) for v in cfg.get('color', [1.0, 1.0, 1.0])]
    if not math.isfinite(intensity) or intensity <= 0:
        raise ValueError('Intensity must be finite and positive')
    if len(color) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in color):
        raise ValueError('Color must contain three finite channels in [0, 1]')
    ground_visible = cfg.get('ground_visible', True)
    if not isinstance(ground_visible, bool):
        raise ValueError('ground_visible must be a boolean')
    selected = random.Random(seed).choice(resolved)
    return dict(schema_version=1, scope='one HDR per production process, shared by all environments',
                seed=seed, candidates=resolved, selected=selected, intensity=intensity, color=color,
                ground_visible=ground_visible,
                config_path=str(config_path), config_sha256=hashlib.sha256(raw).hexdigest(),
                texture_sha256=hashlib.sha256(Path(selected['path']).read_bytes()).hexdigest())


def configure_background(env_cfg, record):
    """Configure the dome and ground visibility before spawning."""
    spawn = env_cfg.scene.dome_light.spawn
    spawn.texture_file = record['selected']['path']
    spawn.texture_format = record['selected']['texture_format']
    spawn.visible_in_primary_ray = True
    spawn.intensity = record['intensity']
    spawn.color = tuple(record['color'])
    env_cfg.scene.ground.spawn.visible = record['ground_visible']
    env_cfg.wait_for_textures = True


def verify_background(env, record, output):
    """Fail if the spawned USD light does not carry the selected background."""
    from pxr import Usd, UsdGeom, UsdLux, UsdPhysics
    light = UsdLux.DomeLight(env.sim.stage.GetPrimAtPath(env.cfg.scene.dome_light.prim_path))
    actual = dict(path=str(light.GetTextureFileAttr().Get().path),
                  texture_format=light.GetTextureFormatAttr().Get(),
                  intensity=float(light.GetIntensityAttr().Get()),
                  color=list(light.GetColorAttr().Get()))
    assert actual['path'] == record['selected']['path'], actual
    assert actual['texture_format'] == record['selected']['texture_format'], actual
    assert math.isclose(actual['intensity'], record['intensity'], rel_tol=1e-6), actual
    assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(actual['color'], record['color'])), actual
    ground = env.sim.stage.GetPrimAtPath(env.cfg.scene.ground.prim_path)
    visible = UsdGeom.Imageable(ground).ComputeVisibility() != UsdGeom.Tokens.invisible
    assert visible == record['ground_visible'], 'Ground visibility mismatch'
    collisions = {str(p.GetPath()): bool(UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get())
                  for p in Usd.PrimRange(ground) if p.HasAPI(UsdPhysics.CollisionAPI)}
    assert any(collisions.values()), 'Ground collision must remain enabled'
    actual['ground_visible'] = visible
    actual['ground_collisions'] = collisions
    record['usd_readback'] = actual
    record['status'] = 'configured_and_read_back'
    Path(output).with_suffix('.background.json').write_text(json.dumps(record, indent=2) + '\n')
    print('[OpenArm background] ' + json.dumps(actual), flush=True)


def annotate_dataset(output):
    """After the writer closes, stamp the same batch provenance on each episode."""
    import h5py
    output = Path(output)
    path = output.with_suffix('.background.json')
    record = json.loads(path.read_text())
    texture = Path(record['selected']['path'])
    assert hashlib.sha256(texture.read_bytes()).hexdigest() == record['texture_sha256'], 'HDR changed during run'
    serialized = json.dumps(record, sort_keys=True)
    with h5py.File(output, 'r+') as dataset:
        assert len(dataset['data']), 'No exported episodes'
        dataset['data'].attrs['background'] = serialized
        for episode in dataset['data'].values():
            episode.attrs['background'] = serialized
    record['dataset_annotated'] = True
    path.write_text(json.dumps(record, indent=2) + '\n')
