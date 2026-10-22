# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Exclude superseded unsynchronized renders and export useful task keyframes."""
import argparse,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();r=json.loads((a.bundle/'catalog.json').read_text());excluded=[];keep=[]
for e in r:
 source=e.get('source','')
 if isinstance(source,str) and '/autodata-domain-randomization/v001/' in source and Path(source).name!='distribution.png':
  excluded.append(dict(id=e['id'],source=source,reason='v001 reset images were not synchronized; superseded by v002; source report explicitly invalidates visual interpretation'))
  (a.bundle/e['path']).unlink()
 else:keep.append(e)
r=keep;idx=1
for folder,label,selected in [(a.run/'g1d-polished-wide','G1-D 排序 · 全景',[0,33,46,60,99,296]),(a.run/'g1d-polished-detail','G1-D 排序 · 近景',[0,33,46,60,99,296]),(a.run/'g1d-polished-side','G1-D 排序 · 侧面',[0,33,46,60,99,296]),(a.run/'rgb-detail-final','简化夹爪排序 · 近景',[0,25,32,45,65,197]),(a.run/'rgb-wide-final','简化夹爪排序 · 全景',[0,25,32,45,65,197]),(a.run/'rgb-top-final','简化夹爪排序 · 俯视',[0,25,32,45,65,197])]:
 meta=json.loads((folder/'render.json').read_text());files=sorted(folder.glob('frame_*.png'));phases=['初始布局','夹紧','抬起','搬运','首块归位','RGB 排序完成']
 for selected_index,phase in zip(selected,phases):
  src=files[selected_index];rel=Path('14_new_keyframes')/f'K{idx:03d}_{folder.name}_{selected_index:03d}.png';path=a.bundle/rel;path.parent.mkdir(exist_ok=True);shutil.copy2(src,path)
  r.append(dict(id=f'K{idx:03d}',path=rel.as_posix(),title=label+' · '+phase,category='14_new_keyframes',type='image',evidence='新增物理状态渲染关键帧',scope=('官方 G1-D 机身与手臂 + 演示用平行夹爪；固定底座、简化碰撞' if 'g1d' in folder.name else '简化笛卡尔夹爪；餐桌包围盒支撑；家居几何只作渲染')+'；已知颜色脚本任务，无策略推理',recommend=1,source=[str(src),str(folder/'render.json')],sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,poster=rel.as_posix(),source_frame=meta['source_frames'][selected_index]));idx+=1
(a.bundle/'catalog.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(a.bundle/'selection-exclusions.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2));print(json.dumps(dict(entries=len(r),excluded=len(excluded),new_images=idx-1)))
