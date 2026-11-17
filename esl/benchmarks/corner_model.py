"""Parametric wide sheet, bead basis, physical masses and impact orientation."""
from __future__ import annotations

import numpy as np


def bead_basis(xy, length, width, opening, taper):
    x, y = np.asarray(xy).T
    coordinates = (y-width/3, y-2*width/3, x-length/3, x-2*length/3,
                   (width*x-length*y)/np.hypot(length, width),
                   (width*x+length*y-length*width)/np.hypot(length, width))
    edge = np.minimum.reduce((x, length-x, y, width-y))
    envelope = np.sin(np.pi/2*np.clip(edge/taper, 0, 1))**2
    return np.column_stack([np.where(np.abs(d) < opening/2,
                                    np.cos(np.pi*np.clip(d/opening, -.5, .5))**2, 0)*envelope
                            for d in coordinates])


def make_mesh(cfg, depths=None, multiplier=1):
    p, b, mat = cfg['plate'], cfg['beads'], cfg['material']
    nx, ny = int(p['nx']*multiplier), int(p['ny']*multiplier)
    x, y = np.meshgrid(np.linspace(0, p['length_mm'], nx+1),
                       np.linspace(0, p['width_mm'], ny+1), indexing='ij')
    xy = np.column_stack((x.ravel(), y.ravel()))
    B = bead_basis(xy, p['length_mm'], p['width_mm'], b['opening_width_mm'], b['edge_taper_mm'])
    depths = np.full(b['count'], b['baseline_depth_mm']) if depths is None else np.asarray(depths, float)
    X = np.column_stack((xy, B@depths))
    a = np.arange(nx*(ny+1)).reshape(nx, ny+1)[:, :-1].ravel()
    conn = np.column_stack((a, a+ny+1, a+ny+2, a+1))
    ne = len(conn)
    return dict(x0=X, conn=conn, elem_type=np.full(ne, 4, np.int8),
                node_id=np.arange(1, len(X)+1), elem_id=np.arange(1, ne+1),
                elem_pid=np.ones(ne, int), thickness=np.full(ne, p['thickness_mm']),
                E=np.full(ne, mat['E_MPa']), nu=np.full(ne, mat['nu']),
                depths=depths, basis=B)


def areas_normals(x, conn):
    q = np.asarray(x)[conn]
    av = .5*np.cross(q[:, 2]-q[:, 0], q[:, 3]-q[:, 1])
    return np.linalg.norm(av, axis=1), av


def nodal_mass(mesh, density):
    area, _ = areas_normals(mesh['x0'], mesh['conn'])
    m = np.zeros(len(mesh['x0']))
    np.add.at(m, mesh['conn'].ravel(), np.repeat(area*mesh['thickness']*density/4, 4))
    return m


def nodal_normals(x, conn):
    _, av = areas_normals(x, conn)
    n = np.zeros_like(x)
    np.add.at(n, conn.ravel(), np.repeat(av, 4, axis=0))
    return n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)


def impact_coordinates(mesh, drop):
    if drop.get('orientation') == 'corner_diagonal':
        # Rotate the initial plate's in-plane corner-to-center diagonal toward +Z.
        # At 90 degrees the center-to-corner diagonal is vertical, with node 1 lowest.
        span=np.ptp(mesh['x0'][:,:2],axis=0)
        direction=np.r_[span,0.]/np.linalg.norm(span)
        axis=np.cross(direction,[0.,0.,1.]);axis/=np.linalg.norm(axis)
        angle=np.deg2rad(drop['panel_tilt_deg'])
        x,y,z=axis;S=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
        R=np.eye(3)+np.sin(angle)*S+(1-np.cos(angle))*(S@S)
    else:
        a, b = np.deg2rad([drop['rx_deg'], drop['ry_deg']])
        rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
        ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
        R = ry@rx
    X = mesh['x0']@R.T
    X[:, 2] += drop['clearance_mm'] + .5*float(mesh['thickness'][0])-X[:, 2].min()
    return X, R


def geometry_metrics(mesh, density, baseline_mass, limits):
    area, av = areas_normals(mesh['x0'], mesh['conn'])
    normal = av/np.maximum(area[:, None], 1e-30)
    slope = float(np.degrees(np.arccos(np.clip(normal[:, 2], -1, 1))).max())
    mass = float(np.sum(area*mesh['thickness']*density))
    height = float(np.ptp(mesh['x0'][:, 2]))
    valid = bool(area.min() > 0 and mass <= baseline_mass*limits['max_mass_ratio']
                 and slope <= limits['max_slope_deg'] and height <= limits['max_height_mm'])
    return dict(valid=valid, mass_tonne=mass, mass_ratio=mass/baseline_mass,
                max_slope_deg=slope, max_height_mm=height, min_area_mm2=float(area.min()))
