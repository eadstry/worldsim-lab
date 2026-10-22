# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Run AutoData SkillGen with the delivered GS profile and unmodified task descriptor."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

p=argparse.ArgumentParser()
p.add_argument('--workspace',type=Path,required=True)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parent
production=a.workspace/'workspace-overlays/openarm-production'
sys.path[:0]=[str(root/'runtime'),str(a.workspace/'AutoData'),str(production)]
os.environ['OPENARM_TELEMETRY_FILE']=str(a.output/'telemetry.jsonl')
os.environ['OPENARM_LOG_INTERVAL']='10'
# Existing process-local compatibility hooks do not edit AutoData or the conda environment.
import importlib.util
spec=importlib.util.spec_from_file_location('production_generate',production/'generate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
options=SimpleNamespace(debug_planner=False,final_hold_steps=60,generation_num_trials=1,num_envs=1,export_workers=0)
script=a.workspace/'AutoData/scripts/generate_dataset.py'
source=module.build_source(script.read_text(),options)
source=source.replace('from compat import install', 'from planner_compat import install as install_planner_compat\ninstall_planner_compat()\nfrom compat import install',1)
configs=root/'runtime/openarm_autodata/tasks/pick_place/autodata_configs'
paths=[script,production/'generate.py',production/'compat.py',production/'runtime/patches/curobo_planner.py',production/'runtime/patches/single_arm_embodiment_adapter.py',configs/'tasks/openarm_bimanual_left_pick_place.yaml',configs/'env_profiles/openarm_left_gs_table.yaml',configs/'embodiments/openarm_bimanual_left_ik_rel.yaml',a.input,Path(__file__),root/'planner_compat.py']
(a.output/'provenance.json').write_text(json.dumps({'files':{str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths},'scope':'Actual AutoData SkillGen; source collected in GS physics; supplied task/profile/thresholds unchanged; requested one successful episode'},indent=2))
sys.argv=[str(script),'--viz','none','--enable_cameras','--kit_args','--enable omni.usd.schema.omni_lens_distortion',
          '--env_name','Isaac-PickPlace-Cube-OpenArm-GS-Bimanual-Left-IK-Rel-v0','--alg','skillgen',
          '--task_descriptor',str(configs/'tasks/openarm_bimanual_left_pick_place.yaml'),
          '--embodiment',str(configs/'embodiments/openarm_bimanual_left_ik_rel.yaml'),
          '--env_profile',str(configs/'env_profiles/openarm_left_gs_table.yaml'),
          '--input_file',str(a.input),'--output_file',str(a.output/'episodes.hdf5'),
          '--result_file',str(a.output/'result.json'),'--num_envs','1','--generation_num_trials','1']
namespace={'__name__':'__main__','__file__':str(script)}
try:
    exec(compile(source,str(script),'exec'),namespace)
except BaseException:
    import traceback
    traceback.print_exc()
    if 'simulation_app' in namespace:
        namespace['simulation_app'].close(exit_code=1)
    raise
