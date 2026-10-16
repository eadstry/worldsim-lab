from pathlib import Path
import json,statistics,hashlib,csv
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--v1-root',type=Path,required=True)
parser.add_argument('--v2-log',type=Path,required=True)
args=parser.parse_args()
base=args.v1_root
paths=[('sync',base/'r01_v1_w0/episodes.telemetry.jsonl'),('cap4',base/'r01_v1_w4/episodes.telemetry.jsonl'),('cap8',base/'r01_v1_w8/episodes.telemetry.jsonl'),('auto',base/'r01_v1_wauto/episodes.telemetry.jsonl'),('v2auto',args.v2_log)]
results={};epis=[];wins=[];sources=[]
for mode,p in paths:
 rows=[json.loads(x) for x in p.read_text().splitlines()];sources.append({'mode':mode,'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 done=[r for r in rows if r['event']=='episode_finished'];doneids={r['episode_id'] for r in done};prev={};local=[]
 for r in rows:
  if r['event']=='episode_started':prev[r['episode_id']]=(0,0,r['elapsed_seconds'])
  if r['event']=='execution_progress' and r['episode_id'] in doneids:
   old=prev[r['episode_id']];steps=r['execution_steps']-old[0];dt=r['execution_wait_seconds']-old[1]
   win=dict(mode=mode,episode_id=r['episode_id'],step_end=r['execution_steps'],calls=steps,execute_seconds=dt,ms_per_call=dt/steps*1000,interval_start=old[2],interval_end=r['elapsed_seconds']);wins.append(win);local.append(win);prev[r['episode_id']]=(r['execution_steps'],r['execution_wait_seconds'],r['elapsed_seconds'])
 for r in done:
  st=r['stages_seconds'];count=r['execution_steps'];wait=st['execution_wait'];res=r['duration_seconds']-sum(st.values());assert res>=-0.01
  epis.append(dict(mode=mode,episode_id=r['episode_id'],success=r['success'],calls=count,execute_seconds=wait,ms_per_call=wait/count*1000 if count else None,episode_seconds=r['duration_seconds'],residual_seconds=res,motion_seconds=st.get('motion_plan',0),export_seconds=st.get('export',st.get('export_enqueue',0))))
 data=[e for e in epis if e['mode']==mode];totalcalls=sum(e['calls'] for e in data);totalwait=sum(e['execute_seconds'] for e in data);q=sorted(w['ms_per_call'] for w in local)
 results[mode]=dict(completed=len(data),successful=sum(e['success'] for e in data),calls=totalcalls,mean_calls=totalcalls/len(data),mean_execute_seconds=totalwait/len(data),weighted_ms_per_call=totalwait/totalcalls*1000,mean_episode_seconds=statistics.mean(e['episode_seconds'] for e in data),mean_residual_seconds=statistics.mean(e['residual_seconds'] for e in data),aggregate_execute_share=totalwait/sum(e['episode_seconds'] for e in data),full_100call_windows=len(local),window_median_ms=statistics.median(q),window_p95_ms=q[int((len(q)-1)*.95)],window_max_ms=max(q))
 matched={e['episode_id']:e for e in data}
 if mode=='sync':baseline=matched
 else:
  shared=set(baseline)&set(matched);results[mode]['same_id_same_calls']=sum(baseline[k]['calls']==matched[k]['calls'] for k in shared);results[mode]['shared_ids']=len(shared)
print(json.dumps(results,indent=2))
(Path(__file__).resolve().parent/'execution-analysis.json').write_text(json.dumps({'summary':results,'episodes':epis,'windows':wins,'sources':sources},indent=2))

for key, records in [('episodes', epis), ('windows', wins)]:
    with (Path(__file__).resolve().parent / f'execution-{key}.csv').open('w') as output:
        writer=csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
