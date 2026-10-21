# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Draw an explicitly schematic AutoData data-production explanation video."""
import argparse,json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np
from produce_media import encode,FONT
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);a=p.parse_args()
font=lambda n:ImageFont.truetype(FONT,n)
steps=[('01','源示范','少量示范轨迹'),('02','子任务切片','标注对象与阶段'),('03','场景采样','布局 / 外观随机化'),('04','轨迹迁移','对齐 / 插值 / 噪声'),('05','物理执行','成功判据与失败过滤'),('06','数据导出','HDF5 → LeRobot')]
def images():
 for i in range(180):
  im=Image.new('RGB',(1280,720),(245,247,250));d=ImageDraw.Draw(im)
  d.text((50,34),'AutoData：从少量示范到任务数据',font=font(36),fill=(20,34,54));d.text((52,88),'数据生产流程 · 原理示意',font=font(22),fill=(94,108,126))
  active=min(i//25,5)
  for k,(num,title,sub) in enumerate(steps):
   x=55+(k%3)*410;y=175+(k//3)*190;focus=k==active
   d.rounded_rectangle((x,y,x+350,y+145),radius=15,fill=(225,242,248) if focus else 'white',outline=(12,132,166) if focus else (217,225,234),width=3 if focus else 2)
   d.text((x+20,y+15),num,font=font(19),fill=(12,132,166));d.text((x+20,y+47),title,font=font(28),fill=(20,34,54));d.text((x+20,y+96),sub,font=font(20),fill=(90,105,124))
   if k%3<2:d.text((x+365,y+50),'→',font=font(30),fill=(124,141,160))
  d.text((55,575),'域随机化：改变任务执行时的初始状态或渲染条件，并记录采样参数',font=font(23),fill=(33,77,102));d.text((55,626),'本片为原理讲解动画，不代表本次已执行 AutoData 扩增或完成策略训练。',font=font(19),fill=(102,113,127))
  yield im
path=a.bundle/'13_explanation/autodata_flow_schematic.mp4';encode(path,images(),15)
r=json.loads((a.bundle/'catalog.json').read_text());r.append(dict(id='E001',path=str(path.relative_to(a.bundle)),title='AutoData 数据生产流程 · 原理讲解动画',category='13_explanation',type='video',evidence='原理示意动画',scope='基于本地 AutoData 技术说明绘制；没有将示意流程冒充本次运行结果',recommend=1,source=['docs/autodata/AutoData-原理与数据流总览.md'],sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size));(a.bundle/'catalog.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
