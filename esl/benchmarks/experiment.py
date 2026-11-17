"""Restartable orchestration of real drops, fixed-budget searches and re-drops."""
from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from scipy.stats import qmc, spearmanr

from esl.mech.drop_surrogates import METHODS, DropReference
from .corner_model import make_mesh, nodal_mass, nodal_normals, geometry_metrics
from .fields import extract, dynamic_metrics, quality_metrics
from .radioss_runner import executable_provenance, run_solver, write_deck


def write_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


def design_id(depths):
    return hashlib.sha256(np.asarray(depths, dtype='<f8').round(8).tobytes()).hexdigest()[:12]


def check_quality(metrics, quality, cfg, multiplier=1):
    a = cfg['acceptance']; failures = []
    for value, limit in [('added_mass_fraction', 'max_added_mass_fraction'),
                         ('hourglass_fraction', 'max_hourglass_initial_energy_fraction'),
                         ('energy_balance_fraction', 'max_energy_balance_fraction')]:
        if metrics[value] > a[limit]: failures.append(f'{value}={metrics[value]:.6g} > {a[limit]}')
    for value, limit in [('momentum_residual_fraction', 'max_momentum_residual_fraction'),
                         ('instantaneous_force_residual_fraction', 'max_instantaneous_force_residual_fraction'),
                         ('max_wall_penetration_mm', 'max_wall_penetration_mm')]:
        if quality[value] > a[limit]: failures.append(f'{value}={quality[value]:.6g} > {a[limit]}')
    if quality['minimum_active_status'] < 1: failures.append('deleted/inactive shell element')
    if metrics['frame_time_s'][-1] < cfg['drop']['end_time_s']-1.1*cfg['drop']['frame_dt_s']:
        failures.append('incomplete duration')
    if multiplier > 1 and metrics['energy_balance_fraction'] > a['max_fine_energy_balance_fraction']:
        failures.append(f"fine energy_balance_fraction={metrics['energy_balance_fraction']:.6g} > {a['max_fine_energy_balance_fraction']}")
    return failures


