"""Elastic, fixed-geometry methodology validation. No design search or plastic gate."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib,json,os,re,subprocess,time
from pathlib import Path
import numpy as np
from esl.mech.kabsch import remove_rigid
from .corner_model import make_mesh,nodal_mass
from .radioss_runner import write_deck,run_solver,executable_provenance
from .fields import read_vtk,history_csv,quality_metrics

def read(p):return json.loads(Path(p).read_text())
def write(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temp.replace(p)
def load(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in z.files}
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def extract_elastic(path,solver,cfg):
    mesh=load(path/'input_mesh.npz');frames=sorted(path.glob('cornerA*'),key=lambda p:int(p.name[7:]))
    keys=['time','x','u','rotation','velocity','acceleration','contact','internal','erosion','stress_upper','stress_lower']
    data={k:[] for k in keys};field_names=None
    for frame in frames:
        text=subprocess.run([str(solver/'exec/anim_to_vtk_linux64_gf'),str(frame)],check=True,capture_output=True,text=True).stdout
        raw=read_vtk(text);ns=raw['point']['NODE_ID'].astype(int);es=raw['cell']['ELEMENT_ID'].astype(int)
        ni={n:i for i,n in enumerate(ns)};ei={n:i for i,n in enumerate(es) if raw['cell']['PART_ID'][i]==1}
        ix=np.array([ni[n] for n in mesh['node_id']]);ex=np.array([ei[n] for n in mesh['elem_id']])
        x=raw['x'][ix];u,R,_,_=remove_rigid(mesh['x0'],x-mesh['x0'])
        for k,v in [('time',raw['time']),('x',x),('u',u),('rotation',R)]:data[k].append(v)
        for k,key in [('velocity','Velocity'),('acceleration','Acceleration'),('contact','Reaction_Forces'),('internal','Internal_Forces')]:
            data[k].append(raw['point'][key][ix])
        for k,key in [('erosion','EROSION_STATUS'),('stress_upper','2DELEM_Stress_(upper)'),('stress_lower','2DELEM_Stress_(lower)')]:
            data[k].append(raw['cell'][key][ex])
        if field_names is None:field_names=dict(point=list(raw['point']),cell=list(raw['cell']))
    arrays={k:np.asarray(v) for k,v in data.items()};arrays['mass']=nodal_mass(mesh,cfg['material']['density_tonne_mm3'])
    gh=history_csv(path,solver)
    if not all(np.all(np.isfinite(v)) for v in arrays.values()):raise ValueError('nonfinite native field')
    np.savez_compressed(path/'history.npz',**arrays);np.savez_compressed(path/'global_history.npz',**gh)
    write(path/'field_provenance.json',dict(material='LAW1 linear elastic',plastic_fields_requested=False,
        fields=field_names,frames=len(frames),coordinate_precision='float32 native animation',
        units=dict(length='mm',time='s',mass='tonne',force='N',stress='MPa')))
    return arrays,gh

def dynamic_metrics(arrays,gh,cfg):
    norm=np.linalg.norm(arrays['u'],axis=2);rms=np.sqrt(np.mean(norm**2,axis=1))
    energy=gh['KINETIC ENERGY']+gh['INTERNAL ENERGY']+gh['ROTATION ENERGY']
    residual=energy-gh['KINETIC ENERGY'][0]-gh['EXTERNAL WORK']
    quality=quality_metrics(arrays,gh,cfg)
    return dict(peak_rms_mm=float(rms.max()),peak_rms_time_s=float(arrays['time'][rms.argmax()]),
        max_node_deflection_mm=float(norm.max()),rms_history_mm=rms.tolist(),frame_times_s=arrays['time'].tolist(),
        energy_balance_fraction=float(np.abs(residual).max()/gh['KINETIC ENERGY'][0]),
        added_mass_fraction=float(gh['ADDED MASS'].max()/gh['MASS'][0]),quality=quality)

def run_dynamic(out,solver,cfg,case,multiplier=1):
    label=case['id'] if multiplier==1 else case['id']+'_fine'
    path=out/'runs'/label;signature=dict(config=cfg,case=case,multiplier=multiplier,schema=1)
    marker=path/'complete.json'
    if marker.exists():
        old=read(marker)
        if old['signature']!=signature:raise ValueError('incompatible cached run: '+label)
        return read(path/'metrics.json')
    if path.exists() and any(path.iterdir()):
        # Keep interrupted native output intact, then start in a fresh run directory.
        # The study-level flock prevents a second active worker in this output root.
        archive=out/'interrupted'/f'{time.time_ns()}_{label}'
        archive.parent.mkdir(parents=True,exist_ok=True);path.rename(archive)
        print(json.dumps(dict(stage='preserved_interrupted_attempt',case=label,archive=str(archive))),flush=True)
    mesh=make_mesh(cfg,case['depths_mm'],multiplier)
    write(out/'progress.json',dict(status='running',stage='dynamic',case=label,updated_at=time.time()))
    print(json.dumps(dict(stage='dynamic',case=label)),flush=True);start=time.monotonic()
    write_deck(path,mesh,cfg);execution=run_solver(path,solver,cfg)
    if 'NORMAL TERMINATION' not in (path/'engine.log').read_text():raise ValueError('abnormal native termination')
    arrays,gh=extract_elastic(path,solver,cfg);metrics=dynamic_metrics(arrays,gh,cfg)
    q=metrics['quality'];metrics['native_valid']=bool(arrays['time'][-1]>=cfg['drop']['end_time_s'] and
        q['instantaneous_force_residual_fraction']<1e-3 and q['momentum_residual_fraction']<.01 and
        q['minimum_active_status']>=1 and metrics['added_mass_fraction']<1e-8)
    metrics.update(elapsed_s=time.monotonic()-start,execution=execution,role=case['role'],
        depths_mm=case['depths_mm'],multiplier=multiplier)
    write(path/'metrics.json',metrics)
    write(marker,dict(signature=signature,starter_sha256=digest(path/'corner_0000.rad'),
        engine_sha256=digest(path/'corner_0001.rad'),native_fields_sha256=digest(path/'history.npz')))
    print(json.dumps(dict(stage='dynamic_complete',case=label,rms=metrics['peak_rms_mm'],
        valid=metrics['native_valid'],seconds=metrics['elapsed_s'])),flush=True)
    return metrics

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['baseline','dynamic','evaluate','all'])
    ap.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[2]/'config/shape_method_validation.json')
    ap.add_argument('--solver',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--method',action='append');ap.add_argument('--case',action='append')
    args=ap.parse_args();cfg=read(args.config);out=args.out.resolve();solver=args.solver.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=dict(config=cfg,solver=executable_provenance(solver),study='fixed geometry method selection')
    import fcntl
    execution_lock=(out/'.study.lock').open('a')
    try:fcntl.flock(execution_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise ValueError('another study process is active in this output folder')
    if (out/'manifest.json').exists() and read(out/'manifest.json')!=manifest:raise ValueError('incompatible manifest')
    write(out/'manifest.json',manifest)
    if args.stage in ['baseline','dynamic','all']:
        gradient_methods={'first_order_load','first_order_balanced','response_taylor'}
        needs_gradient=bool(gradient_methods.intersection(args.method or cfg['study']['methods']))
        cases=[c for c in cfg['cases'] if (args.stage!='baseline' or c['role']=='baseline') and
               (not args.case or c['id'] in args.case) and
               (needs_gradient or c['role'] not in ['calibration','sensitivity_check'])]
        for case in cases:run_dynamic(out,solver,cfg,case)
        if args.stage in ['dynamic','all'] and not args.case:
            for ident in cfg['mesh_check_cases']:
                case=next(x for x in cfg['cases'] if x['id']==ident);run_dynamic(out,solver,cfg,case,2)
    if args.stage in ['evaluate','all']:
        from .shape_methods_evaluate import evaluate
        evaluate(out,cfg,args.method)
    write(out/'progress.json',dict(status='completed',stage=args.stage,updated_at=time.time()))

if __name__=='__main__':main()
