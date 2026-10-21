"""Render native pre-action poses, encode HD previews, then remove only verified temporary PNGs."""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path
import cv2, imageio_ffmpeg, numpy as np
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--scene', type=Path, required=True)
p.add_argument('--blender', type=Path, default=Path('/opt/blender/blender'))
p.add_argument('--start', type=int, default=0)
p.add_argument('--end', type=int, default=12)
p.add_argument('--samples', type=int, default=32)
p.add_argument('--engine', default='BLENDER_EEVEE')
p.add_argument('--render-tag', default='render-hd-v1')
a = p.parse_args()
scripts = Path(__file__).parent
for index in range(a.start, a.end):
    episode = a.source / f'episode-{index:02d}'
    info = json.loads((episode / 'verification.json').read_text())
    assert info['success']
    out = episode / a.render_tag
    video = episode / 'overview.mp4'
    if video.exists():
        manifest = json.loads((episode / 'media-verification.json').read_text())
        assert manifest['sha256'] == hashlib.sha256(video.read_bytes()).hexdigest()
        continue
    subprocess.run([sys.executable, str(scripts / 'export_render_assets.py'), str(episode)], check=True)
    with (episode / (a.render_tag + '.log')).open('w') as log:
        result = subprocess.run([str(a.blender), '-b', str(a.scene), '--python', str(scripts / 'render_episode.py'), '--', '--episode', str(episode), '--out', str(out), '--samples', str(a.samples), '--condition', str(info['condition']), '--engine', a.engine], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode or not (out / 'render.json').exists():
        raise RuntimeError(f'Render failed: {episode}; see log')
    images = sorted(out.glob('frame_*.png'))
    assert len(images) == info['frames']
    partial = episode / 'overview.partial.mp4'
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-framerate', '30', '-start_number', '0', '-i', str(out / 'frame_%04d.png'), '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-g', '15', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', str(partial)]
    subprocess.run(cmd, check=True)
    cap = cv2.VideoCapture(str(partial))
    assert cap.get(cv2.CAP_PROP_FRAME_WIDTH) == 1920 and cap.get(cv2.CAP_PROP_FRAME_HEIGHT) == 1080 and (abs(cap.get(cv2.CAP_PROP_FPS) - 30) < 0.001)
    decoded = 0
    while cap.read()[0]:
        decoded += 1
    cap.release()
    assert decoded == info['frames']
    trajectory = np.load(episode / 'trajectory.npz')
    firstcolor = info['checks'][0]['color']
    lift = np.flatnonzero(trajectory['phases'] == firstcolor + '_lift')
    posters = {'initial': 0, 'grasp': int(lift[-1]), 'final': len(images) - 1}
    for name, frame in posters.items():
        shutil.copy2(images[frame], episode / f'poster-{name}.png')
    partial.rename(video)
    manifest = dict(width=1920, height=1080, fps=30, frames=decoded, sha256=hashlib.sha256(video.read_bytes()).hexdigest(), source_states_sha256=hashlib.sha256((episode / 'trajectory.npz').read_bytes()).hexdigest(), render_source_sha256=hashlib.sha256((scripts / 'render_episode.py').read_bytes()).hexdigest(), render=json.loads((out / 'render.json').read_text()), encoding=dict(codec='H.264', crf=16, gop=15, pixel_format='yuv420p'), posters=posters)
    (episode / 'media-verification.json').write_text(json.dumps(manifest, indent=2))
    for path in images:
        path.unlink()
    print('RENDERED', info['robot'], index, decoded, video.stat().st_size, flush=True)
