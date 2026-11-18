"""Reproduce flat-to-beaded displacement overshoot with real elastic corner drops."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import csv
from pathlib import Path

import numpy as np

from esl.doe import stiffness_metric
from esl.mech.drop_surrogates import make_shell
from esl.mech.shape_methods import Reference, project_fields, relative_error
from .corner_model import nodal_mass
from .radioss_runner import executable_provenance
from .shape_methods import load, read, run_dynamic, write
from .shape_methods_evaluate import resample, rms
from .shape_sensitivity import CONFIG


METHODS = ('frozen', 'balanced', 'snapshot_esl', 'reference_replay')
SCORE_METRICS = ('peak_max_mm', 'peak_rms_mm')
EXTENDED_CASES = ('flat', 'bead5_200', 'bead1_200', 'six_200')


def cases():
    result = {'flat': dict(id='flat', role='baseline', depths_mm=[0.]*6)}
    for bead, depths in ((5, (2., 1., .5, 1.5)), (1, (2.,))):
        for depth in depths:
            key = f'bead{bead}_{int(100*depth):03d}'
            shape = [0.]*6
            shape[bead-1] = depth
            result[key] = dict(id=key, role='validation', depths_mm=shape)
    result['six_200'] = dict(id='six_200', role='validation', depths_mm=[2.]*6)
    return result


def protocols():
    vertical = read(CONFIG/'shape_method_validation.json')
    coarse = deepcopy(vertical)
    coarse['drop']['panel_tilt_deg'] = 60.
    coarse['solver']['time_step_scale'] = .225
    fine = deepcopy(coarse)
    fine['solver']['time_step_scale'] = .45
    labels = tuple(cases())
    return {
        'inclined_coarse': (coarse, 1, labels),
        'inclined_fine': (fine, 2, labels),
        'vertical': (vertical, 1, ('flat', 'bead5_200', 'six_200')),
    }


def run_dir(out, tag, label, multiplier):
    return out/tag/'runs'/(label+('_fine' if multiplier==2 else ''))


def prior_six(prior, tag, cfg, multiplier):
    folder = 'corner' if tag == 'vertical' else tag
    path = run_dir(prior, folder, 'baseline', multiplier)
    signature = read(path/'complete.json')['signature']
    for key in ('plate', 'material', 'drop', 'solver', 'beads'):
        if signature['config'][key] != cfg[key]:
            raise ValueError(f'Reused dynamic input differs in {tag}/{key}')
    if signature['case']['depths_mm'] != [2.]*6 or signature['multiplier'] != multiplier:
        raise ValueError(f'Reused case has the wrong mesh or depth: {path}')
    return path


def run_case(task):
    out, solver, tag, cfg, multiplier, case = task
    result = run_dynamic(out/tag, solver, cfg, case, multiplier, record_progress=False)
    if not result['native_valid']:
        raise ValueError(f'Dynamic quality gate failed: {tag}/{case["id"]}')


def run(out, solver, jobs, prior):
    all_cases = cases()
    groups = []
    for tag, (cfg, multiplier, labels) in protocols().items():
        groups.append([(out, solver, tag, cfg, multiplier, all_cases[label]) for label in labels
                       if label != 'six_200' or not prior])
    work = [batch[i] for i in range(max(map(len, groups))) for batch in groups if i < len(batch)]
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        list(executor.map(run_case, work))


def gauges(cfg, multiplier):
    nx, ny = cfg['plate']['nx']*multiplier, cfg['plate']['ny']*multiplier
    a, b, c = nx*(ny+1)+ny, nx*(ny+1), ny
    # Same physical corners on either mesh. Zero-based node indices for the solver.
    return dict(primary=[(a, '123'), (b, '13'), (c, '3')],
                alternate=[(0, '123'), (b, '23'), (c, '3')])


def response(field, times):
    node_norm = np.linalg.norm(field, axis=2)
    max_trace = np.max(node_norm, axis=1)
    rms_trace = rms(field)
    i_max, i_rms = int(np.argmax(max_trace)), int(np.argmax(rms_trace))
    return dict(peak_max_mm=float(max_trace[i_max]), peak_rms_mm=float(rms_trace[i_rms]),
                peak_max_time_ms=float(times[i_max]*1000), peak_rms_time_ms=float(times[i_rms]*1000),
                max_trace_mm=max_trace.tolist(), rms_trace_mm=rms_trace.tolist())


def dynamic_field(path, mesh, times):
    with np.load(path/'history.npz', allow_pickle=False) as f:
        t, u = f['time'], f['u']
    if np.any(np.diff(t) <= 0) or t[0] > times[0] or t[-1] < times[-1]:
        raise ValueError(f'Dynamic history does not cover common times: {path}')
    return project_fields(mesh['x0'], resample({'time':t, 'u':u}, times))


def energy_rank(model, u6, loads, energy, frozen_details, baseline_peak):
    rows = []
    for i, (u, load_vector, c0, detail) in enumerate(zip(u6, loads, energy, frozen_details, strict=True)):
        if c0 <= baseline_peak * 1e-10:
            continue
        row = stiffness_metric.metrics(model.K(), u, load_vector, c0)
        row.update(entry_id=i, C=detail['compliance_Nmm'])
        rows.append(row)
    needs_full_solve = stiffness_metric.out_of_range(rows, stiffness_metric.LIN_VALID_DEFAULT)
    solve = stiffness_metric.score(rows, 'solve')['M_max']/baseline_peak
    ritz = stiffness_metric.score(rows, 'lin', 'ritz')['M_max']/baseline_peak
    return dict(solve_ratio=solve, ritz_ratio=ritz, effective_ritz_ratio=solve if needs_full_solve else ritz,
                ritz_falls_back_to_solve=needs_full_solve, rho_min=min(row['rho'] for row in rows),
                rho_max=max(row['rho'] for row in rows))


def interpolation(results):
    """Fit B5 at depths 0,1,2; evaluate predeclared 0.5 and 1.5 mm holdouts."""
    fit_labels = ('flat', 'bead5_100', 'bead5_200')
    reports = []
    for label, depth in [('bead5_050', .5), ('bead5_150', 1.5)]:
        actual = results[label]['methods']['dynamic']
        record = dict(depth_mm=depth, case=label, metrics={})
        for key in SCORE_METRICS:
            fitted = [results[label]['methods']['dynamic'][key] for label in fit_labels]
            predicted = float(np.interp(depth, [0., 1., 2.], fitted))
            base = fitted[0]
            record['metrics'][key] = dict(direct_mm=actual[key], predicted_mm=predicted,
                                          direct_change_mm=actual[key]-base, predicted_change_mm=predicted-base,
                                          abs_prediction_error_mm=abs(actual[key]-predicted))
        reports.append(record)
    return dict(fit_depths_mm=[0,1,2], holdouts=reports)


def evaluate(out, prior, solver_hashes):
    all_cases = cases()
    report = dict(methods=['dynamic', *METHODS], protocols={}, solver=solver_hashes)
    for tag, (cfg, multiplier, labels) in protocols().items():
        times = np.arange(201)*cfg['drop']['frame_dt_s']
        base_path = run_dir(out, tag, 'flat', multiplier)
        base = load(base_path/'input_mesh.npz')
        flat = dynamic_field(base_path, base, times)
        supports = gauges(cfg, multiplier)
        nominal = response(flat, times)
        ref = Reference(base, flat, [], cfg['study']['fd_step_mm'], supports)
        base_u6 = [np.column_stack([u, ref.model.rotations_for(u)]) for u in flat]
        c0 = [stiffness_metric.reference(ref.model.K(), u)['C_ref'] for u in base_u6]
        output = dict(tilt_deg=cfg['drop']['panel_tilt_deg'], elements=len(base['conn']),
                      dt_factor=cfg['solver']['time_step_scale'], time_ms=(times*1000).tolist(),
                      nodes_at_static_gauge={k:[(i+1, dofs) for i,dofs in v] for k,v in supports.items()},
                      cases={})
        report['protocols'][tag] = output
        for label in labels:
            reused = label == 'six_200' and prior is not None
            path = prior_six(prior, tag, cfg, multiplier) if reused else run_dir(out, tag, label, multiplier)
            mesh = load(path/'input_mesh.npz')
            metrics = read(path/'metrics.json')
            if not metrics['native_valid'] or not np.array_equal(mesh['depths'], all_cases[label]['depths_mm']):
                raise ValueError(f'Native invalid or wrong depth input: {path}')
            actual = dynamic_field(path, mesh, times)
            fields, diagnostics = ref.predict(mesh, mesh['depths'], nodal_mass(mesh, cfg['material']['density_tonne_mm3']), METHODS)
            if set(fields) != set(METHODS):
                raise ValueError(f'Incomplete comparison for {tag}/{label}: {set(METHODS)-set(fields)}')
            detail = {'depths_mm': mesh['depths'].tolist(), 'reused': reused,
                      'native_peak_max_mm': metrics['max_node_deflection_mm'],
                      'native_peak_rms_mm': metrics['peak_rms_mm'], 'engine_seconds': metrics['execution'][-1]['elapsed_s'],
                      'hashes': {k:v for k,v in read(path/'complete.json').items() if k.endswith('_sha256')},
                      'methods': {}, 'stiffness': energy_rank(make_shell(mesh), base_u6, ref.f0, c0,
                                                             diagnostics['frozen']['details'], max(c0))}
            output['cases'][label] = detail
            reference = fields['reference_replay']
            true_change = actual-reference
            actual_scores = response(actual, times)
            for name, field in [('dynamic',actual), *fields.items()]:
                scores = response(field, times)
                scores.update(change_max_mm=scores['peak_max_mm']-nominal['peak_max_mm'],
                              change_rms_mm=scores['peak_rms_mm']-nominal['peak_rms_mm'],
                              ratio_to_dynamic_max=scores['peak_max_mm']/actual_scores['peak_max_mm'],
                              field_error=relative_error(field, actual),
                              change_field_error=relative_error(field-reference, true_change) if label != 'flat' else None,
                              gauge_error=diagnostics.get(name, {}).get('gauge_relative_l2'))
                detail['methods'][name] = scores
            if label == 'bead5_200':
                i = int(np.argmax(detail['methods']['frozen']['max_trace_mm']))
                np.savez_compressed(out/f'{tag}_bead5_200_snapshot.npz', time_ms=times[i]*1000,
                                    x0=mesh['x0'], conn=mesh['conn'], dynamic=actual[i],
                                    **{name: field[i] for name,field in fields.items()})
            print(f'Compared {tag}/{label}', flush=True)
        if 'bead5_050' in labels:
            output['direct_interpolation'] = interpolation(output['cases'])
        write(out/'comparison.json', report)

    with (out/'peak_displacement.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = ['protocol','case','method','peak_max_mm','peak_max_time_ms','peak_rms_mm','peak_rms_time_ms',
                  'change_max_mm','change_rms_mm','ratio_to_dynamic_max','field_error','change_field_error','gauge_error']
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for tag, group in report['protocols'].items():
            for label, case in group['cases'].items():
                for name, scores in case['methods'].items():
                    writer.writerow(dict(protocol=tag, case=label, method=name, **scores))


def extended_check(out, solver, jobs):
    cfg, multiplier, _ = protocols()['inclined_fine']
    cfg['drop']['end_time_s'] = .08
    tag = 'inclined_extended'
    all_cases = cases()
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        list(executor.map(run_case, [(out, solver, tag, cfg, multiplier, all_cases[label]) for label in EXTENDED_CASES]))
    report = dict(tilt_deg=cfg['drop']['panel_tilt_deg'], elements=3840, end_time_ms=80, cases={})
    for label in EXTENDED_CASES:
        path = run_dir(out, tag, label, multiplier)
        metrics = read(path/'metrics.json')
        with np.load(path/'history.npz', allow_pickle=False) as f:
            t, u = f['time'], f['u']
        report['cases'][label] = dict(
            **response(u, t), time_ms=(t*1000).tolist(), native_valid=metrics['native_valid'],
            hashes={k:v for k,v in read(path/'complete.json').items() if k.endswith('_sha256')},
        )
    write(out/'extended_dynamic.json', report)


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('dynamic','evaluate','all','extended'))
    parser.add_argument('--solver', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--previous-audit', type=Path, help='Reuse matching 2 mm six-bead runs from shape_sensitivity')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    out, solver = args.out.resolve(), args.solver.resolve()
    prior = args.previous_audit.resolve() if args.previous_audit else None
    out.mkdir(parents=True, exist_ok=True)
    solver_hashes = executable_provenance(solver)
    if prior and read(prior/'sensitivity_solver.json') != solver_hashes:
        raise ValueError('Reused solver executables do not match')
    with (out/'.insertion.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage in ('dynamic','all'):
            run(out, solver, args.jobs, prior)
        if args.stage in ('evaluate','all'):
            evaluate(out, prior, solver_hashes)
        if args.stage == 'extended':
            extended_check(out, solver, args.jobs)


if __name__ == '__main__':
    main()
