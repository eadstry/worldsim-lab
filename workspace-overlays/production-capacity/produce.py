# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Production-only continuation: no image decode, HDF5 readback, hashing or video."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from run import write, read_rows
GIB = 1024**3


def summarize_closed(directory, envs, workers, seed, attempts):
    output = directory / 'dataset.hdf5'
    supervisor = json.loads(output.with_suffix('.run.json').read_text())
    original_cell = json.loads((directory/'cell.json').read_text()) if (directory/'cell.json').exists() else {}
    recovered_monitor_exit = (
        supervisor['status'] == 'interrupted' and supervisor.get('returncode') == 0
        and supervisor.get('exit_signal') is None and supervisor.get('received_signals') == [15]
        and supervisor.get('completion_error') is None
        and original_cell.get('error') == "TypeError: '>' not supported between instances of 'NoneType' and 'int'"
    )
    if supervisor['status'] != 'succeeded' and not recovered_monitor_exit:
        raise ValueError('Supervisor has not successfully closed: ' + str(directory))
    config = supervisor['config']
    if (config['num_envs'] != envs or str(config['export_workers']) != str(workers)
            or config['generation_num_trials'] != attempts or config['final_hold_steps'] != 60):
        raise ValueError('Run settings mismatch')
    import yaml
    descriptor = yaml.safe_load((directory/'task.yaml').read_text())
    policy = descriptor['generation_policy']
    if policy['seed'] != seed or policy['guarantee_success'] or not policy['keep_failed']:
        raise ValueError('Task policy mismatch')
    stats = json.loads(output.with_suffix('.result.json').read_text())
    telemetry = read_rows(output.with_suffix('.telemetry.jsonl'))
    starts = [r for r in telemetry if r['event']=='episode_started']
    finished = [r for r in telemetry if r['event']=='episode_finished']
    if (stats['num_attempts'] != attempts or stats['num_success']+stats['num_failures'] != attempts
            or len(starts)!=attempts or len(finished)!=attempts
            or any(r.get('error') for r in finished)
            or any(r['event']=='episode_cancelled' for r in telemetry)):
        raise ValueError('Attempt accounting mismatch or execution error')
    ready = next(r for r in reversed(telemetry) if r['event']=='output_ready')
    if recovered_monitor_exit:
        if supervisor.get('result') != stats or ready['elapsed_seconds'] < max(r['elapsed_seconds'] for r in finished):
            raise ValueError('Interrupted monitor lacks consistent completed-export evidence')
    seconds = ready['elapsed_seconds']-starts[0]['elapsed_seconds']
    if seconds<=0:
        raise ValueError('Invalid timing interval')
    export = output.with_suffix('.export.json')
    if workers and (not export.exists() or json.loads(export.read_text())['status']!='complete'):
        raise ValueError('Async export has not completed')
    # Only JSON journals and filesystem metadata are read; never open the HDF5.
    files = {p.name:p.stat().st_size for p in (output,output.with_name('dataset_failed.hdf5')) if p.exists()}
    if stats['num_success'] and not output.exists():
        raise ValueError('Expected production output is absent')
    return dict(status='production_complete', source_directory=str(directory), recovered_monitor_exit=recovered_monitor_exit, supervisor_status=supervisor['status'], envs=envs, workers=workers, seed=seed,
        attempts_requested=attempts, stats=stats, final_ready_seconds=seconds,
        terminal_accepted_per_minute=stats['num_success']*60/seconds,
        actual_workers_started=sum(r['event']=='export_worker_started' for r in telemetry),
        output_file_bytes=files, independent_file_validation='not performed in production-only mode',
        image_decode='disabled', dataset_hashes='disabled', file_hashes='disabled', review_video='disabled')


