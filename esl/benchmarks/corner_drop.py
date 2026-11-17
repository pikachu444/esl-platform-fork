"""Corner drop experiment CLI. Method definitions are fixed in its contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experiment import Experiment, write_json
from esl.mech.drop_surrogates import METHODS


def load_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text())
    if 'extends' in cfg:
        base = load_config(path.parent/cfg.pop('extends'))
        for key, value in cfg.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key].update(value)
            else:
                base[key] = value
        cfg = base
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['baseline', 'search', 'validate', 'all'])
    parser.add_argument('--config', default=str(Path(__file__).resolve().parents[2]/'config/corner_drop_benchmark.json'))
    parser.add_argument('--solver', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--method', action='append', choices=list(METHODS), help='Omit to run all six methods')
    args = parser.parse_args()
    cfg = load_config(args.config)
    out = Path(args.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock = (out/'.execution.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        parser.error('another experiment is using this output folder')
    try:
        experiment = Experiment(cfg, args.solver, out, args.method)
        if args.stage == 'baseline': result = experiment.baseline()
        elif args.stage == 'search': result = experiment.search()
        elif args.stage == 'validate': result = experiment.validate()
        else:
            experiment.search(); result = experiment.validate()
        print(json.dumps(dict(stage=args.stage, output=str(out), status='completed'), ensure_ascii=False), flush=True)
    except Exception as exc:
        write_json(out/'progress.json', dict(status='failed', stage=args.stage, error=f'{type(exc).__name__}: {exc}'))
        raise
    finally:
        lock.close()


if __name__ == '__main__':
    main()
