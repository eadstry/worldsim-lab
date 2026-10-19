"""Re-run the preserved v2 configuration without modifying upstream or old outputs."""
import json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
prior=Path('/home/tangyuan/WorldSimReady-Home/AutoData/datasets/efficiency_20261014_201834/v2')
python=Path('/home/tangyuan/.codex/worktrees/5b06/WorldSimReady-Home/workspace-overlays/curobo-v2-mvp/.local/env-v2/bin/python3.12')
run=root/'v2-auto-16-seed101';run.mkdir(exist_ok=False)
cmd=json.loads((prior/'r01_v2_wauto/command.json').read_text())['command']
cmd[cmd.index('--output_file')+1]=str(run/'episodes.hdf5')
env=dict(os.environ);cache=root/'cache';cuda=python.parent.parent/'lib/python3.12/site-packages/nvidia/cu13'
env.update(OPENARM_PYTHON=str(python),PYTHONDONTWRITEBYTECODE='1',XDG_CACHE_HOME=str(cache),CUDA_CACHE_PATH=str(cache/'cuda'),TORCH_EXTENSIONS_DIR=str(cache/'torch'),WARP_CACHE_PATH=str(cache/'warp'),CUROBO_CACHE_DIR=str(cache/'curobo'),CUDA_HOME=str(cuda),LD_LIBRARY_PATH=str(cuda/'lib')+':'+str(python.parent.parent/'lib')+':'+env.get('LD_LIBRARY_PATH',''))
record={'command':cmd,'started_unix':time.time(),'purpose':'Complete v2 auto 16-success production and validation; new run, not recovery','timeout_seconds':1800}
(root/'rerun.json').write_text(json.dumps(record,indent=2))
with (run/'launcher.log').open('w') as f:
 try:r=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=1800);record['returncode']=r.returncode
 except subprocess.TimeoutExpired:record['status']='timeout';raise
 finally:record['ended_unix']=time.time();(root/'rerun.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
