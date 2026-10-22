# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load task-local layouts without extending AutoData's environment-profile schema."""

import json
import math
import yaml
from pathlib import Path
from typing import Any

from .prop_assets import PROP_ASSET_DIR, validate_prop_assets

SCENE_CONFIG_DIR = Path(__file__).resolve().parent / "scenes"
SCENE_NAMES = ("desk", "gs_table")


def load_scene_layout(scene_name: str) -> dict[str, Any]:
    """Load a fresh layout and validate only the selected scene's assets.

    Args:
        scene_name: Name of a YAML layout in :data:`SCENE_CONFIG_DIR`.

    Returns:
        Task layout with absolute asset paths and a convex placement polygon [m].
    """
    assert scene_name in SCENE_NAMES, f"Unknown scene {scene_name!r}; choose from {SCENE_NAMES}"
    with (SCENE_CONFIG_DIR / f"{scene_name}.yaml").open() as stream:
        layout = yaml.safe_load(stream)
    required = {
        "table_usd",
        "asset_dependencies",
        "table_position",
        "table_orientation",
        "table_height",
        "robot_position",
        "nightstand_position",
        "nightstand_orientation",
        "cube_half_size",
        "cube_spawn_left",
        "cube_spawn_right",
        "cube_spawn_offsets",
        "static_objects",
        "world_ignore_substrings",
    }
    optional = {
        "pad_geometry",
        "pad_footprint",
        "pad_surface_z",
        "mousepad",
        "ground_plane",
        "left_elbow_angle",
        "nightstand_scale",
    }
    assert isinstance(layout, dict), "Scene layout must be a mapping"
    assert required <= layout.keys(), f"Missing scene fields: {sorted(required - layout.keys())}"
    assert not layout.keys() - required - optional, f"Unknown scene fields: {layout.keys() - required - optional}"
    dependencies = [PROP_ASSET_DIR / path for path in layout["asset_dependencies"]]
    if "pad_geometry" in layout:
        assert "pad_footprint" not in layout and "pad_surface_z" not in layout, "Use one placement geometry source"
        geometry_path = PROP_ASSET_DIR / layout["pad_geometry"]
        assert geometry_path.is_file(), f"Missing scene geometry: {geometry_path}"
        with geometry_path.open() as stream:
            pad = json.load(stream)["mousepad"]
        layout["pad_footprint"] = pad["footprint_metric"]
        layout["pad_surface_z"] = pad["surface_z_m"]
        dependencies.append(geometry_path)
    layout.setdefault("ground_plane", True)
    assert isinstance(layout["ground_plane"], bool)
    if "mousepad" in layout:
        assert (
            not {"pad_geometry", "pad_footprint", "pad_surface_z"} & layout.keys()
        ), "Use one placement geometry source"
        pad = layout["mousepad"]
        pad_required = {"usd", "geometry", "position", "yaw"}
        assert pad_required <= pad.keys() <= pad_required | {"pitch"}, "Invalid mousepad configuration"
        pad.setdefault("pitch", 0.0)
        assert len(pad["position"]) == 3 and all(math.isfinite(v) for v in pad["position"])
        assert math.isfinite(pad["yaw"]) and math.isfinite(pad["pitch"])
        assert abs(pad["pitch"]) < math.pi / 2, "Mousepad top must face upwards"
        pad["usd"] = str(PROP_ASSET_DIR / pad["usd"])
        geometry_path = PROP_ASSET_DIR / pad["geometry"]
        with geometry_path.open() as stream:
            geometry = json.load(stream)["mousepad"]
        pad["footprint"] = tuple(tuple(point) for point in geometry["footprint_metric"])
        pad["surface_z"] = geometry["surface_z_m"]
        dependencies.extend((Path(pad["usd"]), geometry_path))
        x, y, z = pad["position"]
        c, sn = math.cos(pad["yaw"]), math.sin(pad["yaw"])
        cp = math.cos(pad["pitch"])
        top_x = math.sin(pad["pitch"]) * geometry["surface_z_m"]
        layout["pad_footprint"] = [
            (x + c * (cp * px + top_x) - sn * py, y + sn * (cp * px + top_x) + c * py)
            for px, py in geometry["footprint_metric"]
        ]
        layout["pad_surface_z"] = z + cp * geometry["surface_z_m"]
        # Table roots are Z-up; the pad may pitch to match its tabletop collider.
        qx, qy, qz, qw = layout["table_orientation"]
        assert abs(qx) < 1e-8 and abs(qy) < 1e-8, "Separate mousepad requires a level Z-up table root"
        table_yaw = 2 * math.atan2(qz, qw)
        c, sn = math.cos(table_yaw), math.sin(table_yaw)
        tx, ty, tz = layout["table_position"]
        pad["position_env"] = (tx + c * x - sn * y, ty + sn * x + c * y, tz + z)
        yaw = table_yaw + pad["yaw"]
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        cp, sp = math.cos(pad["pitch"] / 2), math.sin(pad["pitch"] / 2)
        pad["orientation_env"] = (-sy * sp, cy * sp, sy * cp, cy * cp)
    assert "pad_footprint" in layout and "pad_surface_z" in layout, "Placement geometry is required"
    for key in ("table_position", "robot_position", "nightstand_position", "cube_spawn_left", "cube_spawn_right"):
        values = layout[key]
        assert len(values) == 3 and all(math.isfinite(v) for v in values), f"Invalid position: {key}"
        layout[key] = tuple(values)
    for key in ("table_orientation", "nightstand_orientation"):
        values = layout[key]
        assert len(values) == 4 and math.isclose(sum(v * v for v in values), 1.0, abs_tol=1e-6), key
        layout[key] = tuple(values)
    polygon = tuple(tuple(point) for point in layout["pad_footprint"])
    assert len(polygon) >= 3 and all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in polygon)
    # Require a non-degenerate, counter-clockwise convex footprint for half-plane containment.
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        assert a != b, "Placement polygon has a zero-length edge"
        assert all(
            (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-10 for p in polygon
        ), "Placement polygon must be counter-clockwise and convex"
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
    assert area > 0, "Placement polygon has zero area"
    assert layout["cube_half_size"] > 0 and math.isfinite(layout["table_height"])
    assert math.isfinite(layout["pad_surface_z"])
    for axis, bounds in layout["cube_spawn_offsets"].items():
        assert axis in ("x", "y", "z", "roll", "pitch", "yaw"), f"Unknown spawn axis: {axis}"
        assert len(bounds) == 2 and all(math.isfinite(v) for v in bounds) and bounds[0] <= bounds[1]
    for key in ("static_objects", "world_ignore_substrings"):
        assert isinstance(layout[key], list) and all(isinstance(v, str) for v in layout[key]), key
    if "nightstand_scale" in layout:
        scale = layout["nightstand_scale"]
        assert len(scale) == 3 and all(math.isfinite(v) and v > 0 for v in scale), "Invalid nightstand scale"
        layout["nightstand_scale"] = tuple(scale)
    if "left_elbow_angle" in layout:
        assert math.isfinite(layout["left_elbow_angle"])
    layout["pad_footprint"] = polygon
    layout["table_usd"] = str(PROP_ASSET_DIR / layout["table_usd"])
    validate_prop_assets((Path(layout["table_usd"]), *dependencies))
    return layout
