"""Check F-ESL sensitivities at the two published points in Buzaglo & Pollini §5.1."""
from __future__ import annotations

import json

import numpy as np


def newmark(load, mass, damping, stiffness, dt):
    """Newmark average acceleration with zero initial displacement and velocity."""
    u = np.zeros_like(load)
    v = np.zeros_like(load)
    a = np.zeros_like(load)
    a[0] = load[0]/mass
    effective_mass = mass + damping*dt/2 + stiffness*dt**2/4
    for i in range(1, len(load)):
        u_pred = u[i-1] + dt*v[i-1] + dt**2*a[i-1]/4
        v_pred = v[i-1] + dt*a[i-1]/2
        a[i] = (load[i] - damping*v_pred - stiffness*u_pred)/effective_mass
        u[i] = u_pred + dt**2*a[i]/4
        v[i] = v_pred + dt*a[i]/2
    return u, a


def evaluate_point(areas, reference_objective, reference_gradient, dt):
    damping = 0.1
    dm, dk = np.array([0.5, 0.75]), np.array([1., 2./3.])
    times = dt*np.arange(round(202/dt) + 1)
    load = np.sin(np.pi/2*times)

    def simulate(section):
        return newmark(load, dm @ section, damping, dk @ section, dt)

    mass, stiffness = dm @ areas, dk @ areas
    u, acceleration = simulate(areas)
    grad_u = newmark(-acceleration[:, None]*dm - u[:, None]*dk, mass, damping, stiffness, dt)[0]
    grad_f = u[:, None]*dk + stiffness*grad_u
    published_window = times >= 200.
    u, grad_u, grad_f = u[published_window], grad_u[published_window], grad_f[published_window]
    f0 = stiffness*u

    def static_gradient(step, grad_force):
        plus = (f0[:, None] + step*grad_force)/(stiffness + step*dk)
        minus = (f0[:, None] - step*grad_force)/(stiffness - step*dk)
        return (plus-minus)/(2*step)

    step = 1e-5
    directions = step*np.eye(2)
    grad_fd = np.column_stack([(simulate(areas+d)[0] - simulate(areas-d)[0])[published_window]/(2*step)
                              for d in directions])
    grad_f_esl = static_gradient(step, grad_f)
    grad_frozen = static_gradient(step, np.zeros_like(grad_f))
    objective = dt*stiffness*np.sum(u*u)
    objective_gradient = dt*np.sum(u[:, None]**2*dk+2*stiffness*u[:, None]*grad_u, axis=0)
    scale = np.linalg.norm(grad_u)
    return dict(
        section_areas=areas.tolist(), objective=float(objective),
        objective_gradient=objective_gradient.tolist(), paper_objective=reference_objective,
        paper_objective_gradient=reference_gradient,
        direct_vs_dynamic_fd_l2=float(np.linalg.norm(grad_u-grad_fd)/scale),
        first_order_vs_direct_gradient_l2=float(np.linalg.norm(grad_f_esl-grad_u)/scale),
        frozen_vs_direct_gradient_l2=float(np.linalg.norm(grad_frozen-grad_u)/scale),
    )


def reproduce():
    points = ((np.array([.1, .6]), .888, [1.26, -1.56]),
              (np.array([.85, .1]), 7.344, [-.72, -38.86]))
    return dict(
        source='https://arxiv.org/abs/2508.07222', section='5.1, Table 1 and Figure 3',
        runs=[dict(time_step=dt, published_step=dt==.2,
                   points=[evaluate_point(*point, dt) for point in points]) for dt in (.2, .02)],
    )


if __name__ == '__main__':
    print(json.dumps(reproduce(), indent=2))
