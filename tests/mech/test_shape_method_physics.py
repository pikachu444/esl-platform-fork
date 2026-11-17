"""Numerical mechanics checks separate from blind native validation."""
import numpy as np
from esl.benchmarks.corner_model import make_mesh,nodal_mass,impact_coordinates
from esl.benchmarks.shape_methods import read
from esl.mech.drop_surrogates import make_shell,inertia_relief
from esl.mech.shape_methods import Reference,relative_error,project_fields
from pathlib import Path

def setup():
    cfg=read(Path(__file__).resolve().parents[2]/'config/shape_method_validation.json')
    cfg['plate'].update(nx=8,ny=6)
    mesh=make_mesh(cfg);x=mesh['x0'];xn=x[:,0]/800;yn=x[:,1]/450
    u=np.column_stack([.01*xn*yn,.008*np.sin(np.pi*xn),.1*np.sin(np.pi*xn)*np.sin(np.pi*yn)])
    slope=np.column_stack([.003*np.cos(np.pi*xn),.004*yn,.02*np.sin(2*np.pi*xn)*np.sin(np.pi*yn)])
    spc={'primary':[(62,'123'),(56,'13'),(6,'3')],
         'alternate':[(0,'123'),(56,'23'),(6,'3')]}
    return cfg,mesh,np.array([u]),np.array([slope]),spc

def test_true_corner_orientation_and_proper_rotation():
    cfg,mesh,*_=setup();x,R=impact_coordinates(mesh,cfg['drop'])
    np.testing.assert_allclose(R.T@R,np.eye(3),atol=1e-14)
    assert abs(np.linalg.det(R)-1)<1e-14
    diagonal=np.array([800.,450.,0.]);world=R@diagonal
    np.testing.assert_allclose(world[:2],0,atol=2e-13)
    assert world[2]>0 and np.argmin(x[:,2])==0

def test_first_order_has_correct_shape_derivative_and_balanced_gauge():
    cfg,mesh,u,g,spc=setup();h=1e-4;cal=[]
    for j in range(6):
        dm=mesh['depths'].copy();dp=dm.copy();dm[j]-=h;dp[j]+=h
        factor=1 if j==0 else 0
        cal.append((make_mesh(cfg,dm),u-h*g*factor,make_mesh(cfg,dp),u+h*g*factor))
    ref=Reference(mesh,u,cal,h,spc)
    errors=[]
    for delta in [.02,.01]:
        depths=mesh['depths'].copy();depths[0]+=delta;cm=make_mesh(cfg,depths)
        fields,rec=ref.predict(cm,np.r_[delta,np.zeros(5)],nodal_mass(cm,cfg['material']['density_tonne_mm3']),['first_order_balanced'])
        assert rec['first_order_balanced']['status']=='completed'
        target=project_fields(cm['x0'],u+delta*g)
        errors.append(relative_error(fields['first_order_balanced'],target))
        assert rec['first_order_balanced']['gauge_relative_l2']<1e-7
    # First-order load should have a second-order state error when the local response is smooth.
    assert 2.5<errors[0]/errors[1]<5.5,errors

def test_elastic_rigid_modes_do_not_create_condensed_loading():
    cfg,mesh,*_=setup();model=make_shell(mesh);x=mesh['x0'];r=x-x.mean(axis=0)
    u=np.broadcast_to([.2,-.1,.3],x.shape)+np.cross([.001,-.002,.003],r)
    f=model.condensed_forces(u)
    assert np.linalg.norm(f)<1e-6


def test_snapshot_uses_reference_basis_and_replays_baseline():
    cfg, mesh, u, g, supports = setup()
    fields = project_fields(mesh['x0'], np.concatenate([u, g]))
    ref = Reference(mesh, fields, [], 0.05, supports, basis_energy_fraction=1.)
    methods = ['snapshot_esl', 'reference_replay']
    density = cfg['material']['density_tonne_mm3']
    pred, record = ref.predict(mesh, np.zeros(6), nodal_mass(mesh, density), methods)
    np.testing.assert_allclose(pred['snapshot_esl'], fields, atol=1e-8)
    assert record['snapshot_esl']['details'][0]['rank'] == 2

    change = np.array([.05, 0, 0, 0, 0, 0])
    candidate = make_mesh(cfg, mesh['depths']+change)
    pred, record = ref.predict(candidate, change, nodal_mass(candidate, density), methods)
    assert record['snapshot_esl']['gauge_relative_l2'] == 0.
    assert relative_error(pred['snapshot_esl'], pred['reference_replay']) > 1e-5
    np.testing.assert_allclose(pred['reference_replay'], project_fields(candidate['x0'], fields), atol=1e-12)


def test_balanced_increment_uses_candidate_geometry_and_removes_wrench():
    cfg, mesh, u, g, supports = setup()
    history = project_fields(mesh['x0'], np.concatenate([u, u+g]))
    ref = Reference(mesh, history, [], .05, supports)
    change = np.array([.05, 0, 0, 0, 0, 0])
    candidate = make_mesh(cfg, mesh['depths']+change)
    methods = ['incremental', 'incremental_balanced']
    _, record = ref.predict(candidate, change, nodal_mass(candidate, cfg['material']['density_tonne_mm3']), methods)
    raw, balanced = (record[m]['details'][0] for m in methods)
    assert raw['applied']['moment_fraction'] > 1e-8
    assert balanced['applied']['force_fraction'] < 1e-12
    assert balanced['applied']['moment_fraction'] < 1e-12
    assert record['incremental_balanced']['gauge_relative_l2'] < 1e-7
