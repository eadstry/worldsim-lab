# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Decode delivered videos, build local selection galleries, and package assets."""
import argparse,collections,hashlib,html,json,zipfile
from pathlib import Path
import cv2
from PIL import Image,ImageDraw,ImageFont
from produce_media import FONT


def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def gallery(entries,title):
 cards=[]
 for e in entries:
  link=html.escape(e['path'],quote=True);poster=html.escape(e.get('poster',e['path']),quote=True)
  media=f'<video controls preload="none" poster="{poster}" src="{link}"></video>' if e['type']=='video' else f'<a href="{link}"><img loading="lazy" src="{poster}"></a>'
  cards.append(f'<article data-kind="{e["type"]}" data-category="{html.escape(e["category"])}" data-search="{html.escape(e["title"]+e["evidence"])}"><div class="media">{media}</div><div class="body"><span class="id">{e["id"]}</span><h2>{html.escape(e["title"])}</h2><b>{html.escape(e["evidence"])}</b><p>{html.escape(e["scope"])}</p><a href="{link}" download>下载 / 查看原文件</a></div></article>')
 cats=sorted({e['category'] for e in entries})
 return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'''</title><style>*{box-sizing:border-box}body{margin:0;background:#f2f5f8;color:#183047;font:15px system-ui,sans-serif}header{padding:35px 5%;background:#142b42;color:white}h1{margin:0 0 12px;font-size:30px}header p{max-width:1100px;line-height:1.7;color:#cbd8e5}nav{position:sticky;top:0;background:white;padding:15px 5%;display:flex;gap:12px;flex-wrap:wrap;z-index:2;box-shadow:0 2px 7px #0001}input,select{font:inherit;padding:10px;border:1px solid #bbcbd8;border-radius:7px}input{min-width:280px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:24px;padding:25px 5%}article{background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px #16304a12}.media{height:235px;background:#0c1824}video,img{width:100%;height:100%;object-fit:contain}.body{padding:18px}.id{font-size:12px;color:#748ba0}h2{font-size:19px;line-height:1.4;margin:7px 0 12px}b{color:#087b99;font-size:13px}p{line-height:1.6;color:#596d7f}a{color:#066c8c}article[hidden]{display:none}</style><header><h1>'''+html.escape(title)+f'</h1><p>{len(entries)} 项素材 · 仅限抓取物品与 RGB 排序。新增片段为 1280×720、H.264、30 FPS。先看编号 N 的新增素材及 E001 流程动画，再按需选择历史录像。G1-D 新视频使用官方机身与手臂及演示用平行夹爪；原生 Dex3 未通过本次抓取验收。二维背景合成和图像增强均有单独标签，未使用 3DGS。</p><p>打开本地 HTML 即可选片，无需联网或上传。编号 M 的数据集原视频可能为 AV1；PPT 可优先使用 12_ppt_h264 中的转码选段。不同视角可能来自不同布局，请阅读素材说明。</p></header><nav><input id="q" placeholder="搜索：G1-D / 灯光 / 背景 / 近景"><select id="kind"><option value="">全部类型</option><option value="video">视频</option><option value="image">图片</option></select><select id="cat"><option value="">全部分类</option>'+''.join(f'<option>{html.escape(c)}</option>' for c in cats)+'''</select><span id="count"></span></nav><main>'''+''.join(cards)+'''</main><script>const q=document.querySelector('#q'),kind=document.querySelector('#kind'),cat=document.querySelector('#cat'),cards=[...document.querySelectorAll('article')];function filter(){let n=0;for(const c of cards){c.hidden=!!((kind.value&&c.dataset.kind!==kind.value)||(cat.value&&c.dataset.category!==cat.value)||(q.value&&!c.dataset.search.toLowerCase().includes(q.value.toLowerCase())));if(!c.hidden)n++;}document.querySelector('#count').textContent=n+' 项';}for(const x of [q,kind,cat])x.addEventListener('input',filter);filter();</script></html>'''


