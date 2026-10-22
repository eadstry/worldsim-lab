# OpenPI 下载适配

首次 OpenPI 构建的官方 PyPI 大文件下载在本机持续缓慢。此入口继续调用 Arena
98866596fd024d96c874fe6fb95ae916d1133629 的原服务包装器，只在其临时 OpenPI
构建副本中，将 files.pythonhosted.org/packages/ 地址替换为清华 PyPI 镜像。
模型配置、检查点、OpenPI 提交、包版本和所有锁定哈希保持不变；uv 仍校验包哈希。
解析后的完整 TOML 除该 URL 前缀外必须一致，否则拒绝构建。

需要 Python 3.11+、已配置的 Docker/GPU 环境，以及用户对首次镜像和权重下载的确认。
不得据此自动准备系统驱动或仿真依赖。原包装器仍负责镜像构建、GPU 服务启动、缓存
所有权清理和原有参数。已有镜像会按原包装器复用，不强制重建或清理缓存。

在共享队列的前台编排中，用本入口替代直接调用服务包装器：

    /path/to/python serve.py --arena-root /path/to/IsaacLab-Arena \
      --evidence-directory /fresh/local/run/download-routing -v pi05 -p 8000

证据目录必须尚不存在。临时 Docker CLI 适配只作用于本进程及其子进程，不改全局
Docker、pip 配置或上游工作树。构建前验证临时副本的实际 OpenPI HEAD；下载路由
回执和原 uv.lock 留在本机运行目录。模型服务与评测仍须按项目共享队列协调生命周期。

主机测试只验证 URL/哈希边界、错误来源拒绝和 Docker 参数透传，不证明模型服务或
策略成功。服务就绪、真实回合、JSONL、规范结果和录像须单独进行运行时验证。
