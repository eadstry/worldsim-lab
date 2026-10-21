"""Edit the ephemeral simulation stage and verify robot collision interventions."""


def robot_roots(stage):
    envs = stage.GetPrimAtPath("/World/envs")
    return [env.GetChild("Robot") for env in envs.GetChildren() if env.GetChild("Robot").IsValid()]


def disable_before_physics(cfg):
    """Uninstance collision geometry in memory before the physics scene is created."""
    from pxr import UsdPhysics

    original = cfg.scene.robot.spawn.func
    # The generic nested-property editor skips instance proxies; do not rely on it.
    cfg.scene.robot.spawn.collision_props = None

    def disable(prim):
        if prim.IsInstance():
            prim.SetInstanceable(False)
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr().Set(False)
        for child in prim.GetChildren():
            disable(child)

    def spawn(prim_path, spawn_cfg, *args, **kwargs):
        prim = original(prim_path, spawn_cfg, *args, **kwargs)
        for root in robot_roots(prim.GetStage()):
            disable(root)
        return prim

    cfg.scene.robot.spawn.func = spawn


def audit(stage, expect_disabled):
    from pxr import Usd, UsdPhysics

    result = {"roots": 0, "enabled": 0, "disabled": 0, "enabled_examples": []}
    for root in robot_roots(stage):
        result["roots"] += 1
        for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                enabled = bool(UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get())
                result["enabled" if enabled else "disabled"] += 1
                if enabled and len(result["enabled_examples"]) < 3:
                    result["enabled_examples"].append(str(prim.GetPath()))
    if not result["roots"] or not result["enabled"] + result["disabled"]:
        raise RuntimeError("Collision intervention could not inspect any robot colliders")
    if expect_disabled and result["enabled"]:
        raise RuntimeError(f"Collision intervention did not take effect: {result}")
    return result
