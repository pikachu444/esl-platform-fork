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
    control: bool = False

PLANS={
    'frozen':Plan('고정 ESL','ESL 대조군','frozen',False,0),
    'balanced':Plan('고정 ESL + 평형 보정','평형 진단','frozen',True,0),
    'incremental':Plan('증분 형상 ESL','DiESL 형상 확장','incremental',False,0),
    'incremental_balanced': Plan('증분 형상 ESL + 평형 보정', 'DiESL 형상 확장', 'incremental', True, 0),
    'first_order_load':Plan('1차 하중 ESL','F-ESL형','first_order',False,12),
    'first_order_balanced':Plan('1차 하중 ESL + 평형 보정','F-ESL형 안정화','first_order',True,12),
    'response_taylor':Plan('동해석 응답 1차 근사','직접 응답 대조군','response',False,12,True),
    'snapshot_esl': Plan('변형 기저 축소 ESL', '실험적 ESL', 'snapshot', True, 0),
    'reference_replay': Plan('기준 동해석 변위 재사용', '변위 대조군', 'replay', False, 0, True),
}

def project_fields(x,fields):
    return np.array([remove_linear_rigid(x,u)[0] for u in fields])

def relative_error(a,b):
    return float(np.linalg.norm(np.asarray(a)-b)/max(np.linalg.norm(b),1e-15))

class Reference:
    def __init__(self,mesh,u,calibration,fd_step,supports, basis_energy_fraction=0.999):
        self.mesh=mesh;self.u=np.asarray(u);self.supports=supports;self.step=fd_step
        if not 0 < basis_energy_fraction <= 1:
            raise ValueError('basis_energy_fraction must be in (0, 1]')
        self.basis_energy_fraction = basis_energy_fraction
        self.snapshot_modes = None
        self.snapshot_preparation_s = 0.
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
                elif plan.source == 'replay':
                    u = project_fields(mesh['x0'], self.u)
                    alt, details = u, []
                elif plan.source == 'snapshot':
                    u, diagnostics = self.predict_in_snapshot_space(model, mass)
                    alt, details = u, [diagnostics]
                elif plan.source=='incremental':
                    u,alt,details=self.incremental(mesh, mass if plan.balance else None)
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

    def predict_in_snapshot_space(self, model, mass):
        """Correct the replayed field in a basis learned from baseline snapshots only."""
        if self.snapshot_modes is None:
            start = time.monotonic()
            _, singular_values, directions = np.linalg.svd(
                self.u.reshape(len(self.u), -1), full_matrices=False)
            energy = np.cumsum(singular_values**2)
            count = 0
            if energy[-1] > 0:
                numerical_rank = np.count_nonzero(singular_values > singular_values[0]*1e-12)
                count = min(numerical_rank, np.searchsorted(energy, self.basis_energy_fraction*energy[-1]) + 1)
            self.snapshot_modes = directions[:count].reshape(count, *model.x0.shape)
            self.snapshot_preparation_s = time.monotonic()-start

        replay = project_fields(model.x0, self.u)
        if len(self.snapshot_modes) == 0:
            return replay, dict(rank=0, gauge='rigid modes removed, no point supports')
        modes = project_fields(model.x0, self.snapshot_modes).reshape(len(self.snapshot_modes), -1)
        basis, scales, _ = np.linalg.svd(modes.T, full_matrices=False)
        basis = basis[:, scales > scales[0]*1e-12]
        if basis.size == 0:
            raise ValueError('snapshot basis contains no deformation for this mesh')
        stiffness_times_basis = np.column_stack([
            model.condensed_forces(mode.reshape(model.x0.shape)).ravel() for mode in basis.T
        ])
        stiffness = basis.T @ stiffness_times_basis
        stiffness = (stiffness + stiffness.T)*0.5
        chol = np.linalg.cholesky(stiffness)
        residual = np.array([
            (inertia_relief(model.x0, force, mass)[0] - model.condensed_forces(field)).ravel()
            for force, field in zip(self.f0, replay, strict=True)
        ]).T
        projected = basis.T @ residual
        coefficients = np.linalg.solve(chol.T, np.linalg.solve(chol, projected))
        correction = (basis @ coefficients).T.reshape(replay.shape)
        remaining = residual - stiffness_times_basis @ coefficients
        return replay+correction, dict(
            rank=int(basis.shape[1]), basis_energy_fraction=self.basis_energy_fraction,
            reduced_condition=float(np.linalg.cond(stiffness)),
            residual_outside_basis_fraction=float(np.linalg.norm(remaining)/max(np.linalg.norm(residual), 1e-20)),
            gauge='rigid modes removed, no point supports',
        )

    def incremental(self,mesh, mass=None):
        self.prepare_increments()
        dx=mesh['x0']-self.mesh['x0'];total=self.u[0].copy();alt_total=total.copy()
        pred=[total.copy()];alt_pred=[total.copy()];details=[]
        for item in self.increments:
            x=item['x']+dx;model=make_shell(mesh,x)
            raw = item['force']
            force = raw if mass is None else inertia_relief(x, raw, mass)[0]
            full,reaction=model.factorize(self.supports['primary']).solve(force)
            afull,_=model.factorize(self.supports['alternate']).solve(force)
            # Align rigid gauge components only. The reference elastic increment is not added.
            total+=item['du']+remove_linear_rigid(x,full[:,:3]-item['du'])[0]
            alt_total+=item['du']+remove_linear_rigid(x,afull[:,:3]-item['du'])[0]
            pred.append(total.copy());alt_pred.append(alt_total.copy())
            details.append(dict(raw=resultants(x,raw),applied=resultants(x,force),reactions=resultants(x,reaction),
                max_reaction_N=float(np.linalg.norm(reaction,axis=1).max()),
                relative_reaction=float(np.linalg.norm(reaction)/max(np.linalg.norm(force),1e-20))))
        return project_fields(mesh['x0'],np.asarray(pred)),project_fields(mesh['x0'],np.asarray(alt_pred)),details

