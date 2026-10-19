"""Validate the completed new run using the unchanged historical validator."""
from pathlib import Path
import subprocess,json,sys
root=Path(__file__).resolve().parent
run=root/'v2-auto-16-seed101'
state=json.loads((run/'episodes.run.json').read_text())
assert state['status']=='succeeded',state['status']
output=run/'episodes.hdf5';assert output.is_file()
validator=Path('/home/tangyuan/WorldSimReady-Home/AutoData/datasets/efficiency_20261014_201834/v2/launchers/v2/validate_output.py')
with (run/'validation.log').open('w') as f:r=subprocess.run([sys.executable,str(validator),str(output)],stdout=f,stderr=subprocess.STDOUT)
report=json.loads((run/'episodes.validation.json').read_text())
assert len(report['episodes'])==16
print(json.dumps({'validator_returncode':r.returncode,'episodes':len(report['episodes']),'terminal_passes':sum(x['final_state_success'] for x in report['episodes']),'sha256':report['sha256']}))
raise SystemExit(r.returncode)
