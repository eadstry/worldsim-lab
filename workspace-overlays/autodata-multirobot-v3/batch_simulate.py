"""Generate exactly twelve independently verified episodes per robot; keep failed attempts."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--robot', required=True)
p.add_argument('--model', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--simulation', type=Path, default=Path(__file__).with_name('simulation.py'))
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
(a.out / 'attempts').mkdir(exist_ok=True)
records = json.loads((a.out / 'simulation-progress.json').read_text()).get('attempts', []) if (a.out / 'simulation-progress.json').exists() else []
source_hash = hashlib.sha256(a.simulation.read_bytes()).hexdigest()
tag = source_hash[:8]
bodyid = ['so101', 'openarm', 'g1d'].index(a.robot)
for condition in range(6):
    for task in range(2):
        index = condition * 2 + task
        existing = a.out / f'episode-{index:02d}'
        if existing.exists():
            info = json.loads((existing / 'verification.json').read_text())
            assert info['success'] and info['robot'] == a.robot and (info['condition'] == condition)
            continue
        seed = 3000 + bodyid * 300 + condition * 10 + task
        success = None
        for attempt in range(6):
            trialseed = seed + attempt * 300
            out = a.out / 'attempts' / f'e{index:02d}-{tag}-a{attempt}'
            log = a.out / 'attempts' / f'e{index:02d}-{tag}-a{attempt}.log'
            cmd = [sys.executable, str(a.simulation), '--robot', a.robot, '--source', str(a.model.resolve()), '--out', str(out.resolve()), '--count', str(1 if task == 0 else 3), '--condition', str(condition), '--seed', str(trialseed)]
            with log.open('w') as stream:
                result = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
            info = json.loads((out / 'verification.json').read_text()) if (out / 'verification.json').exists() else {}
            records.append(dict(episode=index, attempt=attempt, seed=trialseed, returncode=result.returncode, success=info.get('success', False)))
            if result.returncode == 0 and info.get('success'):
                (out / 'generation_job.json').write_text(json.dumps(dict(source_sha256=source_hash, source_snapshot=str(a.simulation.resolve()), command=cmd), indent=2))
                dest = a.out / f'episode-{index:02d}'
                out.rename(dest)
                success = dest
                break
        (a.out / 'simulation-progress.json').write_text(json.dumps(dict(robot=a.robot, completed=index + 1 if success else index, attempts=records, source_sha256=hashlib.sha256(a.simulation.read_bytes()).hexdigest()), indent=2))
        if not success:
            raise RuntimeError(f'No successful native {a.robot} episode {index}; failures retained')
        print(json.dumps(dict(robot=a.robot, episode=index, condition=condition, frames=info['frames'], seed=trialseed, checks=info['checks'])), flush=True)
print('COMPLETE', a.robot, 12, flush=True)
