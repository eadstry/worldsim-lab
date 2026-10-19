"""Register the shared factory and existing planners after simulator startup."""
import gymnasium as gym
import openarm_autodata.generation  # noqa: F401; register the existing planner profiles

from shared_config.config import GYM_ID
from shared_config.runtime import make_env_cfg

# Process-local registration metadata; no upstream source file is changed.
gym.spec(GYM_ID).kwargs['env_cfg_entry_point'] = make_env_cfg
