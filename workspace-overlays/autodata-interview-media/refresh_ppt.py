# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Finish connected G1-D tool visuals and aspect-preserving PPT excerpts."""
import argparse,hashlib,json
from pathlib import Path
import cv2
from PIL import Image,ImageOps
from produce_media import encode,text
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
r=json.loads((a.bundle/'catalog.json').read_text());next_id=max(int(x['id'][1:]) for x in r if x['id'].startswith('N'))+1

def update(item,path):
 item.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())

for view in ['wide','detail','side','grasp']:
 folder=a.run/('g1d-polished-'+view);meta=json.loads((folder/'render.json').read_text());assert meta['task_success'];fs=sorted(folder.glob('frame_*.png'));assert len(fs)==len(meta['source_frames'])
 task='单方块抓取' if view=='grasp' else 'RGB 颜色排序';label={'wide':'全景','detail':'近景','side':'侧面','grasp':'全景'}[view]
 old=next(x for x in r if x['path']==f'10_g1d/g1d-final-{view}.mp4');path=a.bundle/old['path']
 encode(path,(text(Image.open(f),f'G1-D 改装平行夹爪 / {task} / {label}','官方 URDF 机身与手臂｜新增夹爪接触仿真｜固定底座、简化碰撞、脚本 IK') for f in fs))
 old.update(title=f'G1-D {task} · {label} · 讲解版',source=[str(folder/'render.json')]);update(old,path)
 clean=a.bundle/'10_g1d'/f'g1d-adapted-gripper-{view}_clean.mp4';encode(clean,(Image.open(f) for f in fs))
 item={**old,'id':f'N{next_id:03d}','path':str(clean.relative_to(a.bundle)),'title':f'G1-D {task} · {label} · 无字幕版','scope':old['scope']+'；无字幕仅省略画面文字，证据范围相同'};next_id+=1;update(item,clean);r.append(item)
folders=[a.run/('g1d-polished-'+v) for v in ['wide','detail','side']];lists=[sorted(f.glob('frame_*.png')) for f in folders]
assert len({len(f) for f in lists})==1

def montage():
 for fs in zip(*lists):
  ims=[Image.open(f).convert('RGB') for f in fs];im=Image.new('RGB',(1280,720),(15,24,36));im.paste(ims[0].resize((880,495)),(0,90));im.paste(ims[1].resize((400,225)),(880,95));im.paste(ims[2].resize((400,225)),(880,330));yield text(im,'G1-D 改装夹爪 / RGB 排序 / 同轨迹三视角','同一条 MuJoCo 物理轨迹的三相机重渲染｜非 AutoData 扩增 / 非原装 Dex3 能力')
path=a.bundle/'11_comparisons/g1d_rgb_three_views.mp4';encode(path,montage())
r.append(dict(id=f'N{next_id:03d}',path=str(path.relative_to(a.bundle)),title='G1-D RGB 排序 · 同轨迹三视角拼版',category='11_comparisons',type='video',evidence='官方 G1-D + 改装夹爪物理仿真渲染',scope='三个视角来自同一物理状态轨迹；固定底座、演示用平行夹爪、简化碰撞、脚本 IK',recommend=1,source=[str(f/'render.json') for f in folders],bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
# Rebuild the dataset-camera excerpts with letterboxing rather than stretching.
for item in [x for x in r if x['category']=='12_ppt_h264']:
 original=next(x for x in r if x['id']==Path(item['path']).name[:4]);cap=cv2.VideoCapture(str(a.bundle/original['path']));fps=cap.get(cv2.CAP_PROP_FPS)
 def images():
  for _ in range(min(600,int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))):
   ok,f=cap.read()
   if not ok:break
   im=ImageOps.pad(Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)),(1280,720),color=(15,24,36));yield text(im,original['title'],'原数据集前 20 秒 H.264 转码｜格式/轨迹展示，不代表物理任务验收通过')
 path=a.bundle/item['path'];encode(path,images(),fps);cap.release();item['scope']='保留原画幅比例，置入 16:9 留边画布；原视频前 20 秒选段';update(item,path)
(a.bundle/'catalog.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(dict(entries=len(r),new_clean_g1d=4,synchronized_g1d=1)))
