# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Seal local media artifacts, source references, and exact validation evidence."""
import argparse,datetime,hashlib,html,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

s=json.loads((a.output/'selection-summary.json').read_text());assert s['total']==135 and s['videos']==67 and s['images']==68,s
runs=['physics-s7-final','physics-s19','physics-s31','g1d-parallel-r2','g1d-sort-r2']
records={}
for name in runs:
 r=a.run/name;checks=json.loads((r/'independent-verification.json').read_text());assert checks['passed'];records[name]=dict(generator=json.loads((r/'verification.json').read_text()),recheck=checks)
queues={}
for i in [165,166,167,191,197,180,181,182,185,201,202,203,204,205,206,207,208,209]:
 q=json.loads(subprocess.check_output(['python3','scripts/task-queue.py','show',str(i)],text=True));assert q['status']=='succeeded',(i,q['status']);queues[str(i)]=q
failed=[]
for name in ['g1d-native-pilot','g1d-native-r2','g1d-native-r3','g1d-native-r4','g1d-native-r5','g1d-parallel-pilot','g1d-sort-final']:
 r=a.run/name/'verification.json'
 if r.exists():
  v=json.loads(r.read_text());failed.append(dict(run=name,success=v['success'],checks=v['checks'],scope='Diagnostic only; excluded from successful task video selection'))
evidence=dict(scene=dict(repository='Yootta/World-SimReady-Home-mini',revision='f2c633749e7fdf3f981dfd1dd83fc253786713ac',scene='scene000430',usdz_sha256='d38ebd9e8312c46125bee1412c3a45933c245b890ea081c307fcfc4e37814ee6',license='CC-BY-NC-SA-4.0',physics='Native dining-table measured AABB support only; house render-only',gaussian_scene_used=False),official_g1d=json.loads((a.run/'g1d-official/download-manifest.json').read_text()),successful_tasks=records,failed_tasks=failed,successful_queue_records=queues,selection_exclusions=json.loads((a.run/'bundle-v2/selection-exclusions.json').read_text()),scope='MuJoCo CPU rigid-body simulation + Blender rendering + local media QA. No AutoData augmentation, policy inference, training, whole-house collision or sim-to-real validation. G1-D successes require a custom parallel-gripper adaptation; native Dex3 attempts failed.')
(a.output/'simulation-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
base=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();source=Path('workspace-overlays/autodata-interview-media')
code=dict(overlay=source.as_posix(),base_commit=base,source_branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),entrypoints=['physical_task.py','g1d_task.py','render_task.py','render_g1d.py','produce_media.py','refresh_ppt.py','build_gallery.py'],files_sha256={f.name:sha(f) for f in sorted(source.glob('*.py'))},note='Implementation lives only in the root overlay; base_commit predates this overlay. Content hashes identify the implementation. The task commit is reported separately after review; no duplicated code directory is stored in outputs.')
(a.output/'code-ref.json').write_text(json.dumps(code,ensure_ascii=False,indent=2))
links=''.join(f'<li><a href="{x["path"]}">{html.escape(x["path"])}</a> · {x["bytes"]/1024/1024:.1f} MiB</li>' for x in s['archives'])
pictures=''.join(f'<a href="{x}"><img src="{x}" alt="选片缩略图"></a>' for x in s['contact_sheets'])
page=f'''<!doctype html><meta charset="utf-8"><title>AutoData 面试展示素材</title><style>body{{font:17px system-ui;max-width:1200px;margin:40px auto;padding:0 22px;color:#183047;line-height:1.7}}img{{max-width:100%;margin:16px 0}}a{{color:#087b99}}</style><h1>AutoData 面试展示素材 · 2026-10-21</h1><p>{s['total']} 项：{s['videos']} 段视频、{s['images']} 张图片；新增 {s['new_videos']} 段视频。任务限定抓取物品与 RGB 排序。</p><p><a href="../../../runs/interview-media/bundle-v2/index.html">打开完整本机选片预览</a> · <a href="../../../docs/autodata-interview-media-20261021.md">来源、验证与 PPT 选片说明</a></p><p>下载 ZIP 后解压，打开其中的 index.html 可离线选片。原始模型包保持官方文件字节不变。</p><ul>{links}</ul><p>G1-D 成功演示使用官方机身与手臂和新增平行夹爪。原装 Dex3 未通过本次抓取验收。二维背景替换与图像增强在素材库中单独标记；没有使用 3DGS，也没有将本次独立 MuJoCo 演示作为 AutoData 扩增结果。</p><p><a href="catalog.json">逐项来源清单</a> · <a href="simulation-evidence.json">物理与来源证据</a> · <a href="video-validation.json">完整视频解码检查</a></p>{pictures}'''
(a.output/'index.html').write_text(page)
created=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
files={str(f.relative_to(a.output)):sha(f) for f in sorted(a.output.rglob('*')) if f.is_file() and f.name!='manifest.json'}
manifest=dict(schema_version=1,artifact_id='autodata-interview-media',version='v001',created_at=created,sealed_at=created,files=files,validation=dict(all_videos_fully_decoded=True,new_video_codec='H.264 / yuv420p / 30 FPS; renders sampled at 10 unique frames/s',physical_state_rechecks=5,scope=evidence['scope']),delivery=dict(local=dict(status='saved'),publication='No site, Feishu or ChatGPT upload; task branch Git synchronization follows workspace policy'))
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
statusp=Path('config/outputs-status.json');status=json.loads(statusp.read_text());status['artifacts']['autodata-interview-media']=dict(title='AutoData 面试展示素材与 G1-D RGB 任务',status='current',summary=f"{s['videos']} 视频、{s['images']} 图片；新增 {s['new_videos']} 视频；mini 家居抓取与 RGB 排序、域随机化、图像增强及背景合成；G1-D 使用改装平行夹爪",delivery='本地媒体 ZIP 与官方模型 ZIP；未发布站点或上传研究平台')
statusp.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(files=len(files),total=s['total'],archives=s['archives']),ensure_ascii=False,indent=2))
