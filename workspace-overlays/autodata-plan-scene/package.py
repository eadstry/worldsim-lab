# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Package actual plan/state evidence into a self-contained inline visualization."""
import argparse
import base64
import hashlib
import io
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image

p=argparse.ArgumentParser()
p.add_argument('--run-root', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--widget', type=Path, required=True)
a=p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
labels={'baseline':'默认位置','offset-a':'偏移 A','offset-b':'偏移 B'}
data={'cases':[], 'run_root':str(a.run_root.resolve()), 'source_stable':True}
for name,label in labels.items():
    folder=a.run_root/name
    probe=json.loads((folder/'probe-recovered.json').read_text())
    assert probe['frames'], f'No rendered evidence for {name}'
    assert probe['actual_eef_positions_m'], f'No physical execution for {name}'
    result=json.loads((folder/'episodes.result.json').read_text()) if (folder/'episodes.result.json').exists() else {}
    validation=json.loads((folder/'episodes.validation.json').read_text()) if (folder/'episodes.validation.json').exists() else {}
    stable=json.loads((folder/'source-stability.json').read_text())
    data['source_stable'] &= stable['unchanged']
    c={'case':name,'label':label,'offset_m':probe['offset_m'],'steps':probe['steps'],
       'duration_s':probe['steps']*probe['step_dt_s'],'plan_count':len(probe['plans']),
       'plan_successes':sum(bool(x.get('success')) for x in probe['plans']),
       'planned_length_m':sum(x.get('path_length_m',0) for x in probe['plans']),
       'recorded_success':bool(validation['episodes'][0]['recorded_success']) if validation.get('episodes') else None,
       'terminal_success':validation.get('passed'), 'generation_result':result,'frames':[]}
    indexes=np.unique(np.linspace(0,len(probe['frames'])-1,24).round().astype(int))
    for index in indexes:
        frame=probe['frames'][int(index)].copy()
        buffer=io.BytesIO()
        image=Image.open(folder/frame['file']).convert('RGB')
        image.thumbnail((384,288))
        image.save(buffer,format='WEBP',quality=68)
        frame['image']='data:image/webp;base64,'+base64.b64encode(buffer.getvalue()).decode()
        c['frames'].append(frame)
    data['cases'].append(c)
    target=a.output/name
    target.mkdir()
    for file in ('probe.json','probe-recovered.json','source-sha256.json','source-stability.json','episodes.result.json','episodes.validation.json','task.yaml'):
        if (folder/file).exists():shutil.copy2(folder/file,target/file)
    for i in (0,len(probe['frames'])//2,len(probe['frames'])-1):
        filename=probe['frames'][i]['file'];shutil.copy2(folder/filename,target/filename)
max_time=max(c['duration_s'] for c in data['cases'])
data['timeline']=np.linspace(0,max_time,36).tolist()
fragment=Path(__file__).with_name('viewer.html').read_text().replace('__LIVE_DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
assert len(fragment.encode())<1_000_000, 'Inline payload exceeds visualization limit'
a.widget.write_text(fragment)
(a.output/'visualization-fragment.html').write_text(fragment)
summary={**data,'cases':[{k:v for k,v in c.items() if k!='frames'} for c in data['cases']]}
(a.output/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
manifest={'schema_version':1,'artifact_id':'autodata-plan-scene','version':a.output.name,'created_at':now,'sealed_at':now,
          'sources':[str(a.run_root.resolve())],'files':{str(f.relative_to(a.output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.output.rglob('*')) if f.is_file()},
          'validation':{'real_gpu_scenarios':len(data['cases']),'source_stability':data['source_stable'],'scope':'Real cuRobo planning, AutoData execution and terminal-state validation; one episode per scenario'},'delivery':{'local':{'status':'saved'}}}
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'widget_bytes':len(fragment.encode()),'cases':summary['cases']},ensure_ascii=False))
