"""Native articulated, contact-driven demonstrations with pre-action observations."""
from pathlib import Path
import argparse, copy, json, xml.etree.ElementTree as E
import mujoco, numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

def build(robot, source, out, seed=0, condition=0):
    root = E.parse(source).getroot()
    comp = root.find('compiler')
    comp.set('meshdir', str((source.parent / comp.get('meshdir', '.')).resolve()))
    root.attrib['model'] = robot + '_mini'
    opt = root.find('option')
    if opt is None:
        opt = E.SubElement(root, 'option')
    opt.attrib.update(timestep=str(1 / 1200), integrator='implicitfast', iterations='70')
    world = root.find('worldbody')
    base = world.find('body')
    cfg = {'g1d': dict(pos=[0.42, -0.58, -0.6], yaw=np.pi / 2, ee='right_hand_palm_link', tcp=[0.09, 0.075, 0], prefix='right_', grip=['right_hand_thumb_0_joint', 'right_hand_thumb_1_joint', 'right_hand_thumb_2_joint', 'right_hand_middle_0_joint', 'right_hand_middle_1_joint', 'right_hand_index_0_joint', 'right_hand_index_1_joint'], op=[0.3, 0.5, 0, 0.1, 0.8, 0.1, 0.8], cl=[0.3, -0.3, -0.4, 0.7, 0.8, 0.7, 0.8], half=0.03), 'openarm': dict(pos=[1.33, -0.05, -0.35], yaw=0, ee='openarm_right_ee_base_link', tcp=[-0.00143, 0, -0.128], prefix='openarm_right_joint', grip=['openarm_right_finger_joint1', 'openarm_right_finger_joint2'], op=[-0.65, -0.65], cl=[0, 0], half=0.02), 'so101': dict(pos=[0.44, -0.25, 0], yaw=0, ee='gripper', tcp=[0.0071, -0.000218121, -0.0981274], prefix='', grip=['gripper'], op=[0.3], cl=[-0.1], half=0.015)}[robot]
    base.set('pos', ' '.join(map(str, cfg['pos'])))
    q = Rotation.from_euler('z', cfg['yaw']).as_quat()
    base.set('quat', ' '.join(map(str, q[[3, 0, 1, 2]])))
    for b in base.iter('body'):
        for g in b.findall('geom'):
            visual = g.get('group') in (['2'] if robot == 'so101' else ['1'])
            g.set('contype', '0' if visual else '1')
            g.set('conaffinity', '0' if visual else '2')
            g.set('friction', '1.2 .01 .001')
            g.set('condim', '4')
    for j in base.iter('joint'):
        j.set('damping', '.2' if j.get('name') in cfg['grip'] else '3')
        j.set('armature', '.01' if j.get('name') in cfg['grip'] else '.08')
    ee = next((b for b in base.iter('body') if b.get('name') == cfg['ee']))
    E.SubElement(ee, 'site', dict(name='task_tcp', pos=' '.join(map(str, cfg['tcp'])), size='.003'))
    E.SubElement(world, 'geom', dict(name='table_support', type='box', size='.675392 .442032 .025', pos='.558701 -.011005 -.025', contype='2', conaffinity='3', friction='1.2 .01 .001'))
    half = cfg['half']
    rng = np.random.default_rng(seed)
    xs = [1.075, 0.945, 1.01] if robot == 'openarm' else [0.85, 0.57, 0.71] if robot != 'so101' else [0.65, 0.57, 0.61]
    y = -0.24 if robot != 'so101' else -0.29
    starts = np.array([[x, y, half + 0.001] for x in xs])
    goals = np.array([[x, y + 0.11, half + 0.001] for x in sorted(xs)])
    if robot == 'so101':
        starts = np.array([[0.65, -0.13, half + 0.001], [0.65, -0.37, half + 0.001], [0.65, -0.25, half + 0.001]])
        goals = np.array([[0.7, -0.37, half + 0.001], [0.7, -0.25, half + 0.001], [0.7, -0.13, half + 0.001]])
    if robot == 'g1d':
        starts[:, 1] = -0.38
        goals[:, 1] = -0.21
    starts[:, :2] += rng.uniform(-(0.002 if condition == 3 else 0.0005), 0.002 if condition == 3 else 0.0005, (3, 2))
    cfg['mass_kg'] = float(rng.uniform(0.0315, 0.0385))
    cfg['friction'] = float(rng.uniform(1.1, 1.35))
    for i, (c, pos) in enumerate(zip(['red', 'green', 'blue'], starts)):
        b = E.SubElement(world, 'body', dict(name='cube_' + c, pos=' '.join(map(str, pos))))
        E.SubElement(b, 'freejoint')
        E.SubElement(b, 'geom', dict(name='cube_' + c, type='box', size=f'{half} {half} {half}', mass=str(cfg['mass_kg']), contype='2', conaffinity='3', friction=f"{cfg['friction']} .01 .001", condim='4', rgba=['.75 .02 .02 1', '.02 .55 .05 1', '.02 .08 .8 1'][i]))
    old = root.find('actuator')
    if old is not None:
        root.remove(old)
    act = E.SubElement(root, 'actuator')
    names = []
    for j in base.iter('joint'):
        n = j.get('name')
        names.append(n)
        finger = n in cfg['grip']
        slide = j.get('type') == 'slide'
        E.SubElement(act, 'position', dict(name=n, joint=n, kp=('30' if robot == 'g1d' else '30' if robot == 'so101' else '80') if finger else '3000' if slide else '500', kv='.8' if finger else '80' if slide else '14'))
    if robot == 'so101':
        for actuator in act:
            actuator.set('forcerange', '-3.35 3.35')
    out.mkdir(parents=True, exist_ok=False)
    E.ElementTree(root).write(out / 'task.xml')
    return (cfg, starts, goals)

