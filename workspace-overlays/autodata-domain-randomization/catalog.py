# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Inventory the checked-out AutoData execution stack without importing simulation."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
A = 'AutoData/'
B = A + 'submodules/IsaacLab-Arena/'
L = B + 'submodules/IsaacLab/source/isaaclab/isaaclab/'
T = B + 'submodules/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/'
E = L + 'envs/mdp/events.py'
S = T + 'manager_based/manipulation/stack/mdp/franka_stack_events.py'
V = B + 'isaaclab_arena/variations/'
R = B + 'isaaclab_arena/relations/'
ITEMS = []


def add(group, name, kind, stage, params, sampling, access, note, *refs):
    sources = []
    for path, symbol in refs:
        content = (ROOT / path).read_text()
        nodes = [n for n in ast.walk(ast.parse(content))
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == symbol]
        assert nodes, (path, symbol)
        sources.append({'path': path, 'symbol': symbol, 'line': nodes[0].lineno,
                        'sha256': hashlib.sha256(content.encode()).hexdigest()})
    ITEMS.append({'id': f'm{len(ITEMS)+1:02d}', 'group': group, 'name': name, 'kind': kind,
                  'stage': stage, 'params': params, 'sampling': sampling, 'access': access,
                  'note': note, 'sources': sources})


# All public randomized event families from Isaac Lab's common mdp/events.py.
add('初始状态与布局', '根位姿与速度', 'pose', 'reset', 'XYZ / RPY [m, rad]；线速度 / 角速度', '各维均匀采样', 'AutoData event profile',
    'OpenArm 当前仅启用 XY 偏移；上一轮 GPU 256 样本验证通过。函数本身还支持 Z、RPY 和速度，不代表当前任务启用。', (E, 'reset_root_state_uniform'))
add('初始状态与布局', '全空间随机朝向', 'rotation', 'reset', '位置范围；速度范围；完整朝向', 'random_orientation 四元数采样', 'AutoData event profile',
    '与限定 roll/pitch/yaw 区间不同；会改变完整三维朝向。', (E, 'reset_root_state_with_random_orientation'))
add('初始状态与布局', '地形有效点出生', 'terrain', 'reset', 'flat_patches；位姿和速度范围', '从已生成地形有效 patch 中随机选点', '任务配置 + event profile',
    '需要 TerrainImporter 和有效 flat patches；OpenArm 桌面任务未配置。', (E, 'reset_root_state_from_terrain'))
add('初始状态与布局', '关节比例初始化', 'joint', 'reset', 'position_range；velocity_range', '默认关节位置/速度乘均匀随机比例', 'AutoData event profile',
    '位置裁剪到关节限位；不是控制增益随机化。', (E, 'reset_joints_by_scale'))
add('初始状态与布局', '关节偏移初始化', 'joint', 'reset', 'position_range；velocity_range', '默认关节位置/速度加均匀随机偏移', 'AutoData event profile',
    '按关节限位裁剪。', (E, 'reset_joints_by_offset'))
add('初始状态与布局', 'Franka 高斯关节偏移', 'joint', 'reset', 'mean；std', '关节位置高斯偏移', '任务专用 event profile',
    '实现保留最后两个夹爪关节默认位置，不能无审查直接套到其他机器人。', (S, 'randomize_joint_by_gaussian_offset'))
add('初始状态与布局', '柔体节点状态', 'deform', 'reset', 'position_range；velocity_range', '节点状态叠加均匀位移/速度采样', '柔体任务配置',
    '需要支持节点状态写入的 deformable asset；不适用于刚体 cube。', (E, 'reset_nodal_state_uniform'))
add('初始状态与布局', '多物体间距约束', 'layout', 'reset', 'pose_range；min_separation；max_sample_tries', '位姿均匀候选 + 间距拒绝采样', 'AutoData event profile',
    'franka_bin_stack 示例将 cube_1 固定，cube_2/cube_3 随机；采样次数有上限。', (S, 'randomize_object_pose'), (S, 'sample_object_poses'))
add('初始状态与布局', 'Arena 位姿区间', 'pose', 'reset', 'PoseRange：XYZ 最小/最大；RPY 最小/最大', '区间配置 → reset 事件', 'Arena 场景构建',
    'PoseRange 是区间描述；实际采样由构建器注册的事件负责。', (B+'isaaclab_arena/utils/pose.py', 'PoseRange'))
