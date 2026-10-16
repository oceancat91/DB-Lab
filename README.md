# MongoDB 在线问卷系统 · Lab4 第一阶段

Lab4 是项目根目录。本项目按 [WORKFLOW.md](WORKFLOW.md) 和 [AGENTS.md](AGENTS.md) 顺序实施，只覆盖《大作业一第一阶段》。当前 S0–S7 全部验收通过，第一阶段实验已完成；已执行验收结果见 [测试报告](docs/TEST_REPORT.md)，实际状态见 [progress.json](progress.json)。

## 功能与语义

注册和登录后，用户创建自己的问卷，配置单选、多选、文本、数字题及校验和条件跳转，再发布分享链接。发布后题目及匿名/重复策略固定，仍可调整截止时间或关闭。填写者必须登录；匿名表示向创建者隐藏账号，服务端保留私有判重身份。

多选支持最少/最多/精确数量，文本按 Unicode 码点计长度，数字检查有限值、范围和整数。跳转来自问卷配置，服务端按唯一优先级选择首条命中规则，只允许向后跳。返回修改早期答案会清除后续回答；最终提交重新校验全部路径。提交前不自动保存草稿。

允许重复填写与网络重试分别处理：新一轮填写使用新请求编号，网络重试复用原编号。MongoDB 事务将问卷受理条件写入与答卷插入绑定，数据库唯一索引处理并发判重。统计区分成功提交次数和去重人数，空答/跳过不补零，匿名结果不返回账号或私有身份。设计细节见 [DECISIONS](docs/DECISIONS.md)。

## 运行

需要 conda、MongoDB 6.0或兼容版本，且 mongod 在 PATH。全部命令在本文件所在目录的 PowerShell 执行。Python依赖由 conda 管理，不使用 pip。已验证版本见 [环境说明](docs/ENVIRONMENT.md)。

```powershell
conda env create --file environment.yml --yes
conda activate lab4-survey
python scripts/configure_env.py
.\scripts\start_mongo.ps1
python scripts/init_mongo.py --output results/local-environment.json
python scripts/init_db.py
python -m uvicorn survey_app.main:app --host 127.0.0.1 --port 8004
```

打开 http://127.0.0.1:8004/ ，注册新账号后创建问卷。密码至少8字符。mongod独立绑定127.0.0.1:27084，副本集lab4rs，数据在本目录.runtime/mongo，业务库lab4_survey；没有使用旧Lab的27017服务。初始化会校验实际数据目录归属，不会清空既有数据库。应用在启动时也会检查Schema及索引。

`.env` 由脚本生成随机会话密钥，已有文件不覆盖。配置变量为 MONGODB_URI、MONGODB_DATABASE、SESSION_SECRET、COOKIE_SECURE；环境变量优先于.env。使用其他端口或副本集时，启动及初始化分别传入 `-Port / -ReplicaSet` 和 `--port / --replica-set`，并同步连接串。本地实验使用HTTP与回环无认证实例，公网部署需要另行配置认证、TLS和访问控制。

本地网页需要应用进程持续运行；若出现 `ERR_CONNECTION_REFUSED`，先确认上述uvicorn命令正在运行，启动后刷新浏览器。可访问 http://127.0.0.1:8004/health 检查应用及数据库连通；重启电脑后需要重新启动本地服务。

停止应用按Ctrl+C。数据库仅在确认是本项目进程后停止；数据保留在.runtime。若已有同名conda环境，使用 `conda env update --file environment.yml`，不要盲目重建环境。

## 验证

另开已激活相同conda环境的PowerShell：

```powershell
python -m pytest tests --evidence results/local-run.json -q
python scripts/check_schema.py --output results/local-schema.json
python scripts/check_workflow.py
```

pytest自动新建lab4_test_api_UUID测试库，结束只清理该精确新库。业务数据和会话全部持久化到真实MongoDB，不使用关系数据库或文件替代。流程检查器只核对文档/状态/证据结构，不能代替业务测试。Starlette在固定版本中提示TestClient/httpx兼容路径未来弃用，当前实测正常；浏览器与真实HTTP另行验证。

## 已执行验收

- 第一阶段26组用例全部通过，见 [测试报告](docs/TEST_REPORT.md)。
- 全量245项测试通过；独立新conda环境再次245/245，Schema43/43，23步真实HTTP及应用重启持久化通过。
- 浏览器真实验证创建、四类校验、回改跳转、提交回执、匿名明细、整卷/单题统计及关闭。
- BSON备份恢复后3份答卷/2人、均值15及原回执一致，见 [恢复证据](results/S7/backup-restore.json)。
- 四种10请求同时起跑用于验证并发正确性；此结果不代表容量或生产性能指标。

复现发生过Windows脚本编码/清理包装器错误，原始失败和补救证据保留；固定依赖的Starlette/httpx弃用warning已解释。详情见 [干净环境复现](results/acceptance/reproduction.md)。

## 项目文件

- `survey_app/`：FastAPI应用、MongoDBSchema、认证、问卷/校验/跳转、提交/统计和原生HTML/CSS/JS页面。
- `tests/`：独立合成数据、真实数据库与并发验收；`scripts/`：环境、MongoDB、Schema及流程工具。
- [需求映射](docs/REQUIREMENTS.md)、[业务决策](docs/DECISIONS.md)、[测试计划](docs/TEST_PLAN.md)。
- [系统与使用说明](docs/SYSTEM.md)、[数据库设计](docs/DATABASE.md)、[API](docs/API.md)、[关键逻辑](docs/LOGIC.md)、[环境](docs/ENVIRONMENT.md)。
- [第一阶段完成报告](docs/REPORT_STAGE1.md)、[测试报告](docs/TEST_REPORT.md)、[基线与恢复说明](docs/BASELINE_STAGE1.md)。
- [实验日志](docs/EXPERIMENT_LOG.md)、[AI使用记录](docs/AI_USAGE.md)及`results/S1`至`results/S7`、`results/acceptance`实际阶段证据。
- [源作业Word](大作业一第一阶段.docx)和`references/`来源副本。

`.env`、`.runtime/`、环境、Git内部文件及缓存不属于提交内容。`results/Lab4/`是历史重复包，不作为入口或当前交付物；Lab1–Lab3是独立实验，本项目未修改。最终提交四类材料为可运行代码/配置、设计说明、测试用例与真实结果、完整报告；S7交付门禁已通过，详见 [最终门禁](results/S7/gates.md)。

## 打包与已知范围

交付包为 `dist/Lab4-stage1.zip`，解压后入口是Lab4/README.md。配套 `.zip.sha256` 校验压缩包，`results/S7/manifest.json`记录每个提交文件的实际字节摘要；清单和打包检查记录不对自身递归求摘要。重建交付包可运行：

```powershell
python scripts/package_stage1.py
```

包中保留源Word、规范、代码、文档、真实测试/失败记录及合成夹具；排除本机配置、运行时数据库/备份、Git内部文件、环境和缓存。生产认证/TLS、容量压力、其他操作系统/浏览器与完整移动设备适配未验收。当前统计加载可能使滚动位置变化，人为畸形百分号分享URL尚无友好提示；正常生成链接完整链路已通过，详见 [代码复核](results/acceptance/final-code-review.md)。