class Experiment:
    def __init__(self, cfg, solver, out, methods=None):
        self.cfg = cfg; self.solver = Path(solver).resolve(); self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.methods = list(methods or cfg['methods'])
        if not self.methods or any(m not in METHODS for m in self.methods): raise ValueError('invalid method selection')
        self.mesh = make_mesh(cfg); self.mass0 = float(nodal_mass(self.mesh, cfg['material']['density_tonne_mm3']).sum())
        self.ref = None; self.records = {}; self.started = time.time()
        self.cache_path = self.out/'candidates.json'
        if self.cache_path.exists(): self.records = json.loads(self.cache_path.read_text())
        expected = dict(config=cfg, solver=executable_provenance(self.solver), schema='corner-drop/run/2')
        manifest = self.out/'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text()) != expected:
            raise ValueError('output folder belongs to a different config/solver/schema; use a new folder')
        write_json(manifest, expected)

    def progress(self, stage, message, **extra):
        record = dict(status='running', stage=stage, message=message, updated_at=time.time(),
                      elapsed_s=time.time()-self.started, **extra)
        write_json(self.out/'progress.json', record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def drop(self, depths, label, variation=None, multiplier=1):
        cfg = deepcopy(self.cfg)
        if variation: cfg['drop'].update({k:v for k,v in variation.items() if k != 'name'})
        path = self.out/label; mesh = make_mesh(cfg, depths, multiplier)
        signature = dict(config=cfg, depths=np.asarray(depths).tolist(), multiplier=multiplier, extraction_schema=2)
        done = path/'complete.json'
        if done.exists() and json.loads(done.read_text())['signature'] == signature:
            metrics=json.loads((path/'metrics.json').read_text())
            quality=json.loads((path/'quality.json').read_text())
            failures=check_quality(metrics,quality,cfg,multiplier)
            metrics.update(quality_passed=not failures,quality_failures=failures)
            write_json(path/'metrics.json',metrics)
            return metrics,path
        self.progress('dynamic', f'실제 낙하: {label}', design=label)
        # Re-extract a completed native run only when its actual deck inputs match.
        native_matches = False
        if (path/'input_config.json').exists() and (path/'input_mesh.npz').exists() and (path/'engine.log').exists():
            with np.load(path/'input_mesh.npz') as z:
                native_matches = (json.loads((path/'input_config.json').read_text()) == cfg
                                  and np.array_equal(z['x0'], mesh['x0'])
                                  and 'NORMAL TERMINATION' in (path/'engine.log').read_text())
        if not native_matches:
            if path.exists() and any(path.iterdir()):
                raise ValueError(f'refusing to overwrite incompatible or failed run: {path}')
            write_deck(path, mesh, cfg)
            write_json(path/'solver_provenance.json', executable_provenance(self.solver))
            run_solver(path, self.solver, cfg)
        arrays, history, _ = extract(path, self.solver, cfg)
        metrics = dynamic_metrics(arrays, history); quality = quality_metrics(arrays, history, cfg)
        failures = check_quality(metrics, quality, cfg, multiplier)
        metrics.update(quality_passed=not failures, quality_failures=failures, depths_mm=np.asarray(depths).tolist(),
                       geometry=geometry_metrics(mesh, cfg['material']['density_tonne_mm3'], self.mass0, cfg['beads']))
        write_json(path/'metrics.json', metrics); write_json(path/'quality.json', quality)
        write_json(done, dict(signature=signature, quality_passed=not failures))
        return metrics, path

    def baseline(self):
        metrics, path = self.drop(self.mesh['depths'], 'baseline')
        if not metrics['quality_passed']:
            raise ValueError('baseline quality gate failed: '+'; '.join(metrics['quality_failures']))
        with np.load(path/'history.npz') as z: h = dict(z)
        # Explicit, known initial displacement for the incremental reference path.
        for key in ['u','x','rotation','translation','contact','acceleration','velocity','time']:
            if key == 'u': value = np.zeros_like(h[key][0])
            elif key == 'time': value = 0.
            else: value = h[key][0]
            h[key] = np.concatenate((np.asarray(value)[None], h[key]), axis=0)
        rms = np.sqrt(np.mean(np.sum(h['u']**2, axis=2), axis=1)); peak = int(rms.argmax())
        n = len(h['time']); s = self.cfg['sampling']
        loads = np.rint(np.linspace(1, n-1, s['load_frames'])).astype(int)
        loads[np.argmin(abs(loads-peak))] = peak; loads = np.unique(loads)
        increments = np.rint(np.linspace(0, n-1, s['incremental_intervals']+1)).astype(int)
        internal = np.arange(1, len(increments)-1)
        if len(internal): increments[internal[np.argmin(abs(increments[internal]-peak))]] = peak
        increments = np.unique(increments)
        normals = [nodal_normals(self.mesh['x0']+h['u'][i], self.mesh['conn']) for i in increments[:-1]]
        self.ref = DropReference(self.mesh, h, loads, increments, normals, [0,0,-self.cfg['drop']['gravity_mm_s2']])
        if any(METHODS[m].response == 'accumulate' for m in self.methods): self.ref.prepare_increments()
        write_json(self.out/'reference.json', dict(load_indices=loads.tolist(), load_times_s=h['time'][loads].tolist(),
                   incremental_indices=increments.tolist(), incremental_times_s=h['time'][increments].tolist(),
                   methods={m:asdict(METHODS[m]) for m in self.methods}))
        return metrics

    def evaluate(self, depths, methods=None, origin='pool'):
        methods = list(methods or self.methods); ident = design_id(depths)
        row = self.records.setdefault(ident, dict(id=ident, depths_mm=np.asarray(depths).tolist(), origin=origin, methods={}))
        mesh = make_mesh(self.cfg, depths)
        row['geometry'] = geometry_metrics(mesh, self.cfg['material']['density_tonne_mm3'], self.mass0, self.cfg['beads'])
        missing = [m for m in methods if m not in row['methods'] or
                   row['methods'][m].get('diagnostic_schema') != 2]
        if missing and row['geometry']['valid']:
            if self.ref is None: raise ValueError('baseline not prepared')
            result = self.ref.evaluate(mesh, nodal_mass(mesh, self.cfg['material']['density_tonne_mm3']), missing)
            row['methods'].update(result['methods']); row['elapsed_s'] = row.get('elapsed_s',0)+result['elapsed_s']
            write_json(self.cache_path, self.records)
        return row

    def search(self):
        if self.ref is None: baseline = self.baseline()
        else: baseline = json.loads((self.out/'baseline/metrics.json').read_text())
        b,s = self.cfg['beads'], self.cfg['sampling']; base = self.mesh['depths']
        pool = [base]
        for i in range(len(base)):
            for sign in [-1,1]:
                p = base.copy(); p[i] += sign*s['local_delta_mm']; pool.append(p)
        local_ids = [design_id(p) for p in pool[1:]]
        sobol = qmc.Sobol(len(base), scramble=True, seed=self.cfg['seed']).random_base2(s['sobol_power'])
        pool.extend(qmc.scale(sobol, [b['min_depth_mm']]*len(base), [b['max_depth_mm']]*len(base)))
        pool_ids=[]
        for i,p in enumerate(pool):
            self.progress('static', f'공통 후보 {i+1}/{len(pool)}', completed=i, total=len(pool))
            row=self.evaluate(p); pool_ids.append(row['id'])
        selections={}
        for method in self.methods:
            valid=[self.records[i] for i in pool_ids if self.records[i]['methods'].get(method,{}).get('status')=='completed']
            if not valid:
                selections[method]=dict(status='failed',error='no valid static evaluations'); continue
            best=min(valid,key=lambda r:r['methods'][method]['score_mm'])
            # Fixed 12-neighbour budget, evaluated about the initial pool winner.
            center=np.asarray(best['depths_mm']); refinement=[]
            for i in range(s['refinement_evaluations']):
                p=center.copy(); p[(i//2)%len(base)] += (-1 if i%2==0 else 1)*s['local_delta_mm']
                p=np.clip(p,b['min_depth_mm'],b['max_depth_mm'])
                self.progress('refine', f'{METHODS[method].code} 국부 탐색 {i+1}/{s["refinement_evaluations"]}')
                row=self.evaluate(p,[method],origin='refinement'); refinement.append(row['id'])
                if row['methods'].get(method,{}).get('status')=='completed' and row['methods'][method]['score_mm'] < best['methods'][method]['score_mm']: best=row
            selections[method]=dict(status='completed',id=best['id'],depths_mm=best['depths_mm'],
                                    predicted_mm=best['methods'][method]['score_mm'], refinement_ids=refinement)
        # Separate, independent pool, never used to select a design.
        holdout_power=max(s['sobol_power'],int(np.ceil(np.log2(max(1,s['holdout_count']))))+3)
        holdout=qmc.Sobol(len(base),scramble=True,seed=self.cfg['seed']+1).random_base2(holdout_power)
        holdout=qmc.scale(holdout,[b['min_depth_mm']]*len(base),[b['max_depth_mm']]*len(base))
        holdout_ids=[]
        for p in holdout:
            row=self.evaluate(p,origin='holdout')
            if row['geometry']['valid']: holdout_ids.append(row['id'])
            if len(holdout_ids)>=s['holdout_count']: break
        if len(holdout_ids)<s['holdout_count']:
            raise ValueError('not enough geometrically valid holdout designs in the deterministic sampling budget')
        legacy=[self.records[i] for i in pool_ids if self.records[i]['methods'].get('displacement',{}).get('status')=='completed']
        result=dict(selections=selections,pool_ids=pool_ids,local_ids=local_ids,holdout_ids=holdout_ids,
                    baseline_id=design_id(base), legacy_compliance_best_id=min(legacy,key=lambda r:r['methods']['displacement']['compliance_Nmm'])['id'] if legacy else None)
        write_json(self.out/'search.json',result)
        return result

    def validate(self):
        if self.ref is None: self.baseline()
        search=json.loads((self.out/'search.json').read_text())
        ids=list(dict.fromkeys([search['baseline_id']]+search['local_ids']+search['holdout_ids']+
                               [v['id'] for v in search['selections'].values() if v['status']=='completed']+
                               ([search['legacy_compliance_best_id']] if search['legacy_compliance_best_id'] else [])))
        actual={}; failures={}
        for ident in ids:
            row=self.records[ident]
            try:
                if ident==search['baseline_id']: metric=json.loads((self.out/'baseline/metrics.json').read_text())
                else: metric,_=self.drop(row['depths_mm'],f'drops/{ident}')
                actual[ident]=metric
            except Exception as exc:
                failures[ident]=f'{type(exc).__name__}: {exc}'
            write_json(self.out/'actual.json',dict(results=actual,failures=failures))
        base=actual[search['baseline_id']]; a=self.cfg['acceptance']; rows=[]
        for method,chosen in search['selections'].items():
            if chosen['status']!='completed': rows.append(dict(method=method,**chosen)); continue
            ident=chosen['id']; obs=actual.get(ident)
            if not obs: rows.append(dict(method=method,status='failed',error=failures.get(ident,'missing re-drop')));continue
            pairs=[(self.records[i]['methods'][method]['score_mm'],actual[i]['peak_rms_mm']) for i in search['holdout_ids']
                   if i in actual and actual[i]['quality_passed'] and self.records[i]['methods'].get(method,{}).get('status')=='completed']
            corr=float(spearmanr(np.asarray(pairs)[:,0],np.asarray(pairs)[:,1]).statistic) if len(pairs)>=3 else None
            if corr is not None and not np.isfinite(corr): corr=None
            refscore=self.records[search['baseline_id']]['methods'][method].get('score_mm')
            signs=[]
            for i in search['local_ids']:
                if i in actual and refscore is not None and self.records[i]['methods'].get(method,{}).get('status')=='completed':
                    signs.append(bool(np.sign(self.records[i]['methods'][method]['score_mm']-refscore)==np.sign(actual[i]['peak_rms_mm']-base['peak_rms_mm'])))
            improvement=1-obs['peak_rms_mm']/base['peak_rms_mm']
            plastic_ok=obs['plastic_p95'] <= base['plastic_p95']*a['max_plastic_p95_ratio']+1e-12
            rows.append(dict(method=method,code=METHODS[method].code,status='completed',id=ident,depths_mm=chosen['depths_mm'],
                             baseline_static_mm=refscore,predicted_mm=chosen['predicted_mm'],actual_mm=obs['peak_rms_mm'],
                             improvement_fraction=improvement,plastic_p95=obs['plastic_p95'],plastic_passed=plastic_ok,
                             mass_ratio=obs['geometry']['mass_ratio'],quality_passed=obs['quality_passed'],
                             accepted=bool(improvement>=a['min_improvement_fraction'] and plastic_ok and obs['quality_passed'] and obs['geometry']['valid']),
                             holdout_spearman=corr,holdout_pairs=len(pairs),local_direction_agreement=float(np.mean(signs)) if signs else None))
        valid_actual=[(ident,v) for ident,v in actual.items() if v['quality_passed']]
        best_actual=min(valid_actual,key=lambda item:item[1]['peak_rms_mm'])[0]
        # Re-run every selected design and the observed control winner in all attitudes.
        variation_results={}
        selected_ids=list(dict.fromkeys([search['baseline_id']]+[v['id'] for v in search['selections'].values() if v['status']=='completed']))
        variation_ids=list(dict.fromkeys(selected_ids+[best_actual]))
        for case in self.cfg['validation_cases'][1:]:
            variation_results[case['name']]={}
            for ident in variation_ids:
                try:
                    obs,_=self.drop(self.records[ident]['depths_mm'],f'variations/{case["name"]}/{ident}',case)
                    variation_results[case['name']][ident]=obs
                except Exception as exc: variation_results[case['name']][ident]=dict(error=str(exc))
            write_json(self.out/'variations.json',variation_results)
        selected_actual=[(i,actual[i]) for i in selected_ids if i in actual and actual[i]['quality_passed']]
        best_selected=min(selected_actual,key=lambda item:item[1]['peak_rms_mm'])[0]
        fine={}
        for ident in dict.fromkeys([search['baseline_id'],best_selected,best_actual]):
            try:
                obs,_=self.drop(self.records[ident]['depths_mm'],f'fine/{ident}',multiplier=self.cfg['refinement_mesh_multiplier'])
                fine[ident]=obs
            except Exception as exc: fine[ident]=dict(error=str(exc))
        result=dict(schema='corner-drop/result/2',baseline=base,methods=rows,dynamic_failures=failures,
                    fine=fine,fine_selected_id=best_selected,best_observed_id=best_actual,variations=variation_results,
                    actual_drops=len(actual),source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                    elapsed_s=time.time()-self.started,scope='one outer cycle; not a converged/global optimum')
        write_json(self.out/'result.json',result)
        with (self.out/'comparison.csv').open('w',newline='') as f:
            fields=['code','method','status','predicted_mm','actual_mm','improvement_fraction','plastic_p95','mass_ratio','accepted','holdout_spearman','local_direction_agreement']
            writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
        self.progress('completed','동해석 재검증 완료', actual_drops=len(actual))
        write_json(self.out/'progress.json',dict(status='completed',stage='completed',message='결과 생성 완료',updated_at=time.time()))
        return result