add('初始状态与布局', '辅助物体联动', 'layout', 'reset', 'held_and_fixed_only / held_fixed_and_auxiliary', '独立采样主体，辅助物体按主体对齐', 'Arena task event',
    '当前辅助资产写入同一位姿，要求资产坐标系匹配；不是任意相对偏移采样。', (B+'isaaclab_arena/tasks/events.py', 'randomize_poses_and_align_auxiliary_assets'))
add('初始状态与布局', '关系解周围扰动', 'layout', '求解后 / reset', 'RandomAroundSolution：XY 半径；yaw 半范围', '解附近的 PoseRange', 'Arena 关系布局构建',
    '以关系解为中心增加位姿范围；RandomAroundSolution 不等于重新验证所有扰动后布局。', (R+'relations.py', 'RandomAroundSolution'))
add('初始状态与布局', '关系布局池与随机 yaw', 'layout', '构建候选 / reset 消费', 'random_yaw_init；placement_seed；布局池', '初始 yaw 均匀采样；候选池有/无放回接口', 'Arena ObjectPlacer / PooledObjectPlacer',
    '实际 reset 用 sample_for_envs；约束求解有验证与失败回退，不能把所有写入结果当作约束通过。', (R+'object_placer.py', 'ObjectPlacer'), (R+'pooled_object_placer.py', 'PooledObjectPlacer'), (R+'placement_events.py', 'solve_and_place_objects'))

add('外观、光照与相机', '物体颜色', 'color', 'event 阶段可配置', 'colors：RGB 候选或通道范围；mesh_name', '离散颜色或 RGB 均匀采样', 'Isaac Lab event',
    '需要 Replicator、匹配的 mesh/body 路径及 replicate_physics=False；当前 OpenArm 未接入。', (E, 'randomize_visual_color'))
add('外观、光照与相机', '纹理与纹理旋转', 'texture', 'event 阶段可配置', 'texture_paths；texture_rotation [rad]', '纹理池随机选择 + 旋转范围', 'Isaac Lab / stack task event',
    '需要 Replicator、可访问纹理与匹配视觉路径，replicate_physics=False。不是自动随机粗糙度、金属度或透明度。', (E, 'randomize_visual_texture_material'), (S, 'randomize_visual_texture_material'))
add('外观、光照与相机', '灯光强度', 'light', 'Arena build-time；stack reset 可配置', 'UniformSampler low/high；intensity_range', '连续均匀采样', 'Arena Variation / stack task event',
    'Arena 默认范围 100–2000，默认关闭；stack domelight 分支要求 eval_mode 与 eval_type=light_intensity/all。单位遵循 USD 灯光设置。', (V+'light_intensity_variation.py', 'LightIntensityVariation'), (S, 'randomize_scene_lighting_domelight'))
add('外观、光照与相机', '灯光颜色', 'lightcolor', 'Arena build-time；stack reset 可配置', 'RGB low/high；color_variation', 'Arena RGB 均匀；stack 平衡通道扰动', 'Arena Variation / stack task event',
    'Arena 默认关闭；stack 要求 eval_mode 与 eval_type=light_color/all。两条路径的颜色分布不同。', (V+'light_color_variation.py', 'LightColorVariation'), (S, 'sample_random_color'))
add('外观、光照与相机', '方向光入射角', 'direction', 'build-time', 'azimuth / elevation [rad]', '方位角与仰角均匀采样', 'Arena LightDirectionVariation',
    '默认方位角 ±π，偏离正上方 0–80°；默认关闭，采样发生在构建阶段而非每次 reset。', (V+'light_direction_variation.py', 'LightDirectionVariation'))
add('外观、光照与相机', 'HDR 环境与背景', 'hdr', 'Arena build-time；stack reset 可配置', 'hdr_names；textures', 'HDR 注册池 / 纹理池离散选择', 'Arena HDRImageVariation / stack task event',
    'HDR 会影响照明和背景；Arena 默认关闭且需已注册 HDR。stack 要求 eval_type=light_texture/all。', (V+'hdr_image_variation.py', 'HDRImageVariation'), (S, 'randomize_scene_lighting_domelight'))
add('外观、光照与相机', '相机安装平移偏差', 'camera', 'reset', 'ROS 光学坐标 XYZ 偏移 [m]', '默认各轴 Uniform(-0.005, 0.005)', 'Arena CameraExtrinsicsVariation',
    '仅平移，不采样旋转、焦距或畸变；默认关闭。OpenArm 的 mounted-camera 更新会重设标定位姿，接入时须检查覆盖冲突。', (V+'camera_extrinsics_variation.py', 'CameraExtrinsicsVariation'))

