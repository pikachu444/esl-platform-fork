"""Detached Linux experiment worker. Inherits the cross-process concurrency lock."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import time

from .experiment import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock-fd', type=int, required=True)
    parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--solver', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--method', action='append', default=[])
    parser.add_argument('--study',choices=['legacy','shape'],default='legacy')
    args = parser.parse_args()
    out = Path(args.out); canceled = False

    def stop(_sig, _frame):
        nonlocal canceled
        canceled = True
        raise InterruptedError('user canceled the experiment')

    def deadline(_sig, _frame):
        raise TimeoutError('experiment runtime limit exceeded')

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, args.timeout)
    command = ['corner_drop', 'all', '--solver', args.solver, '--config', args.config, '--out', args.out]
    for method in args.method: command.extend(['--method', method])
    exit_code = 0
    try:
        if args.study=='shape':
            from .shape_methods import main as run
        else:
            from .corner_drop import main as run
        sys.argv = command
        run()
        if args.study=='shape':
            from .shape_report import generate_report
        else:
            from .report import generate_report
        generate_report(out)
    except Exception as exc:
        exit_code = 1
        write_json(out/'progress.json', dict(status='canceled' if canceled else 'failed',
                   stage='stopped', error=f'{type(exc).__name__}: {exc}', updated_at=time.time()))
        print(f'{type(exc).__name__}: {exc}', flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        write_json(out/'process_exit.json', dict(returncode=exit_code, finished_at=time.time()))
        import os
        os.close(args.lock_fd)
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
