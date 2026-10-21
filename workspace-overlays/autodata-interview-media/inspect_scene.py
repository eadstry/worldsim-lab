# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Import the immutable mini USDZ in Blender and record import diagnostics."""
import bpy, json, sys, time
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
home, output=map(Path,args)
bpy.ops.wm.read_factory_settings(use_empty=True)
t=time.time()
bpy.ops.wm.usd_import(filepath=str(home), import_cameras=False, import_lights=False, import_materials=True)
rows=[]
for obj in bpy.data.objects:
 if obj.type=='MESH':
  from mathutils import Vector
  coords=[obj.matrix_world@Vector(c) for c in obj.bound_box]
  rows.append(dict(name=obj.name,location=list(obj.location),min=[min(v[i] for v in coords) for i in range(3)],max=[max(v[i] for v in coords) for i in range(3)]))
output.mkdir(parents=True,exist_ok=False)
(output/'objects.json').write_text(json.dumps(rows,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'home.blend'))
print(json.dumps(dict(seconds=time.time()-t,objects=len(bpy.data.objects),meshes=len(rows))),flush=True)
