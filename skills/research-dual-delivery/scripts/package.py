#!/usr/bin/env python3
"""Initialize, seal and verify portable research packages using stdlib only."""
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

VALID={'pending','uploaded','verified','blocked_destination','blocked_auth','blocked_capability','failed'}
def now(): return datetime.now(timezone.utc).isoformat()
def files(root):
    result={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('Symlinks are not portable: '+str(p))
        if p.is_file() and p.name!='manifest.json':
            result[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('action',choices=['init','seal','verify'])
    ap.add_argument('path',type=Path)
    ap.add_argument('--artifact-id')
    ap.add_argument('--version')
    a=ap.parse_args(); root=a.path; manifest=root/'manifest.json'
    if a.action=='init':
        if not a.artifact_id or not a.version or not re.fullmatch(r'[a-z0-9][a-z0-9-]*',a.artifact_id) or not re.fullmatch(r'v\d{3,}',a.version):
            raise ValueError('Use an ASCII artifact ID and version such as v001.')
        if root.exists() and any(root.iterdir()): raise ValueError('Refusing nonempty output directory.')
        root.mkdir(parents=True,exist_ok=True)
        (root/'report.md').write_text('# '+a.artifact_id+'\n\n请填写结论、证据与未解决问题。\n')
        (root/'CHANGELOG.md').write_text('# '+a.version+'\n\n请填写本次修改。\n')
        d={'schema_version':1,'artifact_id':a.artifact_id,'version':a.version,'created_at':now(),'material_cutoff':None,'sources':[],'limitations':[],'sealed_at':None,'files':{},'delivery':{side:{'status':'pending','target':None,'receipt':None,'files':[],'updated_at':None,'error':None} for side in ['feishu','gpt']}}
        manifest.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
        print('initialized='+str(root)); return
    d=json.loads(manifest.read_text())
    for side in ['feishu','gpt']:
        record=d['delivery'][side]
        if record['status'] not in VALID: raise ValueError('Invalid delivery status: '+side)
        if record['status'] in ['uploaded','verified'] and (not record.get('receipt') or not record.get('target') or not record.get('files') or not record.get('updated_at')):
            raise ValueError('Delivery requires target, receipt, files and timestamp: '+side)
    current=files(root)
    if a.action=='seal':
        if d.get('sealed_at'):
            if current!=d['files']: raise ValueError('Sealed content changed; create a new version.')
            print('already_sealed='+str(root)); return
        for required in ['report.md','CHANGELOG.md']:
            if required not in current: raise ValueError('Missing '+required)
            if '请填写' in (root/required).read_text(): raise ValueError('Unfinished template: '+required)
        if not d.get('material_cutoff') or not d.get('sources'): raise ValueError('Record material_cutoff and sources before sealing.')
        d['files']=current; d['sealed_at']=now()
        manifest.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
        print('sealed='+str(root)); return
    if not d.get('sealed_at'): raise ValueError('Package has not been sealed.')
    if current!=d['files']: raise ValueError('Content hash mismatch or unexpected/missing files.')
    print('verified='+str(root)+' files='+str(len(current)))

if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,OSError) as e: raise SystemExit(str(e))