props = [
('刚体摩擦与恢复', 'friction', 'static_friction / dynamic_friction；restitution；num_buckets', '均匀生成物理材质桶后分配', 'make_consistent 可保证动摩擦不大于静摩擦。', 'randomize_rigid_body_material'),
('质量', 'mass', 'mass_distribution_params；recompute_inertia', 'uniform / log_uniform / gaussian；add / scale / abs', 'Isaac Lab 可重算惯量；Arena ObjectMassVariation 默认绝对质量 0.05–2 kg，支持单个选中 body，默认关闭。', 'randomize_rigid_body_mass'),
('惯性张量', 'inertia', 'inertia_distribution_params；diagonal_only', 'uniform / log_uniform / gaussian；add / scale / abs', 'diagonal_only 默认 True；不是物体外观尺寸变化。', 'randomize_rigid_body_inertia'),
('质心偏移', 'com', 'com_range：XYZ [m]', '各轴均匀偏移', '改变质量中心，不移动可见网格。', 'randomize_rigid_body_com'),
('碰撞接触偏置', 'contact', 'rest_offset / contact_offset [m]', 'uniform / log_uniform / gaussian', '修改接触/静止偏置，受物理后端约束。', 'randomize_rigid_body_collider_offsets'),
('重力', 'gravity', 'gravity_distribution_params：XYZ [m/s²]', 'uniform / log_uniform / gaussian；add / scale / abs', 'PhysX 修改整个场景共享的重力；Newton 源码另有按环境路径，本次未运行验证。', 'randomize_physics_scene_gravity'),
('驱动器刚度与阻尼', 'gain', 'stiffness_distribution_params；damping_distribution_params', 'uniform / log_uniform / gaussian；add / scale / abs', '需要 articulation 与受支持 actuator；对不同 actuator 的后端写入路径不同。', 'randomize_actuator_gains'),
('关节物理参数', 'jointparam', 'friction；armature；lower_limit；upper_limit', 'uniform / log_uniform / gaussian；add / scale / abs', '关节摩擦、转子惯量和限位；不是关节初始位置。', 'randomize_joint_parameters'),
('固定肌腱参数', 'tendon', 'stiffness；damping；limit stiffness；limits；rest length；offset', 'uniform / log_uniform / gaussian；add / scale / abs', '仅适用于具有固定肌腱结构且后端支持的 articulation。', 'randomize_fixed_tendon_parameters'),
]
for name, kind, params, sampling, note, symbol in props:
    refs = [(E, symbol)]
    if symbol == 'randomize_rigid_body_mass':
        refs.append((V+'object_mass_variation.py', 'ObjectMassVariation'))
    add('动力学参数', name, kind, 'startup / reset（按后端与任务配置）', params, sampling,
        'Isaac Lab event；兼容时可用 AutoData profile', note+' 当前 OpenArm 未启用，未做本轮 GPU 验证。', *refs)

add('扰动与传感噪声', '外力与外力矩', 'force', 'reset / interval', 'force_range [N]；torque_range [N·m]', '各维均匀采样', 'Isaac Lab event',
    'interval 需 interval_range_s，AutoData profile 当前未暴露该字段；需任务 EventTermCfg。写入外力缓冲不等于单帧冲量。', (E, 'apply_external_force_torque'))
add('扰动与传感噪声', '随机速度推扰', 'velocity', 'reset / interval', 'velocity_range：线速度/角速度', '均匀采样并重设根速度', 'Isaac Lab event',
    '通过速度设置施加扰动；不是物理力。interval 同样需任务配置时间间隔。', (E, 'push_by_setting_velocity'))
add('扰动与传感噪声', '均匀观测噪声', 'noise', '观测计算 / NoiseModel', 'n_min；n_max；add / scale / abs', '逐元素均匀采样', 'Isaac Lab observation/noise 配置',
    '需启用观测 corruption；OpenArm 当前 enable_corruption=False。不能直接等同于 RGB 图像增强。', (L+'utils/noise/noise_cfg.py', 'UniformNoiseCfg'))
add('扰动与传感噪声', '高斯观测噪声', 'noise', '观测计算 / NoiseModel', 'mean；std；add / scale / abs', '逐元素高斯采样', 'Isaac Lab observation/noise 配置',
    '默认均值 0、标准差 1 是库默认值，不是 OpenArm 当前配置。', (L+'utils/noise/noise_cfg.py', 'GaussianNoiseCfg'))
