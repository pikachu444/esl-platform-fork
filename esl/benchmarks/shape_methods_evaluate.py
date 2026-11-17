"""Blind shape-method scoring. No optimizer and no selection of a bead design."""
from __future__ import annotations
from dataclasses import asdict
import time
import numpy as np
from esl.mech.shape_methods import Reference,PLANS,relative_error,project_fields
from .shape_methods import read,write,load
from .corner_model import nodal_mass

def resample(h,times):
    # Linear resampling aligns actual output times; the pictures use native frames separately.
    a=h['u'].reshape(len(h['time']),-1)
    return np.column_stack([np.interp(times,h['time'],a[:,j]) for j in range(a.shape[1])]).reshape(len(times),*h['u'].shape[1:])
def rms(u):return np.sqrt(np.mean(np.sum(u*u,axis=2),axis=1))

def evaluate(out,cfg,methods=None):
    start=time.monotonic();methods=list(methods or cfg['study']['methods'])
    (out/'predictions').mkdir(exist_ok=True)
    if any(m not in PLANS for m in methods):raise ValueError('unknown method')
    basepath=out/'runs/baseline';mesh=load(basepath/'input_mesh.npz');hist=load(basepath/'history.npz')
    tm=np.linspace(0,cfg['drop']['end_time_s'],cfg['study']['load_intervals']+1)
    tm=np.unique(np.r_[tm,float(hist['time'][rms(hist['u']).argmax()])]);u0=resample(hist,tm)
    baseline=read(basepath/'metrics.json');roles={x['id']:x for x in cfg['cases']}
    supports={k:[(int(n)-1,d) for n,d in v] for k,v in cfg['study']['static_gauge'].items()}
    calibration=[]
    for j in range(6):
        minus=out/'runs'/f'cal_b{j+1}_minus';plus=out/'runs'/f'cal_b{j+1}_plus'
        calibration.append((load(minus/'input_mesh.npz'),resample(load(minus/'history.npz'),tm),
                            load(plus/'input_mesh.npz'),resample(load(plus/'history.npz'),tm)))
    ref=Reference(mesh,u0,calibration,cfg['study']['fd_step_mm'],supports)
    write(out/'method_definitions.json',{k:asdict(v) for k,v in PLANS.items()})
    write(out/'evaluation_times.json',dict(times_s=tm.tolist(),resampling='linear to common physical times',
        source_frames=len(hist['time']),fields='rigid-removed displacement',static_gauge=cfg['study']['static_gauge']))
    calibration_cost=sum(read(out/'runs'/c['id']/'metrics.json')['elapsed_s'] for c in cfg['cases'] if c['role']=='calibration')
    results=dict(scope='fixed bead shape perturbation method selection; elastic material',
        methods=methods,field_thresholds=cfg['study']['thresholds'],calibration_dynamic_s=calibration_cost,
        baseline_dynamic_s=baseline['elapsed_s'],baseline={},cases=[],mesh_checks={},
        preparation=dict(base_s=ref.base_preparation_s,first_order_s=ref.gradient_preparation_s))
    for case in [x for x in cfg['cases'] if x['role'] in ['baseline','validation','sensitivity_check']]:
        label=case['id'];path=out/'runs'/label;cm=load(path/'input_mesh.npz');ch=load(path/'history.npz')
        measured=project_fields(cm['x0'],resample(ch,tm));delta=np.array(case['depths_mm'])-mesh['depths']
        mass=nodal_mass(cm,cfg['material']['density_tonne_mm3'])
        write(out/'progress.json',dict(status='running',stage='method_evaluation',case=label,updated_at=time.time()))
        print('EVALUATING '+label,flush=True)
        fields,rec=ref.predict(cm,delta,mass,methods)
        true_rms=rms(measured);true_peak=float(true_rms.max())
        metrics=read(path/'metrics.json')
        for name,pred in fields.items():
            r=rec[name];pred_rms=rms(pred);field_error=relative_error(pred,measured)
            pe=abs(float(pred_rms.max())-true_peak)/max(true_peak,1e-15)
            r.update(field_relative_l2=field_error,peak_rms_relative_error=pe,
                predicted_peak_rms_mm=float(pred_rms.max()),actual_common_peak_rms_mm=true_peak,
                actual_dense_peak_rms_mm=metrics['peak_rms_mm'],
                dense_time_sampling_error=abs(metrics['peak_rms_mm']-true_peak)/metrics['peak_rms_mm'],
                predicted_delta_rms_mm=float(pred_rms.max()-rms(u0).max()),
                actual_delta_rms_mm=float(true_peak-rms(u0).max()),
                vector_mac=float(np.sum(pred*measured)**2/max(np.sum(pred*pred)*np.sum(measured*measured),1e-30)))
            th=cfg['study']['thresholds']
            r['passes_case']=bool(field_error<=th['field_relative_l2'] and pe<=th['peak_rms_relative_error'] and
                r['gauge_relative_l2']<=th['gauge_relative_l2'] and metrics['native_valid'])
        np.savez_compressed(out/'predictions'/f'{label}.npz',time=tm,actual=measured,**fields)
        if label=='baseline':results['baseline']=rec
        else:results['cases'].append(dict(id=label,role=case['role'],delta_mm=delta.tolist(),
            max_change_mm=float(np.abs(delta).max()),native_valid=metrics['native_valid'],methods=rec))
        results['preparation']['incremental_s']=ref.increment_preparation_s
        write(out/'method_results.json',results)
    # Independent finite-difference step check for bead 5. These runs were never calibration input.
    lo=resample(load(out/'runs/check_b5_minus/history.npz'),tm)
    hi=resample(load(out/'runs/check_b5_plus/history.npz'),tm)
    fine_g=(hi-lo)/.05
    results['fd_step_check']=dict(bead=5,calibration_h_mm=.05,check_h_mm=.025,
        response_gradient_relative_difference=relative_error(ref.gradient_u[4],fine_g))
    for name in cfg['mesh_check_cases']:
        coarse=read(out/'runs'/name/'metrics.json');fine=read(out/'runs'/(name+'_fine')/'metrics.json')
        results['mesh_checks'][name]=dict(coarse_rms_mm=coarse['peak_rms_mm'],fine_rms_mm=fine['peak_rms_mm'],
            relative_difference=abs(coarse['peak_rms_mm']-fine['peak_rms_mm'])/fine['peak_rms_mm'],
            fine_native_valid=fine['native_valid'])
    summaries={}
    for name in methods:
        regions={}
        for region,limit in [('small',cfg['study']['small_region_max_change_mm']),('extended',.5)]:
            rows=[x['methods'][name] for x in results['cases'] if x['role']=='validation' and x['max_change_mm']<=limit+1e-10]
            good=[x for x in rows if x['status']=='completed']
            meaningful=[x for x in good if abs(x['actual_delta_rms_mm'])>5e-5*baseline['peak_rms_mm']]
            signs=sum(np.sign(x['actual_delta_rms_mm'])==np.sign(x['predicted_delta_rms_mm']) for x in meaningful)
            agreement=signs/len(meaningful) if meaningful else None
            regions[region]=dict(tests=len(rows),completed=len(good),passed=sum(x.get('passes_case',False) for x in rows),
                worst_field_l2=max((x['field_relative_l2'] for x in good),default=None),
                worst_peak_rms_error=max((x['peak_rms_relative_error'] for x in good),default=None),
                worst_gauge_error=max((x['gauge_relative_l2'] for x in good),default=None),
                direction_agreement=agreement,direction_tests=len(meaningful),
                recommended_in_region=bool(len(good)==len(rows) and all(x['passes_case'] for x in rows) and
                    agreement is not None and agreement>=cfg['study']['thresholds']['direction_agreement'] and
                    results['baseline'][name]['field_relative_l2']<=cfg['study']['thresholds']['roundtrip_relative_l2']),
                median_prediction_s=float(np.median([x['elapsed_s'] for x in good])) if good else None)
        summaries[name]=dict(label=PLANS[name].label,family=PLANS[name].family,regions=regions,
            extra_calibration_drops=PLANS[name].extra_dynamic_runs)
    results['summary']=summaries;results['elapsed_evaluation_s']=time.monotonic()-start
    write(out/'method_results.json',results)
    print('METHOD_SUMMARY '+str({k:v['regions']['small'] for k,v in summaries.items()}),flush=True)