def run(a):
    cfg, starts, goals = build(a.robot, a.source, a.out, a.seed, a.condition)
    m = mujoco.MjModel.from_xml_path(str((a.out / 'task.xml').resolve()))
    d = mujoco.MjData(m)
    ikd = mujoco.MjData(m)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, int(j)) for j in m.actuator_trnid[:, 0]]
    jid = m.actuator_trnid[:, 0]
    qi = m.jnt_qposadr[jid]
    vi = m.jnt_dofadr[jid]
    grip = np.array([names.index(n) for n in cfg['grip']])
    arm = np.array([i for i, n in enumerate(names) if n not in cfg['grip'] and (n.startswith(cfg['prefix']) if cfg['prefix'] else True) and ('hand' not in n)])
    if a.robot == 'g1d':
        arm = np.array([i for i, n in enumerate(names) if n.startswith('right_') and '_hand_' not in n])
    lo = m.jnt_range[jid[arm], 0]
    hi = m.jnt_range[jid[arm], 1]
    site = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, 'task_tcp')
    desired = Rotation.from_euler('z', np.pi / 2 if a.robot == 'g1d' else 0).as_matrix()
    if a.robot == 'g1d':
        desired = np.eye(3)

    def solve(xyz, prior, incremental=False):
        ikd.qpos[:] = d.qpos

        def fun(q):
            ikd.qpos[qi[arm]] = q
            mujoco.mj_forward(m, ikd)
            r = ikd.site_xmat[site].reshape(3, 3)
            orient = Rotation.from_matrix(desired @ r.T).as_rotvec()
            return np.r_[(ikd.site_xpos[site] - xyz) * 10, orient * 0.15, (q - prior) * (0.0001 if incremental else 1e-05)]
        best = None
        boundlo = np.maximum(lo, prior - 0.2) if incremental else lo
        boundhi = np.minimum(hi, prior + 0.2) if incremental else hi
        for k in range(1 if incremental else 7):
            seed = prior if k == 0 else np.random.default_rng(k + 11).uniform(lo * 0.8, hi * 0.8)
            sol = least_squares(fun, np.clip(seed, boundlo + 1e-07, boundhi - 1e-07), bounds=(boundlo, boundhi), max_nfev=150)
            err = np.linalg.norm(fun(sol.x))
            if best is None or err < best[0]:
                best = (err, sol.x)
            if err < 0.002:
                break
        if np.linalg.norm(fun(best[1])[:3]) > 0.04 or np.linalg.norm(fun(best[1])[3:6]) > 0.1:
            raise RuntimeError(f'Unreachable {xyz}: {best[0]} q={best[1]} residual={fun(best[1])}')
        return best[1]
    for n, val in [('left_elbow_joint', 1.1), ('left_shoulder_roll_joint', 0.15)]:
        if n in names:
            d.qpos[qi[names.index(n)]] = val
    d.qpos[qi[grip]] = cfg['op']
    prior = np.clip(np.zeros(len(arm)), lo + 0.01, hi - 0.01)
    high = 0.14 if a.robot != 'so101' else 0.075
    selected = list(range(3)) if a.count == 3 else [a.seed % 3] if a.robot == 'so101' else [0]
    start = np.r_[starts[selected[0], :2], high]
    initial = solve(start, prior)
    d.qpos[qi[arm]] = initial
    d.ctrl[:] = d.qpos[qi]
    mujoco.mj_forward(m, d)
    cb = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'cube_' + c) for c in ['red', 'green', 'blue']])
    records = []
    phases = []
    checks = []

    def phase(label, seconds, xyz, closed):
        begin = d.ctrl.copy()
        goal = begin.copy()
        goal[grip] = cfg['cl'] if closed else cfg['op']
        origin = d.site_xpos[site].copy()
        for f in range(round(seconds * 30)):
            t = min((f + 1) / (seconds * 30 * 0.8), 1)
            t = t * t * (3 - 2 * t)
            ctrl = begin * (1 - t) + goal * t
            if xyz is not None:
                ctrl[arm] = solve(origin * (1 - t) + np.array(xyz) * t, d.ctrl[arm], incremental=True)
            state = d.qpos[qi].copy()
            poses = np.c_[d.xpos.copy(), d.xquat.copy()]
            cube = d.xpos[cb].copy()
            d.ctrl[:] = ctrl
            for _ in range(40):
                d.qfrc_applied[:] = 0
                d.qfrc_applied[vi] = d.qfrc_bias[vi]
                mujoco.mj_step(m, d)
                if any((w.number for w in d.warning)) or not np.isfinite(d.qpos).all():
                    raise RuntimeError('Unstable native contact dynamics')
            mujoco.mj_forward(m, d)
            contacts = []
            for c in d.contact:
                b1, b2 = (m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2])
                if b1 in cb or b2 in cb:
                    contacts.append([int(b1), int(b2), float(c.dist)])
            records.append((state, ctrl.copy(), d.qpos[qi].copy(), poses, cube, d.xpos[cb].copy(), len(contacts)))
            phases.append(label)
        print(label, d.xpos[cb].round(4).tolist(), flush=True)
    phase('settle', 0.6, start, False)
    for i in selected:
        color = ['red', 'green', 'blue'][i]
        src = d.xpos[cb[i]].copy()
        dest = goals[i]
        graspz = src[2] + (0.018 if a.robot == 'g1d' else 0.012 if a.robot == 'openarm' else 0)
        phase(color + '_approach', 1, [*src[:2], high], False)
        phase(color + '_descend', 1, [*src[:2], graspz], False)
        phase(color + '_close', 0.8, [*src[:2], graspz], True)
        before = d.xpos[cb[i]].copy()
        phase(color + '_lift', 1.1, [*src[:2], high], True)
        lift = float(d.xpos[cb[i], 2] - before[2])
        offset = d.xpos[cb[i], :2] - d.site_xpos[site, :2]
        place_xy = dest[:2] - offset
        if a.robot == 'so101':
            place_xy = dest[:2]
        phase(color + '_transfer', 2.5 if a.robot == 'g1d' else 1.5, [*place_xy, high], True)
        if a.robot == 'g1d':
            offset3 = d.xpos[cb[i]] - d.site_xpos[site]
            place_xy = dest[:2] - offset3[:2]
            release_z = cfg['half'] + 0.002 - offset3[2]
        else:
            release_z = graspz + (0.025 if a.robot == 'openarm' else 0)
        phase(color + '_lower', 1.5 if a.robot == 'g1d' else 1.2, [*place_xy, release_z], True)
        phase(color + '_release', 1.1 if a.robot == 'g1d' else 0.8, [*place_xy, release_z], False)
        phase(color + '_retreat', 0.9, [*place_xy, high], False)
        transfer_z = [float(r[4][i, 2]) for r, ph in zip(records, phases) if ph == color + '_transfer']
        checks.append(dict(color=color, cube_index=i, lift_m=lift, min_transfer_height_m=min(transfer_z)))
    phase('final_settle', 0.7, None, False)
    for check in checks:
        i = check['cube_index']
        check.update(error_xy_m=float(np.linalg.norm(d.xpos[cb[i], :2] - goals[i, :2])), rest_height_error_m=float(abs(d.xpos[cb[i], 2] - cfg['half'])))
    arrays = {k: np.array([r[i] for r in records]) for i, k in enumerate(['state', 'action', 'next_state', 'body_pose', 'cube_pos', 'next_cube_pos', 'cube_contact_count'])}
    np.savez_compressed(a.out / 'trajectory.npz', **arrays, phases=np.array(phases))
    sort_axis = 1 if a.robot == 'so101' else 0
    cross_axis = 1 - sort_axis
    sorted_ok = a.count != 3 or (bool(np.all(np.diff(d.xpos[cb, sort_axis]) > cfg['half'] * 2 + 0.005)) and float(np.ptp(d.xpos[cb, cross_axis])) < 0.045)
    summary = dict(sort_order_valid=sorted_ok, generator='native-contact-v1', robot=a.robot, seed=a.seed, condition=a.condition, fps=30, frames=len(records), joint_names=names, units=['m' if m.jnt_type[j] == 2 else 'rad' for j in jid], success=sorted_ok and all((c['lift_m'] > 0.045 and c['min_transfer_height_m'] > cfg['half'] + 0.03 and (c['error_xy_m'] < (0.02 if a.robot == 'so101' else 0.035)) and (c['rest_height_error_m'] < 0.004) for c in checks)), checks=checks, starts=starts.tolist(), goals=goals.tolist(), cfg=cfg, body_names=[mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)], limitations=['Scripted IK and ideal gravity compensation', 'Native convex collision meshes, measured table support proxy', 'Robot self-collision omitted; full home is rendered'])
    (a.out / 'verification.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    assert summary['success'], 'Contact manipulation failed'
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--robot', choices=['g1d', 'openarm', 'so101'], required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=1)
    p.add_argument('--seed', type=int, default=31)
    p.add_argument('--condition', type=int, default=0)
    run(p.parse_args())
