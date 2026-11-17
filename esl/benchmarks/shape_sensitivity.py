"""Audit bead 5 sensitivity against explicit time stepping, mesh and touchdown phase."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path

import numpy as np

from esl.mech.shape_methods import project_fields, relative_error
from .radioss_runner import executable_provenance
from .shape_methods import load, read, run_dynamic, write
from .shape_methods_evaluate import resample, rms


CONFIG = Path(__file__).resolve().parents[2]/'config'
STEPS = (.05, .025, .0125)
PAIRS = (('cal_b5_minus', 'cal_b5_plus'), ('check_b5_minus', 'check_b5_plus'),
         ('audit_b5_0125_minus', 'audit_b5_0125_plus'))
WINDOW_ENDS_MS = (4, 12, 24, 39)


def settings():
    corner = read(CONFIG/'shape_method_validation.json')
    flat = read(CONFIG/'shape_method_control_flat.json')
    half, quarter, shifted = (deepcopy(corner) for _ in range(3))
    half['solver']['time_step_scale'] *= .5
    quarter['solver']['time_step_scale'] *= .25
    # Increase travel to contact while keeping nominal touchdown speed the same.
    shifted['drop']['clearance_mm'] += .02
    shifted['drop']['height_mm'] -= .02
    return {
        'corner': ('corner', corner, 1, 3),
        'half_step': ('half_step', half, 1, 3),
        'quarter_step': ('quarter_step', quarter, 1, 3),
        'fine_mesh': ('corner', corner, 2, 3),
        'clearance_shift': ('clearance_shift', shifted, 1, 2),
        'near_flat': ('near_flat', flat, 1, 3),
    }


def study_cases(cfg, pair_count):
    cases = {case['id']: case for case in cfg['cases']}
    base = cases['baseline']
    for label, change in zip(PAIRS[2], (-STEPS[2], STEPS[2]), strict=True):
        case = deepcopy(base)
        case.update(id=label, role='sensitivity_check')
        case['depths_mm'][4] += change
        cases[label] = case
    return [base] + [cases[label] for pair in PAIRS[:pair_count] for label in pair]


def execute(job):
    folder, solver, cfg, case, multiplier = job
    metrics = run_dynamic(folder, solver, cfg, case, multiplier, record_progress=False)
    if not metrics['native_valid']:
        raise ValueError(f'Native output did not pass quality checks: {folder}/{case["id"]}')


def run(out, solver, jobs):
    provenance = executable_provenance(solver)
    marker = out/'sensitivity_solver.json'
    if marker.exists() and read(marker) != provenance:
        raise ValueError(f'Incompatible solver binaries for {out}')
    write(marker, provenance)
    batches = []
    for folder, cfg, multiplier, pair_count in settings().values():
        cases = study_cases(cfg, pair_count)
        batches.append([(out/folder, solver, cfg, case, multiplier) for case in cases])
    ordered = [batch[i] for i in range(max(map(len, batches))) for batch in batches if i < len(batch)]
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        list(executor.map(execute, ordered))


def touchdown_time(cfg):
    drop = cfg['drop']
    g, gap = drop['gravity_mm_s2'], drop['clearance_mm']
    v0 = np.sqrt(2*g*drop['height_mm'])
    return 2*gap/(v0 + np.sqrt(v0**2 + 2*g*gap))


def native_fields(case_path, cfg, times, multiplier, x_reference):
    with np.load(case_path/'history.npz', allow_pickle=False) as data:
        h = {'time': data['time'], 'u': data['u']}
        elapsed = times + touchdown_time(cfg)
        if elapsed[0] < h['time'][0] or elapsed[-1] > h['time'][-1]:
            raise ValueError(f'Insufficient native samples in {case_path}')
        fields = resample(h, elapsed)
        reactions = data['contact']
        contact_nodes = np.linalg.norm(reactions, axis=-1) > 1e-6

    if multiplier > 1:
        nx, ny = cfg['plate']['nx'], cfg['plate']['ny']
        rows, columns = nx*multiplier + 1, ny*multiplier + 1
        x_fine = load(case_path/'input_mesh.npz')['x0'].reshape(rows, columns, 3)
        np.testing.assert_allclose(x_fine[::multiplier, ::multiplier, :2].reshape(-1, 2), x_reference[:, :2])
        fields = fields.reshape(len(times), rows, columns, 3)[:, ::multiplier, ::multiplier]
        fields = fields.reshape(len(times), -1, 3)

    data = load(case_path/'global_history.npz')
    impulse_key, = (name for name in data if 'ground_force' in name and name.endswith('var 26'))
    impulse_native = -data[impulse_key]
    first, = np.flatnonzero(impulse_native > 1e-8)[:1]
    first_frame, = np.flatnonzero(contact_nodes.any(axis=1))[:1]
    metrics = read(case_path/'metrics.json')
    if not metrics['native_valid']:
        raise ValueError(f'Native validity gate failed: {case_path}')
    diagnostic = dict(
        peak_rms_mm=metrics['peak_rms_mm'], peak_rms_time_s=metrics['peak_rms_time_s'],
        first_wall_impulse_bracket_ms=(1000*data['time'][[max(0, first-1), first]]).tolist(),
        first_field_frame_contact_node_ids=(np.flatnonzero(contact_nodes[first_frame])+1).tolist(),
        final_normal_impulse_ns=float(impulse_native[-1]),
        median_native_dt_us=float(np.median(data['TIME STEP'][1:])*1e6),
        energy_indicator=metrics['energy_balance_fraction'],
        instantaneous_force_residual=metrics['quality']['instantaneous_force_residual_fraction'],
        momentum_residual=metrics['quality']['momentum_residual_fraction'],
        integration_seconds=metrics['execution'][-1]['elapsed_s'],
        native_valid=True,
    )
    return project_fields(x_reference, fields), np.interp(elapsed, data['time'], impulse_native), diagnostic


def summary(out):
    times = np.arange(196)*.0002
    time_ms = times*1000
    windows = {f'0_to_{end}ms': time_ms <= end + 1.e-8 for end in WINDOW_ENDS_MS}
    windows.update({f'{lo}_to_{hi}ms': (time_ms > lo) & (time_ms <= hi + 1.e-8)
                    for lo, hi in zip(WINDOW_ENDS_MS, WINDOW_ENDS_MS[1:])})
    original = out/'corner/runs/baseline'
    x_reference = load(original/'input_mesh.npz')['x0']
    results, fields, derivatives, histories = {}, {}, {}, {'time_after_touchdown_ms': time_ms}
    for name, (folder, cfg, multiplier, pair_count) in settings().items():
        results[name] = dict(mesh_elements=cfg['plate']['nx']*cfg['plate']['ny']*multiplier**2,
                             dt_factor=cfg['solver']['time_step_scale'],
                             nominal_touchdown_ms=float(touchdown_time(cfg)*1000),
                             cases={}, step_comparison={}, central_asymmetry={})
        current = results[name]
        for case in study_cases(cfg, pair_count):
            label = case['id']
            suffix = '_fine' if multiplier > 1 else ''
            case_path = out/folder/'runs'/(label+suffix)
            fields[name, label], histories[f'{name}__{label}__impulse_ns'], current['cases'][label] = native_fields(
                case_path, cfg, times, multiplier, x_reference)
            histories[f'{name}__{label}__rms_mm'] = rms(fields[name, label])

        baseline = fields[name, 'baseline']
        for step, (minus, plus) in zip(STEPS[:pair_count], PAIRS[:pair_count], strict=True):
            low, high = fields[name, minus], fields[name, plus]
            gradient = (high-low)/(2*step)
            derivatives[name, step] = gradient
            histories[f'{name}__{step:g}__bead5_rms_sensitivity'] = rms(gradient)
            asymmetry, difference = high+low-2*baseline, high-low
            current['central_asymmetry'][str(step)] = {
                window: float(np.linalg.norm(asymmetry[mask])/max(np.linalg.norm(difference[mask]), 1e-15))
                for window, mask in windows.items()}

        for wide, small in zip(STEPS[:pair_count-1], STEPS[1:pair_count], strict=True):
            a, b = derivatives[name, wide], derivatives[name, small]
            current['step_comparison'][f'{wide:g}_to_{small:g}'] = {
                window: relative_error(a[mask], b[mask]) for window, mask in windows.items()}

    for name in ('half_step', 'quarter_step', 'fine_mesh', 'clearance_shift'):
        reference = 'half_step' if name == 'quarter_step' else 'corner'
        a, b = fields[reference, 'baseline'], fields[name, 'baseline']
        current = results[name]
        current['discretization_reference'] = reference
        current['baseline_field_error'] = {window: relative_error(a[mask], b[mask]) for window, mask in windows.items()}
        current['gradient_change'] = {
            str(step): {window: relative_error(derivatives[reference, step][mask], gradient[mask])
                        for window, mask in windows.items()}
            for (protocol, step), gradient in derivatives.items() if protocol == name}

    result = dict(bead=5, steps_mm=STEPS, sample_interval_ms=.2, timing='nominal touchdown + common physical time',
                  comparison_mesh='all protocols compared at common 1025 nodes', protocols=results)
    write(out/'sensitivity_audit.json', result)
    np.savez_compressed(out/'sensitivity_histories.npz', **histories)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--solver', type=Path, help='Run native cases before summarizing')
    parser.add_argument('--jobs', type=int, default=1)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.solver:
        import fcntl

        with (args.out/'.sensitivity.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(args.out, args.solver.resolve(), args.jobs)
            summary(args.out)
    else:
        summary(args.out)


if __name__ == '__main__':
    main()