def main():
 p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 entries=json.loads((a.bundle/'catalog.json').read_text());checks=[]
 for e in entries:
  file=a.bundle/e['path'];assert sha(file)==e['sha256']
  if e['type']=='video':
   cap=cv2.VideoCapture(str(file));fps=cap.get(cv2.CAP_PROP_FPS);reported=round(cap.get(cv2.CAP_PROP_FRAME_COUNT));total=0;poster=None;size=None
   while True:
    ok,f=cap.read()
    if not ok:break
    if total==0 or total==min(reported//3,180):poster=f.copy();size=[f.shape[1],f.shape[0]]
    total+=1
   codec=int(cap.get(cv2.CAP_PROP_FOURCC));codec=''.join(chr((codec>>8*i)&255) for i in range(4));cap.release()
   assert total==reported and total>0,(file,total,reported)
   if e['id'][0] in ['N','E']:assert size==[1280,720] and abs(fps-30)<.01 and codec=='h264',(file,size,fps,codec)
   pp=Path('posters')/(e['id']+'.jpg');(a.bundle/pp).parent.mkdir(exist_ok=True);im=Image.fromarray(cv2.cvtColor(poster,cv2.COLOR_BGR2RGB));im.thumbnail((640,360));im.save(a.bundle/pp,quality=88)
   e.update(poster=pp.as_posix(),frames=total,fps=fps,seconds=total/fps,size=size,codec=codec,decoded_all_frames=True);checks.append(dict(path=e['path'],frames=total,fps=fps,codec=codec,decoded_all_frames=True))
  else:
   with Image.open(file) as im:im.verify()
 # Prefer new G1-D and new RGB physical videos when opening the gallery.
 entries.sort(key=lambda e:(0 if e['category']=='10_g1d' else (1 if e['category']=='07_new_rgb' else 2),e['recommend'],e['id']))
 (a.bundle/'catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2));(a.bundle/'index.html').write_text(gallery(entries,'AutoData 面试展示素材库 · 2026-10-21'))
 json.dump(checks,open(a.output/'video-validation.json','w'),ensure_ascii=False,indent=2)
 # Contact sheets preserve IDs and labels for quick PowerPoint selection.
 contacts=[]
 for group,items in [('new-videos',[e for e in entries if e['id'][0] in ['N','E']]),('original-videos',[e for e in entries if e['type']=='video' and e['id'].startswith('M')]),('figures',[e for e in entries if e['type']=='image'])]:
  for page in range(0,len(items),16):
   subset=items[page:page+16];canvas=Image.new('RGB',(1600,4*285),(242,245,248));d=ImageDraw.Draw(canvas)
   for k,e in enumerate(subset):
    im=Image.open(a.bundle/e['poster']).convert('RGB');im.thumbnail((392,220));x=k%4*400;y=k//4*285;canvas.paste(im,(x,y));d.text((x+6,y+224),e['id']+' '+e['title'][:20],font=ImageFont.truetype(FONT,17),fill=(20,40,60));d.text((x+6,y+250),e['evidence'][:22],font=ImageFont.truetype(FONT,14),fill=(70,94,113))
   name=f'{group}-{page//16+1:02d}.jpg';canvas.save(a.output/name,quality=90);contacts.append(name)
 # Each media ZIP contains a self-contained, filtered gallery and provenance.
 archives=[]
 for name,subset in [('01-existing-media.zip',[e for e in entries if e['id'].startswith('M')]),('02-new-ppt-media.zip',[e for e in entries if not e['id'].startswith('M')])]:
  archive=a.output/name
  with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
   paths={e['path'] for e in subset}|{e['poster'] for e in subset}
   for rel in sorted(paths):z.write(a.bundle/rel,rel)
   z.writestr('index.html',gallery(subset,'AutoData 面试展示素材 · '+('现有素材' if name.startswith('01') else '新增素材')));z.writestr('catalog.json',json.dumps(subset,ensure_ascii=False,indent=2))
   z.writestr('NOTICE.txt','mini 场景：Yootta/World-SimReady-Home-mini，CC-BY-NC-SA-4.0。仅分发渲染和既有媒体，不包含原始场景。G1-D 模型：Unitree Robotics，BSD-3-Clause。原模型与作者无本次任务能力背书关系。每项证据范围见 catalog.json。\n')
  archives.append(dict(path=name,bytes=archive.stat().st_size,sha256=sha(archive),entries=len(subset)))
 modelzip=a.output/'03-official-g1d-model.zip'
 with zipfile.ZipFile(modelzip,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
  for f in sorted(a.model.rglob('*')):
   if f.is_file():z.write(f,str(Path('g1d-official')/f.relative_to(a.model)))
 archives.append(dict(path=modelzip.name,bytes=modelzip.stat().st_size,sha256=sha(modelzip),scope='Unmodified official URDF, referenced meshes, BSD license and pinned download manifest; no local task adaptation'))
 summary=dict(total=len(entries),videos=sum(e['type']=='video' for e in entries),images=sum(e['type']=='image' for e in entries),new_videos=sum(e['id'][0] in ['N','E'] for e in entries),categories=dict(collections.Counter(e['category'] for e in entries)),archives=archives,contact_sheets=contacts,all_delivered_videos_decoded=True)
 (a.output/'selection-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(a.output/'catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