add('扰动与传感噪声', '回合偏置与常量偏置', 'bias', 'reset 采样偏置；逐步叠加噪声', 'bias_noise_cfg；noise_cfg；sample_bias_per_component', '随机回合偏置 + 逐步噪声；也支持固定 bias', 'NoiseModelWithAdditiveBiasCfg',
    'ConstantNoiseCfg 本身是确定性偏置，只有偏置采样配置才是随机化。', (L+'utils/noise/noise_cfg.py', 'NoiseModelWithAdditiveBiasCfg'), (L+'utils/noise/noise_cfg.py', 'ConstantNoiseCfg'))
add('扰动与传感噪声', '执行器随机延迟', 'delay', 'actuator reset 采样 / 每步应用', 'min_delay；max_delay [物理步]', '整数区间随机延迟', 'DelayedPDActuatorCfg',
    '需要显式使用 DelayedPDActuator，OpenArm 当前未配置；不等于相机/网络延迟。', (L+'actuators/actuator_pd_cfg.py', 'DelayedPDActuatorCfg'))

add('几何、实例与地形', '刚体尺寸缩放', 'scale', 'usd：仿真播放前', 'scale_range；各轴独立或等比', '连续均匀采样', 'Isaac Lab usd event；AutoData profile 不支持 usd',
    '需 replicate_physics=False；禁止仿真运行中调用，不支持直接缩放 articulation。profile 中固定 scale 不算随机化。', (E, 'randomize_rigid_body_scale'))
add('几何、实例与地形', '多资产实例抽样', 'asset', '构建 / 克隆阶段', 'RigidObjectSet；MultiUsdFileCfg / MultiAssetSpawnerCfg', '实例池选择 / heterogeneous cloning', 'Arena / Isaac Lab 场景配置',
    '不是每回合自动换 USD；底层 wrapper 的 random_choice 已弃用，应使用场景 random_heterogeneous_cloning。', (B+'isaaclab_arena/assets/object_set.py', 'RigidObjectSet'), (L+'sim/spawners/wrappers/wrappers_cfg.py', 'MultiUsdFileCfg'), (L+'scene/interactive_scene_cfg.py', 'InteractiveSceneCfg'))
add('几何、实例与地形', '焦点物体实例切换', 'asset', 'reset', 'asset_cfgs；out_focus_state；pose_range', '每组随机选一个实例进入工作区', 'stack 专用 rigid-object 集合事件',
    '未选实例移到 out_focus_state；需要多实例资产集合，不能直接作用于单个 cube。', (S, 'randomize_rigid_objects_in_focus'))
add('几何、实例与地形', '地形类型与粗糙度', 'terrain', '地形生成阶段', 'sub_terrains；proportion；difficulty_range；seed', '地形类型/难度随机 + 几何噪声', 'TerrainGeneratorCfg',
    '包含均匀高度场与随机网格等具体子地形；不等于 OpenArm 桌面材质随机化。', (L+'terrains/terrain_generator_cfg.py', 'TerrainGeneratorCfg'), (L+'terrains/height_field/hf_terrains_cfg.py', 'HfRandomUniformTerrainCfg'), (L+'terrains/trimesh/mesh_terrains_cfg.py', 'MeshRandomGridTerrainCfg'))

add('AutoData 轨迹增强', '子任务边界抖动', 'boundary', '源片段准备 / 池刷新', 'subtask_term_offset_range；subtask_start_offset_range [帧]', '离散整数采样', 'AutoData TaskDescriptor',
    'SkillGen 起止均可抖动；其他算法主要抖动终点。当前 first_subtask_start_offset_range 实现只取下界，不能宣称该字段完整区间采样。属于数据增强。', (A+'autodata_core/data_generator.py', 'randomize_subtask_boundaries'))
add('AutoData 轨迹增强', '源演示随机选择', 'selection', '每个子任务选源', 'selection_strategy=random', '源池均匀随机', 'AutoData TaskDescriptor',
    '源池只有一条时不会产生多源多样性。属于数据增强，不改变物理域参数。', (A+'autodata_core/selection_strategy.py', 'RandomStrategy'))
add('AutoData 轨迹增强', '物体近邻 top-k 抽样', 'selection', '每个子任务选源', 'nearest_neighbor_object；nn_k；pos_weight；rot_weight', '按物体位姿排序后 top-k 均匀选择', 'AutoData TaskDescriptor',
    'k=1 时选源不随机；k 截断到可用源片段数量。', (A+'autodata_core/selection_strategy.py', 'NearestNeighborObjectStrategy'))
