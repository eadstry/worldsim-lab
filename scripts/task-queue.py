#!/usr/bin/env python3
"""Host-local FIFO for foreground validation commands (Linux, Python stdlib)."""

import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import shlex
import signal
import sqlite3
import subprocess
import sys
import time


def default_directory():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    return Path(os.environ.get('WORLDSIM_TASK_QUEUE_DIR', state / 'worldsimready/task-queue'))


def connect(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise ValueError('Queue directory must belong to this user with mode 0700')
    db = sqlite3.connect(directory / 'queue.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        cwd TEXT NOT NULL, command TEXT NOT NULL, environment TEXT NOT NULL,
        revision TEXT, dirty INTEGER, timeout REAL,
        status TEXT NOT NULL DEFAULT 'queued', submitted REAL NOT NULL,
        started REAL, finished REAL, pid INTEGER, returncode INTEGER, error TEXT
    )''')
    db.commit()
    return db


def git_metadata(cwd):
    def git(*args):
        return subprocess.run(['git', '-C', str(cwd), *args], capture_output=True,
                              text=True, timeout=10)
    try:
        revision = git('rev-parse', 'HEAD')
        status = git('status', '--porcelain', '--untracked-files=normal')
        return (revision.stdout.strip() if revision.returncode == 0 else None,
                int(bool(status.stdout)) if status.returncode == 0 else None)
    except (OSError, subprocess.TimeoutExpired):
        return None, None


def enqueue(db, args):
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise ValueError('Supply a command after --')
    cwd = Path(args.cwd).expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError('Task cwd must be a directory')
    revision, dirty = git_metadata(cwd)
    with db:
        cursor = db.execute('''INSERT INTO tasks
            (name, cwd, command, environment, revision, dirty, timeout, submitted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (args.name or Path(command[0]).name, str(cwd), json.dumps(command),
             json.dumps(dict(os.environ)), revision, dirty, args.timeout, time.time()))
    return cursor.lastrowid


def start_worker(directory):
    # A dispatcher per submission waits on one shared lock. This also avoids a
    # lost wakeup when another dispatcher is exiting after an empty-queue check.
    with (directory / 'worker.log').open('ab') as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                          '--queue-dir', str(directory), 'worker'],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True, close_fds=True)


def stop_group(process):
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # Kill remaining descendants even when their foreground parent already quit.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_one(db, directory, task, lock_fd):
    process = None
    status, code, error = 'failed', None, None
    try:
        with (directory / f'{task["id"]}.log').open('ab', buffering=0) as log:
            log.write((f'cwd: {task["cwd"]}\ncommand: '
                       f'{shlex.join(json.loads(task["command"]))}\n').encode())
            process = subprocess.Popen(json.loads(task['command']), cwd=task['cwd'],
                                       env=json.loads(task['environment']),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True, pass_fds=(lock_fd,))
            with db:
                db.execute('UPDATE tasks SET pid=? WHERE id=?', (process.pid, task['id']))
            code = process.wait(timeout=task['timeout'])
            status = 'succeeded' if code == 0 else 'failed'
    except subprocess.TimeoutExpired:
        status, error = 'timed_out', f'Time limit exceeded: {task["timeout"]}s'
    except (KeyboardInterrupt, SystemExit):
        status, error = 'interrupted', 'Worker received a termination signal'
        raise
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        if process is not None:
            # Foreground commands must not leave background processes competing
            # with the next task. The same cleanup covers timeout and signals.
            stop_group(process)
            code = process.returncode
        with db:
            db.execute('''UPDATE tasks SET status=?, returncode=?, error=?, finished=?
                          WHERE id=?''', (status, code, error, time.time(), task['id']))


def work(db, directory):
    def terminated(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminated)
    signal.signal(signal.SIGINT, terminated)
    with (directory / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # A child inherits this lock. If a worker crashes, the next worker waits
        # until that child exits, then records the incomplete task without retry.
        with db:
            db.execute('''UPDATE tasks SET status='interrupted', finished=?,
                          error='Previous worker exited before recording completion'
                          WHERE status='running' ''', (time.time(),))
        while True:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
            if task is None:
                db.commit()
                return
            db.execute("UPDATE tasks SET status='running', started=? WHERE id=?",
                       (time.time(), task['id']))
            db.commit()
            run_one(db, directory, task, lock.fileno())


def lookup(db, task_id):
    task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if task is None:
        raise ValueError(f'Unknown task: {task_id}')
    return task


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('Timeout must be finite and positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue-dir', type=Path, default=default_directory())
    commands = parser.add_subparsers(dest='action', required=True)
    submit = commands.add_parser('submit', help='Queue a command and start a dispatcher')
    submit.add_argument('--cwd', default=os.getcwd())
    submit.add_argument('--name')
    submit.add_argument('--timeout', type=positive_seconds, help='Maximum running seconds')
    submit.add_argument('--no-start', action='store_true', help='Queue only; run worker later')
    submit.add_argument('command', nargs=argparse.REMAINDER)
    commands.add_parser('worker', help='Wait for the shared lock and drain the queue')
    commands.add_parser('list', help='List the latest 50 tasks')
    for action in ('show', 'logs', 'wait', 'cancel'):
        item = commands.add_parser(action)
        item.add_argument('id', type=int)
    args = parser.parse_args()
    directory = args.queue_dir.expanduser().resolve()
    # Environment snapshots and logs remain private machine-local state.
    os.umask(0o077)
    db = connect(directory)
    try:
        if args.action == 'submit':
            task_id = enqueue(db, args)
            print(task_id, flush=True)
            if not args.no_start:
                try:
                    start_worker(directory)
                except OSError as exc:
                    print(f'Task {task_id} saved; start worker manually: {exc}', file=sys.stderr)
                    return 1
        elif args.action == 'worker':
            work(db, directory)
        elif args.action == 'list':
            print('ID\tSTATUS\tNAME\tCWD')
            for row in db.execute('SELECT * FROM tasks ORDER BY id DESC LIMIT 50'):
                print(f'{row["id"]}\t{row["status"]}\t{row["name"]}\t{row["cwd"]}')
        elif args.action == 'show':
            row = dict(lookup(db, args.id))
            del row['environment']
            row['command'] = json.loads(row['command'])
            row['log'] = str(directory / f'{args.id}.log')
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.action == 'logs':
            lookup(db, args.id)
            path = directory / f'{args.id}.log'
            if path.exists():
                with path.open(errors='replace') as log:
                    for line in log:
                        print(line, end='')
        elif args.action == 'cancel':
            lookup(db, args.id)
            with db:
                result = db.execute("UPDATE tasks SET status='cancelled', finished=? WHERE id=? AND status='queued'",
                                    (time.time(), args.id))
            if result.rowcount != 1:
                raise ValueError('Only queued tasks can be cancelled')
        elif args.action == 'wait':
            while True:
                task = lookup(db, args.id)
                if task['status'] not in ('queued', 'running'):
                    print(task['status'])
                    return 0 if task['status'] == 'succeeded' else 1
                time.sleep(0.2)
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f'task-queue: {exc}', file=sys.stderr)
        sys.exit(2)
