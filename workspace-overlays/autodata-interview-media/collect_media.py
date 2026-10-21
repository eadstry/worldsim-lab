# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Curate local task media, decode originals, and preserve content provenance."""
import argparse, hashlib, json, shutil
from pathlib import Path
import cv2
from PIL import Image


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    entries=[];seen={};failures=[]
    def add(src,group,title,kind,scope,recommend=2):
        if not src.is_file():failures.append(dict(path=str(src),reason='missing'));return
        if src.stat().st_size<1024:failures.append(dict(path=str(src),reason='pointer_or_empty'));return
        sha=digest(src)
        if sha in seen:return
        ident=f'M{len(entries)+1:03d}';dest=Path(group)/(ident+'_'+src.name)
        target=a.output/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        item=dict(id=ident,path=dest.as_posix(),title=title,category=group,evidence=kind,scope=scope,recommend=recommend,source=str(src),sha256=sha,bytes=src.stat().st_size)
        if src.suffix.lower() in ['.mp4','.webm','.gif']:
            cap=cv2.VideoCapture(str(src));fps=cap.get(cv2.CAP_PROP_FPS);total=0;shape=None;poster=None
            while True:
                ok,f=cap.read()
                if not ok:break
                if total==0:shape=[int(f.shape[1]),int(f.shape[0])];poster=f.copy()
                if total==150:poster=f.copy()
                total+=1
            advertised=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
            if not total or (advertised>0 and total!=advertised):
                failures.append(dict(path=str(src),reason=f'decode_incomplete_{total}_of_{advertised}'));target.unlink();return
            item.update(type='video',fps=fps,frames=total,seconds=total/fps,size=shape,decoded_all_frames=True)
            pp=Path('posters')/(ident+'.jpg');(a.output/pp).parent.mkdir(exist_ok=True)
            cv2.imwrite(str(a.output/pp),poster,[cv2.IMWRITE_JPEG_QUALITY,90]);item['poster']=pp.as_posix()
        else:
            with Image.open(src) as im:im.verify()
            item.update(type='image',poster=dest.as_posix())
        seen[sha]=str(src);entries.append(item)
    R=a.root;W=R/'.worktrees'
    for view in ['overview','detail']:
        add(W/'arm-home-scene-20261017/runs/episode-r07'/f'{view}.mp4','01_original_home','Franka 原餐桌抓取 · '+view,'历史物理仿真录像','原记录有抓取/释放稳定性验收；脚本 IK 示范，不是策略推理',1)
    dr=W/'g1-home-domain-20261017/runs/final-review'
    for scenario in ['baseline','lighting','material','camera','visual_only','combined_s1','combined_s2']:
        for view in ['overview','head']:
            src=dr/scenario/f'{view}.mp4'
            if src.exists():add(src,'02_original_domain',f'G1 家居抓取 · {scenario} · {view}','历史仿真域随机化录像','历史任务与各组条件见同目录 summary；G1 为双足型号，与新增 G1-D 区分',1)
    hdr=W/'openarm-hdr-production-20261016/runs/hdr-production/third-person-full-20261017-v2'
    for src in sorted(hdr.glob('*.mp4')):add(src,'03_original_hdr','OpenArm HDR · '+src.stem,'历史 HDR 仿真渲染','原生 HDR 环境/相机录像；不能据视觉变化宣称泛化提升',1)
    for task,run in [('banana-home-grasp-20261017','banana-r02'),('banana-wrist-force-20261017','wrist-force-r02')]:
        for src in sorted((W/task/'runs'/run).glob('*.mp4')):add(src,'04_original_grasp','家居物品抓取 · '+task.split('-2026')[0]+' · '+src.stem,'历史物理仿真录像','单次脚本任务；不是训练策略成功率',2)
    for src in sorted((W/'franka-curobo-comparison-20261017/outputs/franka-curobo-home-comparison/v001').glob('*.mp4')):
        add(src,'04_original_grasp','抓取路径对照 · '+src.stem,'历史对照录像','包含受阻失败对照；不可作为全部成功展示',3)
    for view in ['third_person','left_hand','right_hand']:
        src=R/'runs/openarm-left-joint-space-20261020-v001/openarm-left-joint-lerobot-v3/videos'/('observation.images.'+view)/'chunk-000/file-000.mp4'
        add(src,'05_original_dataset','OpenArm 数据集相机 · '+view,'历史数据集 RGB','LeRobot 原始 AV1 视频流，PPT 优先使用 H.264 选段；格式有效不代表物理任务成功',2)
    for src in [R/'workspace-overlays/dev-state-snapshot-20261013/AutoData/files/logs/openarm_generation_preparation_20261013/openarm-success-replay.mp4',R/'runs/recovered-framework-dev/AutoData/logs/openarm_generation_preparation_20261013/openarm-overview-replay.mp4']:
        add(src,'05_original_dataset','OpenArm 历史回放 · '+src.stem,'历史状态回放','状态回放可展示轨迹；不是新一轮动力学执行',2)
    for sub,title in [('autodata-domain-randomization/v002','OpenArm 初始状态随机化'),('autodata-domain-randomization/v001','OpenArm 随机化分布')]:
        for src in sorted((R/'outputs'/sub).glob('*.png')):
            if sub.endswith('/v001') and src.name!='distribution.png':continue
            add(src,'06_original_figures',title+' · '+src.stem,'历史渲染/统计图','原图与结论范围见源版本；不作新增实验',2)
    for folder in [W/'arm-home-scene-20261017/runs/episode-r07',dr]:
        for src in sorted(folder.glob('*.png')):add(src,'06_original_figures','mini 家居抓取 · '+src.stem,'历史仿真关键帧','与对应录像同一场景来源',1)
    (a.output/'catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2))
    (a.output/'collection.json').write_text(json.dumps(dict(entries=len(entries),videos=sum(x['type']=='video' for x in entries),images=sum(x['type']=='image' for x in entries),excluded=failures),ensure_ascii=False,indent=2))
    print(json.dumps(dict(entries=len(entries),bytes=sum(e['bytes'] for e in entries)),indent=2))

if __name__=='__main__':main()
