import numpy as np
import pytest

from esl.benchmarks.corner_drop import load_config
from esl.benchmarks.corner_model import make_mesh, nodal_mass, nodal_normals
from esl.mech.drop_surrogates import inertia_relief, resultants, DropReference, shape_score


def small_case():
    cfg=load_config('config/corner_drop_benchmark.json');cfg['plate'].update(nx=8,ny=6)
    mesh=make_mesh(cfg);x=mesh['x0']
    u=np.zeros_like(x);u[:,2]=.05*np.sin(np.pi*x[:,0]/800)*np.sin(np.pi*x[:,1]/450)
    history=dict(u=np.array([u*0,u*.4,u]),rotation=np.repeat(np.eye(3)[None],3,axis=0),
                 contact=np.zeros((3,len(x),3)),acceleration=np.zeros((3,len(x),3)))
    normals=[nodal_normals(x+v,mesh['conn']) for v in history['u'][:-1]]
    ref=DropReference(mesh,history,[1,2],[0,1,2],normals,[0,0,-9810])
    return cfg,mesh,ref


def test_inertia_relief_removes_force_and_moment_but_keeps_balanced_bending():
    rng=np.random.default_rng(31);x=rng.normal(size=(20,3))*100;m=rng.uniform(1,3,20)
    f=rng.normal(size=x.shape);balanced,correction=inertia_relief(x,f,m)
    assert resultants(x,balanced)['force_fraction']<1e-14
    assert resultants(x,balanced)['moment_fraction']<1e-14
    np.testing.assert_allclose(inertia_relief(x,balanced,m)[0],balanced,atol=1e-14)
    x=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],float)
    bend=np.column_stack([np.zeros(4),np.zeros(4),[1,-1,1,-1]])
    np.testing.assert_allclose(inertia_relief(x,bend,np.ones(4))[0],bend,atol=1e-14)


def test_same_geometry_round_trip_including_increment_gauge():
    cfg,mesh,ref=small_case();mass=nodal_mass(mesh,cfg['material']['density_tonne_mm3'])
    methods=['displacement','balanced_displacement','incremental_geometry','ritz_reference']
    out=ref.evaluate(mesh,mass,methods)['methods'];expected=shape_score(mesh['x0'],ref.u[-1])[0]
    for name,row in out.items():
        assert row['status']=='completed',(name,row)
        assert row['score_mm']==pytest.approx(expected,rel=3e-6,abs=1e-8)


def test_candidate_balance_uses_candidate_coordinates():
    cfg,mesh,ref=small_case();candidate=make_mesh(cfg,[3,2,2,2,2,2])
    out=ref.evaluate(candidate,nodal_mass(candidate,cfg['material']['density_tonne_mm3']),
                     ['displacement','balanced_displacement'])['methods']
    d0=out['displacement']['cases'][-1];d1=out['balanced_displacement']['cases'][-1]
    assert d0['raw']['moment_fraction']>1e-8
    assert d1['applied']['moment_fraction']<1e-12
    assert d1['applied']['force_fraction']<1e-12
    assert d0['reaction_vectors_N']


def test_physical_force_uses_full_world_acceleration_before_body_rotation():
    cfg,mesh,ref=small_case();m=nodal_mass(mesh,cfg['material']['density_tonne_mm3'])
    accel=np.broadcast_to([123.,-456.,789.],mesh['x0'].shape)
    external=np.zeros_like(accel);external[:,2]=np.linspace(-1,1,len(m))
    ref.history['acceleration'][2]=accel
    ref.history['contact'][2]=m[:,None]*(accel-ref.gravity)+external
    rotation=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    ref.history['rotation'][2]=rotation
    np.testing.assert_allclose(ref.force('acceleration',1,m),external@rotation,atol=1e-14)
    # Contact-only source deliberately retains the deformation-inertia difference.
    assert np.linalg.norm(ref.force('contact',1,m)-external@rotation)>0
