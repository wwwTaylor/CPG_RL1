"""Engine-agnostic A1 leg kinematics helpers.

These functions are reused by both PyBullet and Isaac integrations.
"""

from __future__ import annotations

import numpy as np


def compute_leg_jacobian_and_foot_position(
    leg_id: int,
    leg_joint_positions: np.ndarray,
    hip_link_length: float,
    thigh_link_length: float,
    calf_link_length: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Jacobian and foot position for one leg in leg frame."""
    q = leg_joint_positions
    l1, l2, l3 = hip_link_length, thigh_link_length, calf_link_length

    side_sign = -1 if leg_id in (0, 2) else 1

    s1, s2, s3 = np.sin(q[0]), np.sin(q[1]), np.sin(q[2])
    c1, c2, c3 = np.cos(q[0]), np.cos(q[1]), np.cos(q[2])

    c23 = c2 * c3 - s2 * s3
    s23 = s2 * c3 + c2 * s3

    jacobian = np.zeros((3, 3))
    jacobian[1, 0] = -side_sign * l1 * s1 + l2 * c2 * c1 + l3 * c23 * c1
    jacobian[2, 0] = side_sign * l1 * c1 + l2 * c2 * s1 + l3 * c23 * s1
    jacobian[0, 1] = -l3 * c23 - l2 * c2
    jacobian[1, 1] = -l2 * s2 * s1 - l3 * s23 * s1
    jacobian[2, 1] = l2 * s2 * c1 + l3 * s23 * c1
    jacobian[0, 2] = -l3 * c23
    jacobian[1, 2] = -l3 * s23 * s1
    jacobian[2, 2] = l3 * s23 * c1

    foot_pos = np.zeros(3)
    foot_pos[0] = -l3 * s23 - l2 * s2
    foot_pos[1] = l1 * side_sign * c1 + l3 * (s1 * c23) + l2 * c2 * s1
    foot_pos[2] = l1 * side_sign * s1 - l3 * (c1 * c23) - l2 * c1 * c2

    return jacobian, foot_pos


def compute_leg_inverse_kinematics(
    leg_id: int,
    xyz_coord: np.ndarray,
    hip_link_length: float,
    thigh_link_length: float,
    calf_link_length: float,
) -> np.ndarray:
    """Compute inverse kinematics for one A1 leg in leg frame."""
    shoulder_length = hip_link_length
    elbow_length = thigh_link_length
    wrist_length = calf_link_length

    x, y, z = xyz_coord

    d_term = (
        y**2
        + (-z) ** 2
        - shoulder_length**2
        + (-x) ** 2
        - elbow_length**2
        - wrist_length**2
    ) / (2 * wrist_length * elbow_length)
    d_term = np.clip(d_term, -1.0, 1.0)

    side_sign = -1 if leg_id in (0, 2) else 1

    wrist_angle = np.arctan2(-np.sqrt(1 - d_term**2), d_term)
    sqrt_component = y**2 + (-z) ** 2 - shoulder_length**2
    sqrt_component = max(float(sqrt_component), 0.0)

    shoulder_angle = -np.arctan2(z, y) - np.arctan2(
        np.sqrt(sqrt_component), side_sign * shoulder_length
    )
    elbow_angle = np.arctan2(-x, np.sqrt(sqrt_component)) - np.arctan2(
        wrist_length * np.sin(wrist_angle),
        elbow_length + wrist_length * np.cos(wrist_angle),
    )

    return np.array([-shoulder_angle, elbow_angle, wrist_angle])
