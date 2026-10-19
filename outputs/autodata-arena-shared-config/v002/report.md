# AutoData / Arena 共享配置落地 v002

材料核对：2026-10-13（Asia/Shanghai）。

本版已实现根目录配置、无仿真依赖解析器、公共环境工厂、AutoData 进程内注册入口和 Arena 外部环境适配器。维护入口为 `config/openarm/experiment.json`，操作说明为 `config/README.md`；完整本版实现快照见 `implementation.zip`。

## 检查与回退

顶层 Arena 没有已跟踪源码修改，只有未跟踪 deliveries。两份旧交付目录完整迁移至根仓库 `workspace-overlays/arena-deliveries/`，包含旧配置、环境/资产副本和验证证据；没有 reset、clean、提交切换或补丁应用。Arena 工作树现在干净。迁移后文件清单和哈希记录于 evidence.json。旧归档从 Git 排除，仅保存在当前机器。

AutoData 现有修改及其内嵌依赖安装改动保持原样。AutoData 当前 HEAD 为 945806ed1cd85cc8734ddeaae196aca891fd06bf，与根仓库记录的版本有已有偏差；本次没有更改子模块提交。以实际工作树哈希记录来源，不把 HEAD 当成完整状态。

## 架构与实现

根配置 common 声明动作缩放、reset 范围、成功阈值和生成种子。两端调用同一个 make_env_cfg，直接使用 AutoData 的唯一 OpenArm 环境/资产源码。生成端通过官方 env_module 接口在当前进程替换 Gym 配置工厂；评估端通过官方 external_environment_class_path 加载根仓库管理的适配器。Arena 源码无需修改。

解析器派生 AutoData task / embodiment / env_profile 原生配置并构建两侧命令。动作缩放和生成 seed 禁止在原生模板重复定义；未知公共字段、非法数值、冲突 profile 和预留评估参数启动前失败。评估默认 zero_action 仅用于检查入口，不代表训练策略评估。模型策略可使用外置 TorchScript adapter。

每次解析保存输入哈希、工作树环境/资产及适配器哈希、两上游 HEAD、任务参数指纹、有效 seed 和 argv。运行时检查源码漂移及真实导入路径。task_contract_hash 表示公共参数相同；源码语义一致还须核对 source_hashes，二者不能互相替代。

现有生成逻辑负责 recorder、成功检查提取、失败筛选；外置评估适配器负责当前 Arena 的终止接口、PhysX 和夹爪索引兼容。回合时限、策略和评估种子只属于 evaluation。此前示例中的“正夹爪值闭合”与已有源码不符，本版明确为负值闭合，v001 历史包不改写。

## 验证与限制

7 项标准库主机单元测试全部通过：动作缩放与 seed 派生，公共 reset/成功阈值传播，两模式参数隔离，未知/非法参数拒绝，重复/冲突配置拒绝，双侧命令计划。两种 resolve 均实际生成快照。新增 Python 文件完成 AST 语法检查。

没有执行 GPU 仿真、训练或上游容器测试，没有验证数据集标注或回读。现阶段支持 OpenArm 左臂 7D 相对 IK 与当前固定场景成员；新增物体、其他机器人和任意 profile scene/event 补丁显式不支持。GPU 运行要求用户已手动启动并配置好相应容器，且完整工作区挂载可访问。新架构仍需分别完成回放、成功规则、相机、动作、reset、回合计数和 HDF5 验收；历史运行记录不能替代本版运行验证。

用户明确本次不需要飞书与 ChatGPT 交付，仅本地封装。本包没有上传，也没有发送消息或公开发布。
