# 第一阶段环境与隔离

2026-10-15 已从 `environment.yml` 使用 conda 新建 `lab4-survey`，未使用 pip。实际版本与连通结果见 [S1 环境证据](../results/S1/environment.json)。本机 Windows、Python 3.11.17、MongoDB 6.0.29、FastAPI 0.143.1、PyMongo 4.19.0；其他直接依赖版本已写入 environment.yml。

本项目以 Lab4 为根目录。`results/Lab4/` 是历史材料，已从版本提交排除，不参与应用导入或运行。参考规范原样副本在 `references/`，仅供核对，项目行为规范为根目录 AGENTS。

本地 MongoDB 仅绑定 127.0.0.1:27084，副本集 `lab4rs`，数据目录 `.runtime/mongo`；没有使用已有 27017 服务或任何 Lab 数据。业务库 `lab4_survey`，环境能力检查库 `lab4_environment`，自动化测试只允许 `lab4_test_` 前缀的独立新库；复现测试另建测试库。运行时数据库、日志、PID、环境和 `.env` 不提交。

在已安装 conda 和 MongoDB 且 mongod 在 PATH 的 Windows PowerShell 中，本次已执行的顺序为：

```powershell
conda env create --file environment.yml --yes
conda activate lab4-survey
python scripts/configure_env.py
.\scripts\start_mongo.ps1
python scripts/init_mongo.py
python scripts/check_workflow.py
```

`configure_env.py` 不覆盖已有配置，随机生成 SESSION_SECRET 且不输出；`.env.example` 不含真实密钥。启动脚本用隐藏进程运行，端口已使用时不抢占、不终止其他进程。初始化脚本先确认数据库进程的 dbPath 恰为本项目路径，再初始化副本集；不匹配则退出。环境探针实际执行 MongoDB 事务并回读，之后仅删除自身 UUID 探针记录。

应用连接与配置均从环境变量/`.env` 读取。MongoDB 本地实验实例未启用认证，限制为回环访问；本说明不宣称具备公网部署条件。COOKIE_SECURE=false 仅供本地 HTTP，正式 HTTPS 应配置 true。

安装中出现一次 conda-forge SSL EOF，conda 自动重试后成功完成且导入/事务验证通过；保留此说明，不修改系统 SSL 校验。conda 的 conda-pypi 推广提示没有被执行。环境检查仅证明能力，不表示课程业务通过。
