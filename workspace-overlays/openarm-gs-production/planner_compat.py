# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Supply configuration fields expected by the delivered package on the locked AutoData API."""
def install():
    from curobo.util_file import load_yaml
    from isaaclab.utils.configclass import configclass
    from autodata_interfaces.motion_planners.curobo import curobo_planner_cfg as cfg
    @configclass
    class GSCompatiblePlannerCfg(cfg.CuroboPlannerCfg):
        warmup: bool = False
        contact_offset_axis: tuple[float,float,float] = (0.,0.,1.)
        gripper_closes_on_increasing_position: bool = True
        def get_robot_config(self):
            return load_yaml(self.robot_config_file)['robot_cfg']
    cfg.CuroboPlannerCfg=GSCompatiblePlannerCfg
