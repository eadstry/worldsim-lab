"""Compose recorded WXYZ body poses with native visual-geometry local frames."""
import numpy as np

def compose_visual_frames(body_pose, local_position, local_quaternion):
    pose = np.asarray(body_pose, dtype=np.float64)
    if pose.ndim != 2 or pose.shape[1] != 7:
        raise ValueError('Expected N × 7 body positions and WXYZ quaternions')
    q = pose[:, 3:]
    if not np.allclose(np.linalg.norm(q, axis=1), 1, atol=1e-06):
        raise ValueError('Body quaternions must be normalized')
    p = np.asarray(local_position, dtype=np.float64)
    local = np.asarray(local_quaternion, dtype=np.float64)
    if p.shape != (3,) or local.shape != (4,) or (not np.isclose(np.linalg.norm(local), 1, atol=1e-06)):
        raise ValueError('Invalid local rigid transform')
    tangent = 2 * np.cross(q[:, 1:], p)
    position = pose[:, :3] + p + q[:, :1] * tangent + np.cross(q[:, 1:], tangent)
    quaternion = np.column_stack((q[:, 0] * local[0] - q[:, 1:] @ local[1:], q[:, :1] * local[1:] + local[0] * q[:, 1:] + np.cross(q[:, 1:], local[1:])))
    quaternion /= np.linalg.norm(quaternion, axis=1)[:, None]
    for i in range(1, len(quaternion)):
        if np.dot(quaternion[i - 1], quaternion[i]) < 0:
            quaternion[i] *= -1
    return (position, quaternion)
