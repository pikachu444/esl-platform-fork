"""Native Radioss deck and real OpenCourant subprocess execution, never a mock solver."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from .corner_model import impact_coordinates


def reals(*xs):
    return ''.join(f'{float(x):20.12E}' for x in xs)


def ints(*xs):
    return ''.join(f'{int(x):10d}' for x in xs)


def write_deck(path, mesh, cfg):
    path = Path(path); path.mkdir(parents=True, exist_ok=True)
    m, d = cfg['material'], cfg['drop']
    X, R = impact_coordinates(mesh, d)
    speed = np.sqrt(2*d['gravity_mm_s2']*d['height_mm'])
    if m.get('law', 'PLAS_JOHNS') == 'ELAST':
        material = ['/MAT/ELAST/1', 'linear elastic benchmark material',
                    reals(m['density_tonne_mm3']), reals(m['E_MPa'], m['nu'])]
    else:
        material = ['/MAT/PLAS_JOHNS/1', 'benchmark steel', reals(m['density_tonne_mm3']),
                    reals(m['E_MPa'], m['nu'])+ints(0, 0),
                    reals(m['yield_MPa'], m['hardening_MPa'], m['hardening_exponent'], 0, 0),
                    reals(0, 1)+ints(0, 0)+reals(0, 0), reals(0, 0, 0, 0)]
    s = ['#RADIOSS STARTER', '/BEGIN', 'corner', ints(2022, 0),
         '                  Mg                  mm                   s',
         '                  Mg                  mm                   s'] + material + [
         '/PROP/SHELL/1', 'QEPH five through-thickness points', ints(24, 0, 0, 0),
         reals(0, 0, 0, 0, 0), ints(5, 0)+reals(mesh['thickness'][0], 0)+' '*10+ints(1, 1),
         '/PART/1', 'wide beaded panel', ints(1, 1, 0), '/NODE']
    s.extend(ints(i)+reals(*p) for i, p in zip(mesh['node_id'], X))
    s.append('/SHELL/1')
    s.extend(ints(i, *(mesh['node_id'][c])) for i, c in zip(mesh['elem_id'], mesh['conn']))
    s.extend(['/GRNOD/NODE/1', 'all panel nodes'])
    ids = mesh['node_id']
    s.extend(ints(*ids[j:j+10]) for j in range(0, len(ids), 10))
    s.extend(['/INIVEL/TRA/1', 'velocity equivalent to specified free fall',
              reals(0, 0, -speed)+ints(1, 0),
              '/FUNCT/1', 'unit load multiplier', reals(0, 1), reals(1, 1),
              '/GRAV/1', 'gravity', ints(1)+'         Z'+ints(0, 0, 1)+' '*10+reals(1, -d['gravity_mm_s2']),
              '/RWALL/PLANE/1', 'ground with half thickness offset', ints(0, 2, 1, 0),
              reals(0, d['friction'], 0)+' '*20+ints(0), reals(0, 0, .5*float(mesh['thickness'][0])), reals(0, 0, 1),
              '/TH/RWALL/1', 'ground_force', 'FN        FT', ints(1), '/END'])
    starter = path/'corner_0000.rad'; starter.write_text('\n'.join(s)+'\n', encoding='ascii')
    eng = ['/RUN/corner/1', reals(d['end_time_s']), '/DT/NODA', reals(cfg['solver']['time_step_scale'], 0), '/PRINT/-100', '/TFILE', reals(d['frame_dt_s']/10),
           '/ANIM/DT', reals(0, d['frame_dt_s']), '/ANIM/MASS',
           '/ANIM/VECT/VEL', '/ANIM/VECT/ACC', '/ANIM/VECT/CONT', '/ANIM/VECT/FOPT', '/ANIM/VECT/FREAC',
           '/ANIM/VECT/FINT', '/ANIM/ELEM/EPSP', '/ANIM/SHELL/EPSP/ALL', '/ANIM/ELEM/VONM', '/ANIM/ELEM/ENER',
           '/ANIM/ELEM/HOURG', '/ANIM/SHELL/TENS/STRAIN/UPPER', '/ANIM/SHELL/TENS/STRAIN/LOWER',
           '/ANIM/SHELL/TENS/STRESS/UPPER', '/ANIM/SHELL/TENS/STRESS/LOWER', '/END']
    if m.get('law') == 'ELAST':
        eng = [line for line in eng if '/EPSP' not in line]
    (path/'corner_0001.rad').write_text('\n'.join(eng)+'\n', encoding='ascii')
    np.savez_compressed(path/'input_mesh.npz', **mesh, world_initial=X, initial_rotation=R)
    (path/'input_config.json').write_text(json.dumps(cfg, indent=2)+'\n')
    return starter


def solver_environment(root, threads):
    root = Path(root).resolve(); env = os.environ.copy()
    paths = [root/'extlib/hm_reader/linux64', root/'extlib/h3d/lib/linux64']
    env.update(RAD_CFG_PATH=str(root/'hm_cfg_files'), OPENCOURANT_PATH=str(root),
               OMP_NUM_THREADS=str(threads), OMP_STACKSIZE='128M',
               LD_LIBRARY_PATH=':'.join(map(str, paths))+':'+env.get('LD_LIBRARY_PATH', ''))
    return env


def run_solver(path, root, cfg):
    path, root = Path(path).resolve(), Path(root).resolve()
    env = solver_environment(root, cfg['solver']['threads'])
    commands = [[str(root/'exec/starter_linux64_gf'), '-i', 'corner_0000.rad', '-np', '1'],
                [str(root/'exec/engine_linux64_gf'), '-i', 'corner_0001.rad', '-nt', str(cfg['solver']['threads'])]]
    records = []
    for name, command in zip(['starter', 'engine'], commands):
        start = time.monotonic()
        with (path/f'{name}.log').open('w') as f:
            completed = subprocess.run(command, cwd=path, env=env, stdout=f, stderr=subprocess.STDOUT,
                                       timeout=cfg['solver']['timeout_s'])
        rec = dict(stage=name, command=command, returncode=completed.returncode,
                   elapsed_s=time.monotonic()-start)
        records.append(rec)
        (path/'execution.json').write_text(json.dumps(records, indent=2)+'\n')
        if completed.returncode:
            tail = (path/f'{name}.log').read_text(errors='replace')[-3500:]
            raise RuntimeError(f'{name} failed ({completed.returncode})\n{tail}')
    return records


def executable_provenance(root):
    return {n: hashlib.sha256((Path(root)/'exec'/n).read_bytes()).hexdigest()
            for n in ['starter_linux64_gf', 'engine_linux64_gf', 'anim_to_vtk_linux64_gf']}
