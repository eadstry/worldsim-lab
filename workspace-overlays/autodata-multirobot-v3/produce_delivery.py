"""Run bounded parallel HD rendering inside one host queue job, then official v3 export."""
import argparse, concurrent.futures, json, os, subprocess, sys, time
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--scene', type=Path, required=True)
p.add_argument('--lerobot-python', type=Path, required=True)
p.add_argument('--workers', type=int, default=4)
a = p.parse_args()
a.root = a.root.resolve()
scripts = Path(__file__).resolve().parent
if not 1 <= a.workers <= 4:
    raise ValueError('Use 1–4 bounded render processes')
force = a.root / 'so101-force-limited'
old = a.root / 'superseded' / 'so101-unbounded'
if force.exists():
    assert len(list(force.glob('episode-*/verification.json'))) == 12
    for path in force.glob('episode-*/verification.json'):
        assert json.loads(path.read_text())['success']
    old.parent.mkdir(parents=True, exist_ok=True)
    (a.root / 'production' / 'so101').rename(old)
    force.rename(a.root / 'production' / 'so101')
preflight = a.root / 'preflight-input'
preflight.mkdir(exist_ok=True)
reference = old / 'episode-00' if (old / 'episode-00' / 'overview.mp4').exists() else a.root / 'production' / 'so101' / 'episode-00'
if not (reference / 'overview.mp4').exists():
    subprocess.run([sys.executable, str(scripts / 'batch_render.py'), '--source', str(reference.parent), '--scene', str(a.scene), '--start', '0', '--end', '1', '--render-tag', 'render-preflight'], check=True)
if not (preflight / 'episode-00').exists():
    (preflight / 'episode-00').symlink_to(reference, target_is_directory=True)
output = a.root / 'preflight-dataset'
lerobot_env = dict(os.environ)
lerobot_env['LD_LIBRARY_PATH'] = str(a.lerobot_python.parent.parent / 'ffmpeg-libs') + (':' + lerobot_env['LD_LIBRARY_PATH'] if lerobot_env.get('LD_LIBRARY_PATH') else '')
if (output / 'meta' / 'generation.json').exists() and (not (output / 'validation.json').exists()):
    subprocess.run([str(a.lerobot_python), str(scripts / 'export_lerobot.py'), '--output', str(output), '--validate'], check=True, env=lerobot_env)
if not (output / 'validation.json').exists():
    subprocess.run([str(a.lerobot_python), str(scripts / 'export_lerobot.py'), '--source', str(preflight), '--output', str(output), '--robot', 'so101', '--expected-episodes', '1'], check=True, env=lerobot_env)
if not (a.root / 'action-state-replay-final.json').exists():
    subprocess.run([sys.executable, str(scripts / 'audit_replay.py'), '--source', str(a.root / 'production'), '--output', str(a.root / 'action-state-replay-final.json')], check=True)
for robot in ['g1d', 'openarm', 'so101']:
    assert len(list((a.root / 'production' / robot).glob('episode-*'))) == 12
jobs = [(robot, index) for index in range(12) for robot in ['g1d', 'openarm', 'so101']]
completed = []
start = time.time()

def render(job):
    robot, index = job
    log = a.root / f'render-{robot}-{index:02d}.log'
    cmd = [sys.executable, str(scripts / 'batch_render.py'), '--source', str(a.root / 'production' / robot), '--scene', str(a.scene.resolve()), '--start', str(index), '--end', str(index + 1), '--render-tag', 'render-hd-bulk', '--samples', '32']
    with log.open('w') as stream:
        subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, check=True)
    return dict(robot=robot, episode=index)
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
    for future in concurrent.futures.as_completed([pool.submit(render, job) for job in jobs]):
        result = future.result()
        completed.append(result)
        (a.root / 'media-progress.json').write_text(json.dumps(dict(completed=len(completed), total=36, elapsed_s=time.time() - start, episodes=completed), indent=2))
        print('HD_COMPLETE', len(completed), 36, json.dumps(result), flush=True)
for robot in ['g1d', 'openarm', 'so101']:
    output = a.root / 'datasets' / robot
    if not (output / 'validation.json').exists():
        subprocess.run([str(a.lerobot_python), str(scripts / 'export_lerobot.py'), '--source', str(a.root / 'production' / robot), '--output', str(output), '--robot', robot], check=True, env=lerobot_env)
print('ALL_DATASETS_VALIDATED', 36, flush=True)
