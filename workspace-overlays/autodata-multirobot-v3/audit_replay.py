"""Replay stored joint targets in MuJoCo, verifying native dynamics and observation timing."""
import argparse, json, xml.etree.ElementTree as E
from pathlib import Path
import mujoco, numpy as np
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
results = []
for episode in sorted(a.source.glob('*/episode-*')):
    info = json.loads((episode / 'verification.json').read_text())
    r = np.load(episode / 'trajectory.npz')
    assert info['success']
    np.testing.assert_array_equal(r['next_state'][:-1], r['state'][1:])
    np.testing.assert_array_equal(r['next_cube_pos'][:-1], r['cube_pos'][1:])
    xml = E.parse(episode / 'task.xml')
    assert not xml.findall('.//weld') and (not any((b.get('mocap') == 'true' for b in xml.findall('.//body')))), 'Grasp attachment found'
    m = mujoco.MjModel.from_xml_path(str((episode / 'task.xml').resolve()))
    d = mujoco.MjData(m)
    jids = m.actuator_trnid[:, 0]
    qi = m.jnt_qposadr[jids]
    vi = m.jnt_dofadr[jids]
    d.qpos[qi] = r['state'][0]
    cb = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'cube_' + c) for c in ['red', 'green', 'blue']])
    for b in cb:
        j = m.body_jntadr[b]
        assert m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
        q = m.jnt_qposadr[j]
        d.qpos[q:q + 7] = r['body_pose'][0, b]
    d.ctrl[:] = r['state'][0]
    mujoco.mj_forward(m, d)
    maximum = 0
    for i in range(len(r['state'])):
        error = float(np.max(np.abs(d.qpos[qi] - r['state'][i])))
        maximum = max(maximum, error)
        np.testing.assert_allclose(d.qpos[qi], r['state'][i], atol=1e-06, rtol=0, err_msg=f'{episode.name}/{i}/pre-state')
        np.testing.assert_allclose(d.xpos[cb], r['cube_pos'][i], atol=1e-06, rtol=0)
        d.ctrl[:] = r['action'][i]
        for step in range(40):
            d.qfrc_applied[:] = 0
            d.qfrc_applied[vi] = d.qfrc_bias[vi]
            mujoco.mj_step(m, d)
        mujoco.mj_forward(m, d)
        np.testing.assert_allclose(d.qpos[qi], r['next_state'][i], atol=1e-06, rtol=0)
        np.testing.assert_allclose(d.xpos[cb], r['next_cube_pos'][i], atol=1e-06, rtol=0)
    for c in info['checks']:
        ci = ['red', 'green', 'blue'].index(c['color'])
        sel = r['phases'] == c['color'] + '_transfer'
        assert r['cube_pos'][sel, ci, 2].min() > info['cfg']['half'] + 0.03, 'Dropped during transfer'
    if len(info['checks']) == 3:
        axis = 1 if info['robot'] == 'so101' else 0
        assert np.all(np.diff(r['next_cube_pos'][-1, :, axis]) > info['cfg']['half'] * 2 + 0.005), 'Incorrect RGB order'
    result = dict(robot=info['robot'], episode=episode.name, frames=len(r['state']), maximum_joint_replay_error=maximum, no_attachment=True, all_pre_and_post_states_replayed=True)
    results.append(result)
    print(json.dumps(result), flush=True)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(dict(mujoco=mujoco.__version__, episodes=len(results), frames=sum((x['frames'] for x in results)), results=results), indent=2))
assert len(results) == 36
