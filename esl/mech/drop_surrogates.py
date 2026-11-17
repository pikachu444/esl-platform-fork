"""Pure mechanics for the corner-drop experiment (no files or configuration parsing).

The plans describe deliberate approximations, not interchangeable ESL formulas.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from .kabsch import remove_linear_rigid
from .shell import ShellModel
from .supports import pca_corners, pick_321


@dataclass(frozen=True)
class MethodPlan:
    code: str
    title: str
    source: str
    balance: bool
    response: str
    experimental: bool


METHODS = {
    'displacement': MethodPlan('D0', '기존 변위 ESL', 'displacement', False, 'solve', False),
    'balanced_displacement': MethodPlan('D1', '평형 보정 변위 ESL', 'displacement', True, 'solve', True),
    'physical_acceleration': MethodPlan('P0', '접촉력·전체 가속도', 'acceleration', True, 'solve', True),
    'contact_inertia_relief': MethodPlan('P1', '접촉력·관성완화', 'contact', True, 'solve', True),
    'incremental_geometry': MethodPlan('I0', '증분 기준 형상', 'incremental', False, 'accumulate', True),
    'ritz_reference': MethodPlan('R0', '기준 변형 Ritz', 'displacement', False, 'ritz', True),
}


def inertia_relief(x, f, mass):
    """Mass-weighted rigid acceleration projection; also removes total moment."""
    x, f, mass = np.asarray(x, float), np.asarray(f, float), np.asarray(mass, float)
    if x.shape != f.shape or x.shape != (len(mass), 3) or np.any(mass <= 0):
        raise ValueError('inertia relief requires matching (N,3) coordinates/forces and positive masses')
    r = x-np.average(x, axis=0, weights=mass)
    inertia = np.eye(3)*np.sum(mass*np.sum(r*r, axis=1))-(r.T*mass)@r
    a = f.sum(axis=0)/mass.sum()
    alpha = np.linalg.solve(inertia, np.cross(r, f).sum(axis=0))
    correction = mass[:, None]*(a+np.cross(alpha, r))
    return f-correction, correction


def resultants(x, f):
    r = np.asarray(x)-np.mean(x, axis=0)
    scale = max(float(np.linalg.norm(f, axis=1).sum()), 1e-30)
    length = max(float(np.linalg.norm(r, axis=1).max()), 1e-30)
    force = np.asarray(f).sum(axis=0); moment = np.cross(r, f).sum(axis=0)
    return dict(force_N=force.tolist(), moment_Nmm=moment.tolist(),
                force_fraction=float(np.linalg.norm(force)/scale),
                moment_fraction=float(np.linalg.norm(moment)/(scale*length)))


def make_shell(mesh, x=None):
    return ShellModel(mesh['x0'] if x is None else x, mesh['conn'], mesh['elem_type'],
                      mesh['thickness'], mesh['E'], mesh['nu'], backend='superlu')


def gauge_solve(model):
    return model.factorize(pick_321(model.x0, pca_corners(model.x0)['idx']))


def shape_score(x, u):
    elastic = remove_linear_rigid(x, u)[0]
    n = np.linalg.norm(elastic, axis=1)
    return float(np.sqrt(np.mean(n*n))), float(n.max()), elastic


class DropReference:
    """Frozen, actually measured baseline history and reference stiffness operators."""

    def __init__(self, mesh, history, load_indices, increment_indices, normals, gravity):
        self.mesh, self.history = mesh, history
        self.load_indices = np.asarray(load_indices, int)
        self.increment_indices = np.asarray(increment_indices, int)
        self.u = history['u'][self.load_indices]
        self.model = make_shell(mesh)
        self.loads = np.asarray([self.model.condensed_forces(u) for u in self.u])
        self.energy = np.einsum('tnj,tnj->t', self.u, self.loads)
        self.gravity = np.asarray(gravity, float)
        self.normals = normals
        self.increments = []

    def prepare_increments(self):
        if self.increments:
            return
        for start, end, normal in zip(self.increment_indices[:-1], self.increment_indices[1:], self.normals):
            x = self.mesh['x0']+self.history['u'][start]
            du = self.history['u'][end]-self.history['u'][start]
            model = make_shell(self.mesh, x)
            self.increments.append(dict(x=x, du=du, normal=normal, force=model.condensed_forces(du),
                                        end=int(end)))

    def force(self, source, i, mass):
        if source == 'displacement':
            return self.loads[i].copy()
        j = self.load_indices[i]; h = self.history
        world = h['contact'][j]+mass[:, None]*self.gravity
        if source == 'acceleration':
            world = world-mass[:, None]*h['acceleration'][j]
        elif source != 'contact':
            raise ValueError(f'unknown force source {source}')
        return world@h['rotation'][j]

    def evaluate(self, mesh, mass, method_ids):
        """Same reference/candidate operators for every plan; retain each failed method."""
        start = time.monotonic(); model = make_shell(mesh)
        solve = None
        results = {}
        for method in method_ids:
            plan = METHODS[method]; begin = time.monotonic()
            try:
                if plan.response == 'accumulate':
                    record = self._incremental(mesh)
                else:
                    if solve is None:
                        solve = gauge_solve(model)
                    record = self._static(mesh, mass, model, solve, plan)
                record.update(status='completed', elapsed_s=time.monotonic()-begin, diagnostic_schema=2)
            except Exception as exc:
                record = dict(status='failed', error=f'{type(exc).__name__}: {exc}',
                              elapsed_s=time.monotonic()-begin)
            results[method] = record
        return dict(methods=results, elapsed_s=time.monotonic()-start)

    def _static(self, mesh, mass, model, solve, plan):
        rows, responses = [], []
        for i, ref_u in enumerate(self.u):
            raw = self.force(plan.source, i, mass)
            f, correction = inertia_relief(mesh['x0'], raw, mass) if plan.balance else (raw, np.zeros_like(raw))
            full, reactions = solve.solve(f)
            rms, max_def, elastic = shape_score(mesh['x0'], full[:, :3])
            replay_rms = rms; rho = None
            if plan.response == 'ritz':
                energy = float(np.sum(ref_u*model.condensed_forces(ref_u)))
                rho = energy/max(float(self.energy[i]), 1e-30)
                if rho <= 0 or not np.isfinite(rho):
                    raise ValueError('nonpositive Ritz energy ratio')
                rms, max_def, elastic = shape_score(mesh['x0'], ref_u/rho)
            responses.append(elastic)
            nodes = np.flatnonzero(np.linalg.norm(reactions, axis=1) > 0)
            rows.append(dict(frame=int(self.load_indices[i]), rms_mm=rms, max_def_mm=max_def,
                             compliance_Nmm=float(np.sum(f*full[:, :3])), force_replay_rms_mm=replay_rms,
                             energy_ratio=rho, raw=resultants(mesh['x0'], raw),
                             applied=resultants(mesh['x0'], f), reactions=resultants(mesh['x0'], reactions),
                             reaction_node_ids=mesh['node_id'][nodes].tolist(),
                             reaction_vectors_N=reactions[nodes].tolist(),
                             correction_norm_N=float(np.linalg.norm(correction)),
                             relative_correction=float(np.linalg.norm(correction)/max(np.linalg.norm(raw), 1e-30)),
                             backward_error=float(model.stats['solve_backward_err']),
                             relative_residual=float(model.stats['solve_resid_rel'])))
        peak = int(np.argmax([r['rms_mm'] for r in rows]))
        return dict(score_mm=rows[peak]['rms_mm'], max_def_mm=max(r['max_def_mm'] for r in rows),
                    compliance_Nmm=sum(r['compliance_Nmm'] for r in rows),
                    peak_case=peak, cases=rows)

    def _incremental(self, mesh):
        self.prepare_increments()
        height_change = mesh['x0'][:, 2]-self.mesh['x0'][:, 2]
        total = np.zeros_like(mesh['x0']); rows = []
        for ref in self.increments:
            x = ref['x']+ref['normal']*height_change[:, None]
            model = make_shell(mesh, x); solve = gauge_solve(model)
            full, reactions = solve.solve(ref['force'])
            # Match only the six rigid gauge components to the measured reference increment.
            # No elastic part of the reference displacement is added to the computed solution.
            difference = full[:, :3]-ref['du']
            du = ref['du']+remove_linear_rigid(x, difference)[0]
            total += du
            rms, max_def, _ = shape_score(mesh['x0'], total)
            nodes=np.flatnonzero(np.linalg.norm(reactions,axis=1)>0)
            rows.append(dict(frame=ref['end'], rms_mm=rms, max_def_mm=max_def,
                             applied=resultants(x, ref['force']), reactions=resultants(x, reactions),
                             reaction_node_ids=mesh['node_id'][nodes].tolist(),reaction_vectors_N=reactions[nodes].tolist(),
                             backward_error=float(model.stats['solve_backward_err']),
                             relative_residual=float(model.stats['solve_resid_rel'])))
        return dict(score_mm=max(r['rms_mm'] for r in rows), max_def_mm=max(r['max_def_mm'] for r in rows),
                    compliance_Nmm=None, cases=rows)
