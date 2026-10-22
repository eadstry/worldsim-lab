# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Package actual Arena visual checks, preserving first-run failures and rechecks."""
import argparse
import ast
import base64
import hashlib
import io
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

p=argparse.ArgumentParser()
p.add_argument('--first',type=Path,required=True)
p.add_argument('--recheck',type=Path,required=True)
p.add_argument('--arena-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--widget',type=Path,required=True)
a=p.parse_args()
first=json.loads((a.first/'result.json').read_text())
recheck=json.loads((a.recheck/'result.json').read_text())
assert first['source_unchanged'] and recheck['source_unchanged']
first_by_id={c['id']:c for c in first['cases']}
by_id=dict(first_by_id)
for c in recheck['cases']:
    assert c['status']=='passed',c['id']
    by_id[c['id']]=c
assert len(by_id)==10 and all(c['status']=='passed' for c in by_id.values())
classes={'intensity':'LightIntensityVariation','color':'LightColorVariation',
         'temperature':'LightColorTemperatureVariation','direction':'LightDirectionVariation',
         'hdr':'HDRImageVariation','extrinsics':'CameraExtrinsicsVariation','intrinsics':'CameraIntrinsicsVariation',
         'mass':'ObjectMassVariation','disappear':'ObjectDisappearVariation'}
assert set(classes.values())=={x['class'] for x in first['concrete_variations']}
a.output.mkdir(parents=True,exist_ok=False)
data={'cases':[], 'arena_head':subprocess.check_output(['git','-C',str(a.arena_root),'rev-parse','HEAD'],text=True).strip(),
      'arena_has_local_changes':bool(subprocess.check_output(['git','-C',str(a.arena_root),'status','--porcelain'],text=True).strip()),
      'scope':first['scope'],'concrete_variation_count':len(classes)}
for name,c0 in first_by_id.items():
    c=json.loads(json.dumps(by_id[name]))
    run=a.recheck if name in {x['id'] for x in recheck['cases']} else a.first
    c['run_source']=str(run.resolve())
    c['source']=[{'class':classes[name],'path':str(x['source']),'line':x['line']} for x in first['concrete_variations'] if x['class']==classes.get(name)]
    if name=='pose':
        path=a.arena_root/'isaaclab_arena/utils/pose.py'
        node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='PoseRange')
        c['source']=[{'class':'PoseRange','path':str(path),'line':node.lineno}]
    folder=a.output/name;folder.mkdir()
    for s in c['samples']:
        shutil.copy2(run/name/s['file'],folder/s['file'])
        buffer=io.BytesIO();im=Image.open(run/name/s['file']).convert('RGB')
        im.save(buffer,format='WEBP',quality=78)
        s['image']='data:image/webp;base64,'+base64.b64encode(buffer.getvalue()).decode()
    data['cases'].append(c)
for label,run in [('first-run',a.first),('recheck',a.recheck)]:
    folder=a.output/label;folder.mkdir()
    for file in ('result.json','source-sha256.json'):shutil.copy2(run/file,folder/file)
for run in (a.first,a.recheck):
    for file in run.rglob('error.txt'):
        shutil.copy2(file,a.output/f'{run.name}-{file.parent.name}-error.txt')
summary={**data,'cases':[{**c,'samples':[{k:v for k,v in s.items() if k!='image'} for s in c['samples']]} for c in data['cases']]}
(a.output/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
fragment=Path(__file__).with_name('viewer.html').read_text().replace('__ARENA_DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
assert len(fragment.encode())<1_000_000
a.widget.write_text(fragment)
(a.output/'visualization-fragment.html').write_text(fragment)
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
manifest={'schema_version':1,'artifact_id':'arena-domain-visual','version':a.output.name,'created_at':now,'sealed_at':now,
          'sources':[str(a.first.resolve()),str(a.recheck.resolve())],
          'files':{str(f.relative_to(a.output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.output.rglob('*')) if f.is_file()},
          'validation':{'real_gpu_check_count':10,'concrete_arena_variations_covered':9,'first_run_passed':8,'rechecked_passed':2,'backend':'PhysX','not_checked':'Newton, policy performance, planning and statistical distribution'},
          'delivery':{'local':{'status':'saved'}}}
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'widget_bytes':len(fragment.encode()),'passed':len(data['cases']),'arena_head':data['arena_head']}))