add('AutoData 轨迹增强', '机器人距离 top-k 抽样', 'selection', '每个子任务选源', 'nearest_neighbor_robot_distance；nn_k', '按机器人相关位姿距离排序后 top-k 选择', 'AutoData TaskDescriptor',
    '不是在全池等概率随机；受距离排序与可用源数量约束。', (A+'autodata_core/selection_strategy.py', 'NearestNeighborRobotDistanceStrategy'))
add('AutoData 轨迹增强', '执行动作噪声', 'trajectory', '每步执行；插值阶段可开关', 'action_noise；apply_noise_during_interpolation', '高斯噪声', 'AutoData subtask + embodiment adapter',
    '单臂实现对六维 pose action 加噪、夹爪直通，可裁剪；双臂实现对位置和四元数分量加噪，两者不能混写成同一种姿态噪声。', (A+'autodata_interfaces/embodiments/single_arm_embodiment_adapter.py', 'DeltaPoseIKSingleArmAdapter'), (A+'autodata_interfaces/embodiments/bimanual_embodiment_adapter.py', '_add_noise'))
add('AutoData 轨迹增强', '规划轨迹执行噪声', 'trajectory', '规划完成后的 waypoint 执行', 'motion_noise_scale', '规划 waypoint 携带执行噪声幅度', 'AutoData SkillGen / planner profile',
    '不是随机化 cuRobo 求解器或障碍物；噪声最终由 embodiment 执行路径施加。', (A+'autodata_core/algorithms.py', 'SkillGen'), (A+'autodata_interfaces/motion_planners/curobo/curobo_planner_cfg.py', 'CuroboPlannerCfg'))
add('AutoData 轨迹增强', '双臂协调位姿扰动', 'coordination', '协调变换构造', 'coordination_scheme_pos_noise_scale [m]；rot_noise_scale [rad]', 'XYZ 与逐轴 Euler 均匀噪声', 'AutoData task constraint',
    '位置平移与欧拉角扰动叠加到协调变换；只有声明了相应约束的任务生效。', (A+'autodata_core/transforms.py', '_add_uniform_noise_to_pose'))


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    tree = ast.parse((ROOT/E).read_text())
    public_events = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                     and not n.name.startswith('_') and n.name != 'reset_scene_to_default'}
    covered = {s['symbol'] for row in ITEMS for s in row['sources'] if s['path'] == E}
    assert public_events == covered, {'missing': sorted(public_events-covered), 'extra': sorted(covered-public_events)}
    variations = {n.name for path in (ROOT/V).glob('*_variation.py')
                  for n in ast.parse(path.read_text()).body
                  if isinstance(n, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id in
                     ('BuildTimeVariationBase', 'RunTimeVariationBase') for b in n.bases)}
    covered_variations = {s['symbol'] for row in ITEMS for s in row['sources']}
    assert variations <= covered_variations, variations-covered_variations
    catalog = {'date': '2026-10-16', 'scope': '当前 AutoData 工作树 + 内嵌 Arena + 其 Isaac Lab 稳定通用接口及 stack 扩展；排除根目录独立 Arena、实验 Warp 接口和 GR00T 外部仿真生态',
               'validation': '本轮源码清点；示意图非 GPU 实测。此前仅 OpenArm XY reset 已实测。',
               'coverage': {'common_mdp_randomized_events': len(public_events), 'concrete_arena_variations': len(variations),
                            'method_families': len(ITEMS)},
               'integration_limits': [
                   'AutoData profile 的事件 mode 仅 startup/reset/interval；不能配置 usd/prestartup。',
                   'profile.add 未暴露 interval_range_s；profile.override 仅更新 params，不能覆盖事件时间间隔。',
                   'Arena VariationBaseCfg.enabled 默认 False；build-time 与 per-reset 不同。',
                   '现有 OpenArm 默认只随机 XY；观测 enable_corruption=False；相机更新与外参 Variation 需检查覆盖。',
                   '纹理需要 Replicator、纹理文件及匹配网格路径；存在 API 不代表任意资产可直接运行。',
                   '尺寸与实例变化后须核对 cuRobo 碰撞模型；默认 spawn 状态与 reset 物理状态也须一致。'],
               'not_claimed': ['相机旋转/焦距/内参/镜头畸变随机化未找到本范围通用实现',
                               '粗糙度/金属度/透明度随机化未找到本范围通用封装',
                               'RGB 曝光/运动模糊/遮挡增强未找到 AutoData 配置入口',
                               '固定场景覆盖、reset_scene_to_default、常量偏置、随机种子本身不计独立域随机化'],
               'items': ITEMS}
    (output/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    print(json.dumps(catalog['coverage']))


if __name__ == '__main__':
    import sys
    build(Path(sys.argv[1]))
