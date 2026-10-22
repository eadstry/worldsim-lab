# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Create PPT-compatible videos, comparisons, and explicitly labelled composites."""
import argparse,hashlib,json,math,shutil
from pathlib import Path
import cv2,imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageOps

FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

def text(im,label,sub=''):
    im=im.convert('RGB');d=ImageDraw.Draw(im,'RGBA');d.rectangle((0,0,1280,53),fill=(12,23,38,220));d.text((22,8),label,font=ImageFont.truetype(FONT,25),fill='white')
    if sub:d.rectangle((0,682,1280,720),fill=(12,23,38,220));d.text((20,686),sub,font=ImageFont.truetype(FONT,17),fill=(230,238,245))
    return im

def frames(path):
    cap=cv2.VideoCapture(str(path))
    while True:
        ok,f=cap.read()
        if not ok:break
        yield Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB))
    cap.release()

def encode(path,images,fps=10):
    path.parent.mkdir(parents=True,exist_ok=True)
    writer=imageio_ffmpeg.write_frames(str(path),(1280,720),fps=fps,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',macro_block_size=1,output_params=['-crf','20','-preset','fast','-movflags','+faststart','-r','30'],ffmpeg_log_level='error')
    writer.send(None);count=0
    try:
        for im in images:writer.send(np.asarray(ImageOps.pad(im.convert('RGB'),(1280,720),color=(15,24,36)),dtype=np.uint8));count+=1
    finally:writer.close()
    assert count>0
    return count

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);a=p.parse_args()
    entries=json.loads((a.bundle/'catalog.json').read_text());new=[]
    def register(path,title,evidence,scope,source,rec=1):
        item=dict(id=f'N{len(new)+1:03d}',path=str(path.relative_to(a.bundle)),title=title,category=path.parent.name,evidence=evidence,scope=scope,recommend=rec,source=source,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,type='video');new.append(item)
    for name,label in [('rgb-detail-final','近景'),('rgb-wide-final','家居全景'),('rgb-top-final','俯视')]:
        folder=a.run/name;fs=sorted(folder.glob('frame_*.png'));assert len(fs)==198,(name,len(fs))
        dest=a.bundle/'07_new_rgb'/f'{name}_clean.mp4';encode(dest,(Image.open(f) for f in fs))
        register(dest,'RGB 排序 · '+label,'新增物理仿真状态渲染','MuJoCo 简化笛卡尔夹爪；原餐桌包围盒支撑；家居几何用于渲染；脚本按已知颜色规划',[str(folder/'render.json')])
        dest=a.bundle/'07_new_rgb'/f'{name}_explained.mp4'
        labels=['接近','下降','夹紧','抬起','搬运','放下','松开','撤回']
        traj=json.loads((a.run/({'rgb-detail-final':'physics-s7-final','rgb-wide-final':'physics-s19','rgb-top-final':'physics-s31'}[name])/'trajectory.json').read_text())
        def annotated():
            for i,f in enumerate(fs):
                phase=traj[i*3]['phase'];parts=phase.split('_');lab={'approach':'接近','descend':'下降','grasp':'夹紧','lift':'抬起','transfer':'搬运','lower':'放下','release':'松开','retreat':'撤回','initialize':'初始化','settle':'稳定归位'}.get(parts[-1],parts[-1])
                yield text(Image.open(f),f'RGB 颜色排序 / {label} / {lab}','简化夹爪物理仿真 + mini 家居渲染｜已知颜色脚本任务｜非训练策略 / 非 AutoData 扩增结果')
        encode(dest,annotated());register(dest,'RGB 排序步骤讲解 · '+label,'新增物理仿真讲解版','与无字幕版相同轨迹，增加阶段说明',[str(folder/'render.json')])
    # One short, complete red-cube pick/place for the task-introduction slide.
    fs=sorted((a.run/'rgb-detail-final').glob('frame_*.png'))[:66]
    dest=a.bundle/'07_new_rgb/rgb-red-pick-place.mp4';encode(dest,(text(Image.open(f),'方块抓取：接近 → 夹紧 → 抬起 → 放下','简化夹爪物理仿真状态渲染｜完整红方块子任务') for f in fs));register(dest,'红方块抓取与放置 · 短版','新增物理仿真状态渲染','完整首个方块子任务；截取非加速',[str(a.run/'rgb-detail-final/render.json')])
    # Sensor/image augmentations preserve color semantics and share one measured rollout.
    basefs=sorted((a.run/'rgb-detail-final').glob('frame_*.png'))
    styles=[('warm','暖色白平衡'),('cool','冷色白平衡'),('dim','曝光降低'),('bright','曝光提高'),('noise','传感噪声'),('blur','轻度模糊'),('contrast','对比度变化'),('vignette','渐晕变化')]
    for variant,label in styles:
        def transformed():
            rng=np.random.default_rng(20261021)
            yy,xx=np.mgrid[:720,:1280];rad=((xx-640)/900)**2+((yy-360)/600)**2
            for f in basefs:
                im=Image.open(f).convert('RGB');x=np.asarray(im,dtype=np.float32)
                if variant=='warm':x*=np.array([1.08,1.,.86])
                elif variant=='cool':x*=np.array([.87,1.,1.09])
                elif variant=='dim':x*=.62
                elif variant=='bright':x=x*1.18+5
                elif variant=='noise':x+=rng.normal(0,5,x.shape)
                elif variant=='contrast':x=(x-127.5)*1.2+127.5
                elif variant=='vignette':x*=np.clip(1-.4*rad,.5,1)[...,None]
                im=Image.fromarray(np.uint8(np.clip(x,0,255)))
                if variant=='blur':im=im.filter(ImageFilter.GaussianBlur(1.2))
                yield text(im,'图像域增强 / '+label,'同一条轨迹的视频后处理｜未重新运行物理、灯光或相机仿真')
        dest=a.bundle/'08_image_augmentation'/f'rgb_{variant}.mp4';encode(dest,transformed());register(dest,'RGB 任务图像增强 · '+label,'视频后处理','同轨迹像素变换；不能宣称物理参数随机化或泛化性能提升',[str(a.run/'rgb-detail-final/render.json')],2)
    # Alpha foreground is rendered from the native table and task only.
    fgs=sorted((a.run/'rgb-foreground').glob('frame_*.png'));assert len(fgs)==198
    back_sources=[('home','原 mini 家居',a.run/'rgb-wide-final/frame_0000.png'),('other_view','mini 家居另一视角',a.bundle/'posters/M003.jpg'),('studio','纯色演播室',None)]
    for slug,label,src in back_sources:
        bg=Image.open(src).convert('RGBA').resize((1280,720)).filter(ImageFilter.GaussianBlur(7)) if src else Image.new('RGBA',(1280,720),(27,42,64,255))
        def composite():
            for f in fgs:
                fg=Image.open(f).convert('RGBA');yield text(Image.alpha_composite(bg,fg),f'背景替换 / {label}','二维 Alpha 合成｜背景视角、遮挡和照明不构成新的物理仿真验证')
        dest=a.bundle/'09_background_composites'/f'rgb_background_{slug}.mp4';encode(dest,composite());register(dest,'方块排序背景替换 · '+label,'二维背景合成','透明前景包含原生餐桌、任务对象与夹爪；背景独立替换，没有 3DGS',[str(a.run/'rgb-foreground/render.json'),str(src)],2)
    # G1-D renders are optional only when a physical run passed.
    for folder in sorted(a.run.glob('g1d-final-*')):
        if not (folder/'render.json').exists():continue
        meta=json.loads((folder/'render.json').read_text());assert meta['task_success']
        fs=sorted(folder.glob('frame_*.png'));dest=a.bundle/'10_g1d'/f'{folder.name}.mp4'
        encode(dest,(text(Image.open(f),'G1-D + 演示用平行夹爪 / RGB 方块任务','官方 URDF 机身与手臂｜改装夹爪接触仿真｜固定底座、简化碰撞、脚本 IK') for f in fs))
        register(dest,'G1-D 方块抓取 / RGB 排序 · '+folder.name.split('-')[-1],'官方 G1-D + 改装夹爪物理仿真渲染','原生 Dex3 抓取尝试未通过；本视频使用新增平行夹爪，固定底座、理想重力补偿',[str(folder/'render.json')])
    # Compare original randomized videos at the same video time, with source labels.
    originals=[x for x in entries if x['category']=='02_original_domain' and 'overview' in x['title']]
    chosen=[next(x for x in originals if ('· '+n+' ·') in x['title']) for n in ['baseline','lighting','material','camera']]
    caps=[cv2.VideoCapture(str(a.bundle/x['path'])) for x in chosen]
    seconds=min(x['seconds'] for x in chosen)
    def grid():
        for i in range(int(seconds*10)):
            canvas=Image.new('RGB',(1280,720),(15,24,36));dd=ImageDraw.Draw(canvas)
            for k,(cap,item) in enumerate(zip(caps,chosen)):
                cap.set(cv2.CAP_PROP_POS_MSEC,i*100);ok,f=cap.read()
                if not ok:raise ValueError('Source comparison frame missing')
                tile=Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)).resize((640,320));canvas.paste(tile,(k%2*640,42+k//2*330));dd.text((k%2*640+12,46+k//2*330),item['title'].split('·')[1].strip(),font=ImageFont.truetype(FONT,21),fill='black')
            yield text(canvas,'家居抓取 / 历史域随机化对照','baseline / lighting / material / camera｜按视频时间对齐；各组物理状态并非逐帧完全相同')
    dest=a.bundle/'11_comparisons/home_domain_2x2.mp4';encode(dest,grid());register(dest,'家居抓取域随机化四宫格','历史录像重新排版','按视频时间并排，不是严格逐状态因果对照',[x['source'] for x in chosen])
    for c in caps:c.release()
    # Three views use different seeds; label this rather than implying synchronization.
    streams=[iter(frames(a.bundle/'07_new_rgb'/f'{n}_clean.mp4')) for n in ['rgb-detail-final','rgb-wide-final','rgb-top-final']]
    def threeview():
        for i in range(594):
            ims=[next(s) for s in streams];canvas=Image.new('RGB',(1280,720),(15,24,36));canvas.paste(ims[0].resize((880,495)),(0,90));canvas.paste(ims[1].resize((400,225)),(880,95));canvas.paste(ims[2].resize((400,225)),(880,330))
            yield text(canvas,'RGB 排序 / 三种视角选片','三个独立初始布局的物理仿真示例｜用于展示选择，非同一次仿真的同步相机')
    dest=a.bundle/'11_comparisons/rgb_three_views.mp4';encode(dest,threeview(),30);register(dest,'RGB 排序三视角拼版','不同种子任务录像拼版','三个布局对应三个物理任务；不是同步相机',[str(a.run/n/'render.json') for n in ['rgb-detail-final','rgb-wide-final','rgb-top-final']])
    # H.264 excerpts for the original AV1 dataset cameras. Keep complete originals too.
    for item in [x for x in entries if x['category']=='05_original_dataset' and '数据集相机' in x['title']]:
        source=a.bundle/item['path'];cap=cv2.VideoCapture(str(source));fps=cap.get(cv2.CAP_PROP_FPS)
        def excerpt():
            for i in range(min(600,int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))):
                ok,f=cap.read()
                if not ok:break
                im=ImageOps.pad(Image.fromarray(cv2.cvtColor(f,cv2.COLOR_BGR2RGB)),(1280,720),color=(15,24,36))
                yield text(im,item['title'],'原数据集前 20 秒转码｜格式/轨迹展示，不代表通过物理任务验收')
        dest=a.bundle/'12_ppt_h264'/f"{item['id']}_excerpt_h264.mp4";encode(dest,excerpt(),fps);cap.release();register(dest,item['title']+' · PPT H.264 选段','原视频转码选段','保留原画幅比例，并使用 16:9 留边画布展示',[item['source']],2)
    entries+=new
    (a.bundle/'catalog.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2));print(json.dumps(dict(new_videos=len(new),total_entries=len(entries)),ensure_ascii=False))

if __name__=='__main__':main()