def launch_cell(args, label, envs, workers, seed, attempts):
    import yaml
    from bench32 import available_gib, terminate
    from resources import cgroup_sample
    cell=args.directory/label
    cell.mkdir()
    row=dict(label=label,status='preflight',envs=envs,workers=workers,seed=seed,attempts_requested=attempts)
    write(cell/'cell.json',row)
    def production_only_limits():
        if shutil.disk_usage(args.directory).free<70*GIB:
            raise RuntimeError('Disk reserve below 70 GiB')
        if available_gib()<8:
            raise RuntimeError('Effective memory reserve below 8 GiB')
    production_only_limits()
    competing=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    if competing:
        raise RuntimeError('Other GPU compute processes are active')
    if available_gib()<12+envs*4.5+(16 if workers else 0)+8:
        raise RuntimeError('Insufficient estimated memory headroom')
    task=yaml.safe_load(args.task.read_text())
    task['generation_policy'].update(seed=seed,guarantee_success=False,keep_failed=True,num_trials=attempts)
    descriptor=cell/'task.yaml'
    descriptor.write_text(yaml.safe_dump(task,sort_keys=False))
    output=cell/'dataset.hdf5'
    command=[sys.executable,str(Path(__file__).with_name('launch.py')),'--production-root',str(args.production_root),
        '--gate-root',str(args.gate_root),'--autodata-root',str(args.autodata_root),'--arm','left','--final-hold-steps','60',
        '--input_file',str(args.input),'--output_file',str(output),'--num_envs',str(envs),
        '--generation_num_trials',str(attempts),'--task_descriptor',str(descriptor),'--export-workers',str(workers),
        '--export-queue-memory-gib','16','--log-interval','2']
    row.update(status='running',command=command)
    write(cell/'cell.json',row)
    initial_oom=cgroup_sample(os.getpid()).get('memory.events',{}).get('oom_kill',0)
    process=None
    before=time.monotonic()
    try:
        with (cell/'launcher.log').open('xb') as log:
            process=subprocess.Popen(command,cwd=args.production_root.parents[1],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while process.poll() is None:
                production_only_limits()
                if time.monotonic()-before>2400:
                    raise RuntimeError('Batch timeout')
                resources=output.with_suffix('.resources.jsonl')
                if resources.exists():
                    samples=read_rows(resources)
                    if rss_limit_exceeded(samples,44*GIB):
                        raise RuntimeError('Producer RSS above 44 GiB')
                time.sleep(2)
            if process.returncode:
                raise RuntimeError('Production supervisor failed: '+str(process.returncode))
        if cgroup_sample(os.getpid()).get('memory.events',{}).get('oom_kill',0)>initial_oom:
            raise RuntimeError('OOM event observed')
        row.update(summarize_closed(cell,envs,workers,seed,attempts),launcher_seconds=time.monotonic()-before)
        write(cell/'cell.json',row)
        return row
    except BaseException as exc:
        row.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        write(cell/'cell.json',row)
        raise
    finally:
        if process is not None and process.poll() is None:
            terminate(process)


def rss_limit_exceeded(samples, limit):
    # A final resource sample may arrive after /proc/<pid> disappears. Missing
    # RSS is unavailable, not a numeric zero and not a reason to abort exports.
    rss = samples[-1].get('process_rss_bytes') if samples else None
    return rss is not None and rss > limit


def prior_context(root):
    lineage = []
    visited = set()
    current = root
    while True:
        current = current.resolve()
        if current in visited or len(lineage) >= 8:
            raise ValueError('Invalid recovery lineage')
        visited.add(current)
        lineage.append(current)
        if (current/'environment.json').exists():
            environment = json.loads((current/'environment.json').read_text())
            break
        previous = json.loads((current/'report.json').read_text()).get('prior_run')
        if not previous:
            raise ValueError('Missing original production workspace context')
        current = Path(previous)
    cells = {}
    # Prefer the newest actual batch directory. A directory that exists but is
    # unfinished must be rejected by summarize_closed rather than regenerated.
    for directory in reversed(lineage):
        for manifest in directory.glob('*/dataset.run.json'):
            cells[manifest.parent.name] = manifest.parent
    return environment, cells


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('directory','production-root','gate-root','autodata-root','input','task','reuse-run'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name,value in vars(args).items():setattr(args,name,value.resolve())
    def interrupted(signum,frame):raise KeyboardInterrupt('Controller interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    args.directory.mkdir(parents=True,exist_ok=False)
    sys.path[:0]=[str(args.production_root),str(args.gate_root)]
    report=dict(status='running',budget=74,mode='production_only',rows=[],
        primary_metric='simulator terminal-accepted exports per final-ready minute; not independently file-validated',
        skipped=['image decode','HDF5 readback validation','dataset/file hashes','review video encoding'],
        scope='Small-batch production measurements; independent data quality not established',
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        prior_run=str(args.reuse_run), automatic_retries=False)
    write(args.directory/'report.json',report)
    old_environment, prior_cells=prior_context(args.reuse_run)
    old_workspace=Path(old_environment['worktree'])
    if old_workspace!=args.production_root.parents[1]:
        raise ValueError('Recovery must use the same production/runtime workspace')
    def run(label,envs,workers,seed,attempts):
        previous=prior_cells.get(label)
        if previous is not None:
            row=summarize_closed(previous,envs,workers,seed,attempts)
            row.update(label=label,reused=True,reused_run_commit=old_environment['workspace_commit'])
            old_cell=json.loads((previous/'cell.json').read_text())
            row['original_independent_validation']=old_cell.get('status')=='complete' and (previous/'validation.json').exists()
        else:
            row=launch_cell(args,label,envs,workers,seed,attempts)
        report['rows'].append(row)
        write(args.directory/'report.json',report)
        print(json.dumps({k:row[k] for k in ('label','status','stats','terminal_accepted_per_minute')},ensure_ascii=False),flush=True)
        return row
    try:
        for worker in (0,2):
            row=run(f'pilot-workers{worker}',1,worker,101,1)
            if row['stats']['num_success']!=1:raise RuntimeError('Pilot did not succeed')
        for seed,variants in [(101,(0,2,'auto')),(202,('auto',2,0))]:
            for envs in (1,4):
                for workers in variants:run(f'screen-env{envs}-workers{workers}-seed{seed}',envs,workers,seed,4)
        candidates=[]
        for envs in (1,4):
            base=[r for r in report['rows'] if r['label'].startswith('screen-') and r['envs']==envs and str(r['workers'])=='0']
            baseline=sum(r['stats']['num_success'] for r in base)/sum(r['final_ready_seconds'] for r in base)
            for workers in (2,'auto'):
                rows=[r for r in report['rows'] if r['label'].startswith('screen-') and r['envs']==envs and str(r['workers'])==str(workers)]
                rate=sum(r['stats']['num_success'] for r in rows)/sum(r['final_ready_seconds'] for r in rows)
                if rate>baseline and sum(r['stats']['num_success'] for r in rows)>=sum(r['stats']['num_success'] for r in base):
                    candidates.append((rate,envs,str(workers)))
        if candidates:
            _,envs,worker=max(candidates)
            report['confirmation_selection']=dict(envs=envs,workers=worker,criterion='Exported simulator-accepted rate; independent validation waived by user')
            for index,seed in enumerate((303,404,505)):
                for workers in ((0,worker) if index%2==0 else (worker,0)):
                    run(f'confirm-env{envs}-workers{workers}-seed{seed}',envs,workers,seed,4)
        else:report['confirmation_selection']=None
        report['status']='production_complete'
    except BaseException as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}',remaining_batches='not started')
        raise
    finally:write(args.directory/'report.json',report)
    # HDF5 already uses gzip2; use an uncompressed tar, with no hash pass.
    archive=args.directory.with_name(args.directory.name+'.tar')
    if archive.exists():raise FileExistsError(archive)
    source_bytes=sum(sum(r['output_file_bytes'].values()) for r in report['rows'])
    if 2*source_bytes>600_000_000_000 or shutil.disk_usage(args.directory).free<source_bytes+70*GIB:
        raise RuntimeError('Archive would exceed conservative storage reserve')
    command=['tar','-cf',str(archive),'-C',str(args.directory),'.']
    for row in report['rows']:
        if row.get('reused'):command.extend(['-C',str(Path(row['source_directory']).parent),row['label']])
    subprocess.run(command,check=True)
    write(archive.with_suffix('.receipt.json'),dict(archive=str(archive),bytes=archive.stat().st_size,
        hash='not computed per user instruction',upload_status='pending_destination_and_authenticated_uploader'))


if __name__=='__main__':main()
