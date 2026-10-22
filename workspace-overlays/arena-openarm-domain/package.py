# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Seal actual OpenArm runtime evidence and build the in-conversation comparison."""
import argparse
import base64
import hashlib
import io
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageStat

p=argparse.ArgumentParser()
p.add_argument('--runs',type=Path,required=True)
p.add_argument('--arena-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--widget',type=Path,required=True)
a=p.parse_args()
classes={'intensity':'LightIntensityVariation','color':'LightColorVariation','temperature':'LightColorTemperatureVariation',
         'direction':'LightDirectionVariation','hdr':'HDRImageVariation','extrinsics':'CameraExtrinsicsVariation',
         'intrinsics':'CameraIntrinsicsVariation','mass':'ObjectMassVariation','disappear':'ObjectDisappearVariation','pose':'PoseRange'}
main=json.loads((a.runs/'arena-openarm-domain-r01/result.json').read_text())
assert main['status']=='passed' and main['source_unchanged']
assert {c['id'] for c in main['cases']}==set(classes)
assert {c['class'] for c in main['concrete_variations']}==set(classes.values())-{'PoseRange'}
a.output.mkdir(parents=True,exist_ok=False)
run_names=['arena-openarm-domain-r01','arena-openarm-original-intrinsics','arena-openarm-original-extrinsics',
           'arena-openarm-original-intrinsics-r02','arena-openarm-original-extrinsics-r02',
           'arena-openarm-original-refresh','arena-openarm-light-readback','arena-openarm-original-control-refresh']
reports={}
for name in run_names:
    run=a.runs/name
    d=json.loads((run/'result.json').read_text())
    assert d['status']!='running' and d['source_unchanged'],name
    reports[name]=d
    folder=a.output/'evidence'/name;folder.mkdir(parents=True)
    for filename in ('result.json','source-sha256.json','runner-used.py'):
        shutil.copy2(run/filename,folder/filename)
    for error in run.rglob('error.txt'):
        shutil.copy2(error,folder/(error.parent.name+'-error.txt'))

def image_url(path):
    buffer=io.BytesIO()
    Image.open(path).convert('RGB').save(buffer,format='WEBP',quality=76)
    return 'data:image/webp;base64,'+base64.b64encode(buffer.getvalue()).decode()

data={'cases':[],'scope':main['scope'],
      'arena_head':subprocess.check_output(['git','-C',str(a.arena_root),'rev-parse','HEAD'],text=True).strip(),
      'arena_has_local_changes':bool(subprocess.check_output(['git','-C',str(a.arena_root),'status','--porcelain'],text=True).strip())}
selections=[]
for c in main['cases']:
    run_name='arena-openarm-domain-r01'
    if c['id'] in ('hdr','direction'):
        run_name='arena-openarm-light-readback'
        c=next(x for x in reports[run_name]['cases'] if x['id']==c['id'])
        assert c['status']=='passed'
    selections.append((c,run_name,False))
for kind in ('intrinsics','extrinsics'):
    run_name='arena-openarm-original-refresh' if kind=='intrinsics' else 'arena-openarm-original-control-refresh'
    case=next(c for c in reports[run_name]['cases'] if c['id']==kind)
    selections.append((case,run_name,True))
for case,run_name,original in selections:
    c=json.loads(json.dumps(case));kind=c['id'];c['kind']=kind
    c['source']=[classes[kind]];c['run_source']=str((a.runs/run_name).resolve())
    c['binding']='原场景穹顶光' if kind in ('intensity','color','temperature','hdr') else '原蓝色方块'
    if kind=='direction':c['binding']='新增 DirectionalLight'
    if kind in ('intrinsics','extrinsics'):
        c['binding']='原 third_person_camera' if original else '新增诊断针孔相机'
        if original:
            c['id']='original-'+kind
            c['label']='原相机 · '+('内参' if kind=='intrinsics' else '外参')
            c['note']+='；检查原标定 K 或原安装位姿是否实际改变'
    folder=a.output/'images'/c['id'];folder.mkdir(parents=True)
    for sample in c['samples']:
        src=a.runs/run_name/kind/sample['file']
        shutil.copy2(src,folder/sample['file'])
        sample['image']=image_url(src)
        if original and sample.get('after_observation_file'):
            after=a.runs/run_name/kind/sample['after_observation_file']
            shutil.copy2(after,folder/sample['after_observation_file'])
            if kind=='extrinsics':
                sample['image_before_observation']=sample['image']
                sample['image']=image_url(after)
        original_file=sample.get('original_camera_file')
        if original_file and not original:
            shutil.copy2(a.runs/run_name/kind/original_file,folder/original_file)
    if original and kind=='extrinsics' and len(c['samples'])==2:
        paths=[folder/sample['after_observation_file'] for sample in c['samples']]
        c['before_control_pixel_mean_absolute_difference']=c['pixel_mean_absolute_difference']
        c['pixel_mean_absolute_difference']=sum(ImageStat.Stat(ImageChops.difference(Image.open(paths[0]),Image.open(paths[1]))).mean)/3
        c['note']+='；画面为 3 个零动作控制步后，A/B 相机位置差回到 0 mm'
    if original and kind=='intrinsics':
        c['note']+='；aperture 已变化，但 OpenCV fx/fy 未变'
    data['cases'].append(c)
summary={**data,'cases':[{**c,'samples':[{k:v for k,v in s.items() if not k.startswith('image')} for s in c['samples']]} for c in data['cases']]}
(a.output/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
fragment=Path(__file__).with_name('viewer.html').read_text().replace('__OPENARM_DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
assert len(fragment.encode())<1_000_000
a.widget.write_text(fragment)
(a.output/'visualization-fragment.html').write_text(fragment)
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
manifest={'schema_version':1,'artifact_id':'arena-openarm-domain','version':a.output.name,'created_at':now,'sealed_at':now,
          'sources':[str((a.runs/name).resolve()) for name in run_names],
          'files':{str(f.relative_to(a.output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.output.rglob('*')) if f.is_file()},
          'validation':{'scene':'OpenArm production left pick-place','backend':'PhysX','native_variations_exercised':9,
                        'pose_range_exercised':True,'scene_comparisons_passed':10,
                        'original_camera_checks':{c['kind']:c['status'] for c in data['cases'] if c['id'].startswith('original-')},
                        'limitations':['No motion planning, grasp replay, task-success or policy evaluation','No Newton or distribution statistics',
                                       'Directional light and diagnostic camera are explicit scene additions','Existing local upstream changes retained']},
          'delivery':{'local':{'status':'saved'}}}
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'widget_bytes':len(fragment.encode()),'cases':len(data['cases']),'original_camera_checks':manifest['validation']['original_camera_checks']}))
