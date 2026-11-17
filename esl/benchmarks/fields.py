"""Read the official animation converter's legacy VTK and preserve actual solver fields."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import re
import subprocess

import numpy as np

from esl.mech.kabsch import remove_rigid
from .corner_model import nodal_mass


def read_vtk(text):
    stream = iter(io.StringIO(text)); point, cell, meta = {}, {}, {}
    location, count = None, 0
    result = dict(point=point, cell=cell, meta=meta)

    def numbers(n, dtype=float):
        values = []
        while len(values) < n:
            values.extend(next(stream).split())
        if len(values) != n:
            raise ValueError(f'VTK field has {len(values)} tokens, expected {n}')
        return np.asarray(values, dtype=dtype)

    for line in stream:
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind == 'FIELD':
            for _ in range(int(parts[2])):
                name, nc, nt, _dtype = next(stream).split()
                meta[name] = numbers(int(nc)*int(nt)).reshape(int(nt), int(nc))
        elif kind == 'POINTS':
            result['x'] = numbers(int(parts[1])*3).reshape(-1, 3)
        elif kind == 'CELLS':
            result['cells'] = numbers(int(parts[2]), int)
        elif kind == 'CELL_TYPES':
            result['cell_types'] = numbers(int(parts[1]), int)
        elif kind in ('POINT_DATA', 'CELL_DATA'):
            location = point if kind == 'POINT_DATA' else cell
            count = int(parts[1])
        elif kind == 'SCALARS':
            nc = int(parts[3]) if len(parts) > 3 else 1
            if not next(stream).startswith('LOOKUP_TABLE'):
                raise ValueError('missing VTK lookup table')
            val = numbers(count*nc)
            location[parts[1]] = val if nc == 1 else val.reshape(count, nc)
        elif kind in ('VECTORS', 'TENSORS'):
            nc = 3 if kind == 'VECTORS' else 9
            location[parts[1]] = numbers(count*nc).reshape(count, nc)
    if 'x' not in result or 'TIME' not in meta:
        raise ValueError('VTK has no coordinates or time')
    result['time'] = float(meta['TIME'][0, 0])
    return result


def history_csv(path, root):
    path, root = Path(path), Path(root)
    source = path/'cornerT01'
    if not source.exists():
        raise ValueError('solver time history is missing')
    # Native converter has a short Fortran filename buffer. Keep the argv local;
    # project/run isolation can otherwise produce paths longer than that buffer.
    subprocess.run([str(root/'exec/th_to_csv_linux64_gf'), source.name], cwd=path,
                   check=True, capture_output=True, text=True)
    with source.with_suffix('.csv').open() as f:
        rows = list(csv.reader(f))
    names = [s.strip() for s in rows[0] if s.strip()]
    values = np.asarray([[float(x) for x in row[:len(names)]] for row in rows[1:] if row], float)
    if values.shape[1] != len(names):
        raise ValueError('time history columns differ')
    return dict(zip(names, values.T))


def extract(path, root, cfg):
    path, root = Path(path), Path(root)
    with np.load(path/'input_mesh.npz') as z:
        mesh = {k: z[k] for k in z.files}
    frames = sorted((f for f in path.glob('cornerA*') if re.fullmatch(r'cornerA\d+', f.name)),
                    key=lambda f: int(f.name[len('cornerA'):]))
    if not frames:
        raise ValueError('no actual solver animations')
    wanted_nodes, wanted_elems = mesh['node_id'], mesh['elem_id']
    node_set, elem_set = set(wanted_nodes), set(wanted_elems)
    collected = {k: [] for k in ['time', 'x', 'u', 'rotation', 'translation', 'velocity', 'acceleration',
                                 'contact', 'wall', 'internal', 'plastic', 'plastic_layers', 'stress_upper',
                                 'stress_lower', 'strain_upper', 'strain_lower', 'von_mises', 'hourglass', 'erosion']}
    source_fields = None
    for frame in frames:
        text = subprocess.run([str(root/'exec/anim_to_vtk_linux64_gf'), str(frame)],
                              check=True, capture_output=True, text=True).stdout
        data = read_vtk(text)
        if source_fields is None:
            source_fields = dict(point=list(data['point']), cell=list(data['cell']))
        nodes = data['point']['NODE_ID'].astype(int)
        elems = data['cell']['ELEMENT_ID'].astype(int)
        ni = {n: i for i, n in enumerate(nodes) if n in node_set}
        parts = data['cell']['PART_ID'].astype(int)
        ei = {n: i for i, n in enumerate(elems) if n in elem_set and parts[i] == 1}
        if len(ni) != len(wanted_nodes) or len(ei) != len(wanted_elems):
            raise ValueError('solver animation node/element IDs differ from the input model')
        ix = np.asarray([ni[n] for n in wanted_nodes]); ex = np.asarray([ei[n] for n in wanted_elems])
        X = data['x'][ix]
        u, R, t, _ = remove_rigid(mesh['x0'], X-mesh['x0'])
        collected['time'].append(data['time']); collected['x'].append(X)
        collected['u'].append(u); collected['rotation'].append(R); collected['translation'].append(t)
        for target, key in [('velocity', 'Velocity'), ('acceleration', 'Acceleration'),
                            ('contact', 'Reaction_Forces'), ('wall', 'Sect.RBY,Wall_F.'),
                            ('internal', 'Internal_Forces')]:
            if key not in data['point']:
                raise ValueError(f'required solver field missing: {key}')
            collected[target].append(data['point'][key][ix])
        for target, key in [('von_mises', '2DELEM_Von_Mises'),
                            ('hourglass', '2DELEM_Hourglass_Energy_per_unit_mass'), ('erosion', 'EROSION_STATUS')]:
            if key not in data['cell']:
                raise ValueError(f'required solver field missing: {key}')
            collected[target].append(data['cell'][key][ex])
        layers = [data['cell'][f'2DELEM_Plast_Strn_Layer___{i}_'][ex] for i in range(1, 6)]
        collected['plastic_layers'].append(np.stack(layers, axis=1))
        collected['plastic'].append(np.max(layers, axis=0))
        for target, key in [('stress_upper', '2DELEM_Stress_(upper)'), ('stress_lower', '2DELEM_Stress_(lower)'),
                            ('strain_upper', '2DELEM_Strain_(upper)'), ('strain_lower', '2DELEM_Strain_(lower)')]:
            collected[target].append(data['cell'][key][ex])
    arrays = {k: np.asarray(v) for k, v in collected.items()}
    arrays['mass'] = nodal_mass(mesh, cfg['material']['density_tonne_mm3'])
    hist = history_csv(path, root)
    np.savez_compressed(path/'history.npz', **arrays)
    np.savez_compressed(path/'global_history.npz', **hist)
    # Mass is reconstructed from actual input elements, not invented from an absent result field.
    measured = float(hist['MASS'][0]); assembled = float(arrays['mass'].sum())
    mass_error = abs(measured-assembled)/measured
    metadata = dict(units=dict(length='mm', time='s', mass='tonne', force='N', stress='MPa'),
                    fields=source_fields, mass_source='initial element area*rho*t/4, checked against solver total mass',
                    solver_total_mass=measured, assembled_total_mass=assembled, mass_relative_error=mass_error,
                    animation_coordinate_precision='float32 (official animation format/converter)',
                    contact_source='Reaction_Forces on plate nodes: RWALL reaction on the plate; Contact_Forces is interface-only',
                    plastic_source='maximum over all five through-thickness integration points per shell element',
                    frames=len(frames), first_time=float(arrays['time'][0]), last_time=float(arrays['time'][-1]))
    (path/'field_provenance.json').write_text(json.dumps(metadata, indent=2)+'\n')
    if mass_error > 1e-5:
        raise ValueError(f'assembled mass differs from solver: {mass_error}')
    return arrays, hist, metadata


def dynamic_metrics(arrays, history):
    norms = np.linalg.norm(arrays['u'], axis=2)
    rms = np.sqrt(np.mean(norms**2, axis=1))
    plastic_p95 = np.percentile(arrays['plastic'], 95, axis=1)
    initial_energy = float(history['KINETIC ENERGY'][0])
    total = history['KINETIC ENERGY']+history['INTERNAL ENERGY']+history['ROTATION ENERGY']
    balance = total-initial_energy-history['EXTERNAL WORK']
    stress = np.stack((arrays['stress_upper'], arrays['stress_lower'])).reshape(2, -1, 3, 3)
    dev = stress-np.trace(stress, axis1=-2, axis2=-1)[..., None, None]*np.eye(3)/3
    surface_vm = np.sqrt(1.5*np.sum(dev*dev, axis=(-1, -2)))
    return dict(peak_rms_mm=float(rms.max()), peak_rms_time_s=float(arrays['time'][rms.argmax()]),
                peak_def_mm=float(norms.max()), final_rms_mm=float(rms[-1]),
                peak_plastic=float(arrays['plastic'].max()), plastic_p95=float(plastic_p95.max()),
                max_von_mises_MPa=float(max(arrays['von_mises'].max(), surface_vm.max())),
                initial_energy_Nmm=initial_energy,
                energy_balance_fraction=float(np.max(np.abs(balance))/initial_energy),
                hourglass_fraction=float(np.max(np.abs(history['HOURGLASS ENERGY']))/initial_energy),
                added_mass_fraction=float(np.max(history['ADDED MASS'])/history['MASS'][0]),
                initial_mass_tonne=float(history['MASS'][0]),
                frame_time_s=arrays['time'].tolist(), rms_history_mm=rms.tolist())


def quality_metrics(arrays, history, cfg):
    """Independent wall-impulse balance; TH/RWALL FN/FT are impulses, not forces."""
    times = arrays['time']; m = arrays['mass']; total_mass = float(m.sum())
    impulses = []
    for i in range(6):
        keys = [k for k in history if 'ground_force' in k and re.search(r'var\s+'+str(24+i)+r'$', k)]
        if len(keys) != 1:
            raise ValueError(f'missing independent wall impulse component {i}: {keys}')
        impulses.append(np.interp(times, history['time'], history[keys[0]]))
    # The history impulse is exerted ON THE WALL, opposite to plate reaction.
    wall_impulse = np.asarray(impulses).T
    panel_impulse = -(wall_impulse[:, :3]+wall_impulse[:, 3:])
    speed = np.sqrt(2*cfg['drop']['gravity_mm_s2']*cfg['drop']['height_mm'])
    p_initial = np.array([0., 0., -total_mass*speed])
    gravity_impulse = total_mass*times[:, None]*np.array([0., 0., -cfg['drop']['gravity_mm_s2']])
    actual_p = np.einsum('n,tnj->tj', m, arrays['velocity'])
    error = actual_p-p_initial-gravity_impulse-panel_impulse
    # Internal_Forces uses the driving-force sign in the native solver output.
    ma = arrays['acceleration']*m[None, :, None]
    mg = m[None, :, None]*np.array([0., 0., -cfg['drop']['gravity_mm_s2']])
    residual = ma-arrays['internal']-arrays['contact']-mg
    denom = np.maximum(np.linalg.norm(ma, axis=(1, 2)), 1e-20)
    return dict(momentum_residual_fraction=float(np.linalg.norm(error, axis=1).max()/np.linalg.norm(p_initial)),
                instantaneous_force_residual_fraction=float((np.linalg.norm(residual, axis=(1, 2))/denom).max()),
                minimum_active_status=float(arrays['erosion'].min()),
                max_wall_penetration_mm=float(max(0, .5*cfg['plate']['thickness_mm']-arrays['x'][:, :, 2].min())),
                wall_impulse_sign='TH/RWALL FN+FT acts on wall; negate for plate',
                momentum_history_residual_Ns=error.tolist())
