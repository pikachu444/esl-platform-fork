"""Pure, declared ESL definitions for shape-perturbation prediction (no IO/DOE)."""
from __future__ import annotations
from dataclasses import dataclass
import time
import numpy as np
from .drop_surrogates import make_shell,inertia_relief,resultants
from .kabsch import remove_linear_rigid

@dataclass(frozen=True)
class Plan:
    label:str
    family:str
    source:str
    balance:bool
    extra_dynamic_runs:int

PLANS={
    'frozen':Plan('고정 ESL','ESL 대조군','frozen',False,0),
    'balanced':Plan('고정 ESL + 평형 보정','평형 진단','frozen',True,0),
    'incremental':Plan('증분 형상 ESL','DiESL 형상 확장','incremental',False,0),
    'first_order_load':Plan('1차 하중 ESL','F-ESL형','first_order',False,12),
    'first_order_balanced':Plan('1차 하중 ESL + 평형 보정','F-ESL형 안정화','first_order',True,12),
    'response_taylor':Plan('동해석 응답 1차 근사','직접 응답 대조군','response',False,12),
}

def project_fields(x,fields):
    return np.array([remove_linear_rigid(x,u)[0] for u in fields])

def relative_error(a,b):
    return float(np.linalg.norm(np.asarray(a)-b)/max(np.linalg.norm(b),1e-15))

class Reference:
    def __init__(self,mesh,u,calibration,fd_step,supports):
        self.mesh=mesh;self.u=np.asarray(u);self.supports=supports;self.step=fd_step
        self.model=make_shell(mesh)
        t=time.monotonic()
        self.f0=np.array([self.model.condensed_forces(x) for x in self.u])
        self.base_preparation_s=time.monotonic()-t
        self.gradient_u=[];self.gradient_f=[];t=time.monotonic()
        for minus_mesh,minus_u,plus_mesh,plus_u in calibration:
            self.gradient_u.append((plus_u-minus_u)/(2*fd_step))
            mm=make_shell(minus_mesh);mp=make_shell(plus_mesh)
            fm=np.array([mm.condensed_forces(x) for x in minus_u])
            fp=np.array([mp.condensed_forces(x) for x in plus_u])
            self.gradient_f.append((fp-fm)/(2*fd_step))
        self.gradient_u=np.asarray(self.gradient_u);self.gradient_f=np.asarray(self.gradient_f)
        self.gradient_preparation_s=time.monotonic()-t
        self.increments=[];self.increment_preparation_s=0.

    def prepare_increments(self):
        if self.increments:return
        t=time.monotonic()
        for i in range(len(self.u)-1):
            x=self.mesh['x0']+self.u[i]
            model=make_shell(self.mesh,x)
            du=self.u[i+1]-self.u[i]
            self.increments.append(dict(x=x,du=du,force=model.condensed_forces(du)))
        self.increment_preparation_s=time.monotonic()-t

    def predict(self,mesh,delta,mass,methods):
        start=time.monotonic();model=make_shell(mesh);fields={};records={};solvers={}
        model_s=time.monotonic()-start
        def solve(which):
            if which not in solvers:solvers[which]=model.factorize(self.supports[which])
            return solvers[which]
        for name in methods:
            begin=time.monotonic();plan=PLANS[name]
            try:
                if plan.source=='response':
                    u=project_fields(mesh['x0'],self.u+np.einsum('j,jtnc->tnc',delta,self.gradient_u))
                    alt=u.copy();details=[]
                elif plan.source=='incremental':
                    u,alt,details=self.incremental(mesh)
                else:
                    loads=self.f0 if plan.source=='frozen' else self.f0+np.einsum('j,jtnc->tnc',delta,self.gradient_f)
                    pred=[];other=[];details=[]
                    for raw in loads:
                        f,correction=inertia_relief(mesh['x0'],raw,mass) if plan.balance else (raw,np.zeros_like(raw))
                        full,reaction=solve('primary').solve(f)
                        afull,_=solve('alternate').solve(f)
                        pred.append(full[:,:3]);other.append(afull[:,:3])
                        details.append(dict(raw=resultants(mesh['x0'],raw),applied=resultants(mesh['x0'],f),
                            reactions=resultants(mesh['x0'],reaction),
                            max_reaction_N=float(np.linalg.norm(reaction,axis=1).max()),
                            relative_reaction=float(np.linalg.norm(reaction)/max(np.linalg.norm(f),1e-20)),
                            relative_balance_correction=float(np.linalg.norm(correction)/max(np.linalg.norm(raw),1e-20))))
                    u=project_fields(mesh['x0'],np.asarray(pred));alt=project_fields(mesh['x0'],np.asarray(other))
                fields[name]=u
                records[name]=dict(status='completed',family=plan.family,label=plan.label,
                    elapsed_s=time.monotonic()-begin,assembly_s=model_s,
                    gauge_relative_l2=relative_error(alt,u),details=details,
                    extra_calibration_drops=plan.extra_dynamic_runs)
            except Exception as exc:
                records[name]=dict(status='failed',error=f'{type(exc).__name__}: {exc}',elapsed_s=time.monotonic()-begin)
        return fields,records

    def incremental(self,mesh):
        self.prepare_increments()
        dx=mesh['x0']-self.mesh['x0'];total=self.u[0].copy();alt_total=total.copy()
        pred=[total.copy()];alt_pred=[total.copy()];details=[]
        for item in self.increments:
            x=item['x']+dx;model=make_shell(mesh,x)
            full,reaction=model.factorize(self.supports['primary']).solve(item['force'])
            afull,_=model.factorize(self.supports['alternate']).solve(item['force'])
            # Align rigid gauge components only. The reference elastic increment is not added.
            total+=item['du']+remove_linear_rigid(x,full[:,:3]-item['du'])[0]
            alt_total+=item['du']+remove_linear_rigid(x,afull[:,:3]-item['du'])[0]
            pred.append(total.copy());alt_pred.append(alt_total.copy())
            details.append(dict(applied=resultants(x,item['force']),reactions=resultants(x,reaction),
                max_reaction_N=float(np.linalg.norm(reaction,axis=1).max()),
                relative_reaction=float(np.linalg.norm(reaction)/max(np.linalg.norm(item['force']),1e-20))))
        return project_fields(mesh['x0'],np.asarray(pred)),project_fields(mesh['x0'],np.asarray(alt_pred)),details

