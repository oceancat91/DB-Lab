# TC-E02 干净环境复现

结论：PASS。执行日期2026-10-15，Asia/Shanghai。最终事实以 [reproduction-final.json](reproduction-final.json) 为准。

从提交 `e7255c3332b3492691eff27a0a5ce7e395127422` 使用 `git archive` 导出独立源码；归档105个文件与解压副本逐字节摘要一致，见 [源码核对](reproduction-source.json)。没有把Git的LF字节与原工作树CRLF字节声称为同一个原始摘要。应用源码和测试没有修改。

新建conda环境 `lab4-survey-repro-be6b0d`，完全由归档 `environment.yml` 安装，无pip。真实安装退出0。Python 3.11.17，MongoDB 6.0.29；FastAPI、PyMongo及其余直接依赖的实际版本见最终JSON及 [环境探针](reproduction-environment.json)。隔离使用27085/lab4repro、8005和副本 `.runtime/mongo`；主27084/8004及旧Lab未操作。配置脚本生成新随机会话密钥，秘密未输出或复制到证据。

实际命令顺序（在干净副本、选定新环境内）：

```powershell
conda env create --file environment.yml --name lab4-survey-repro-be6b0d --yes
python scripts/check_workflow.py
python scripts/configure_env.py
.\scripts\start_mongo.ps1 -Port 27085 -ReplicaSet lab4repro
python scripts/init_mongo.py --port 27085 --replica-set lab4repro --output results/acceptance/reproduction-environment.json
python scripts/init_db.py
python scripts/check_schema.py --output results/acceptance/reproduction-schema.json
python -m pytest tests --evidence results/acceptance/reproduction-tests.json -q
python -m uvicorn survey_app.main:app --host 127.0.0.1 --port 8005
```

启动Mongo在新环境安装完成前由README的PowerShell脚本执行；Python验证命令全部使用新环境解释器。配置在生成后仅调整副本的端口、副本集和数据库，未更改依赖定义。

- [全部自动化测试](reproduction-tests.json)：245/245 PASS，真实MongoDB，UUID测试库精确清理PASS；[原始输出](reproduction-tests.txt)保留Starlette/httpx弃用警告，未屏蔽。
- [Schema](reproduction-schema.json)：43/43 PASS，UUID测试库精确清理PASS。
- 真实HTTP共23步：注册/登录、四题型及跳转配置、发布、逐题预检、成功提交、整卷/单题统计及匿名明细、关闭后410。数字均值手算为10且实际为10。
- 终止经PID命令核验的自有应用进程26896，启动新进程19376后，旧会话、统计、答卷及相同请求回执均保持；应用最终已关闭。

安装包装器的前三轮失败保留在 `reproduction-conda-*-attempt*.json/txt`：先发生PowerShell原生stderr误判，随后定位PowerShell5按ANSI读取UTF-8无BOM计划破坏中文路径。修正包装器的UTF-8读取及相对参数后，conda真实安装成功；没有修改SSL校验或依赖。

首轮业务复现全通过，但清理包装器把PowerShell5的GBK进程命令输出当作UTF-8解码，最终exit1。原 [reproduction.json](reproduction.json)、[stderr](reproduction-runner-error.txt) 完整保留。仅修正验收工具的输出编码后，重新核验PID17332命令、27085端口、副本集和精确dbPath，实际优雅关闭并确认PID退出；[补救证据](reproduction-cleanup-repair.json) 为PASS。没有因清理工具故障重跑或改写245项测试、Schema或HTTP原始结果。复现数据库文件保留在副本 `.runtime/mongo`。

限制：这是同一Windows主机上的新conda环境、源码树、MongoDB实例与数据目录；复用了已安装的MongoDB可执行文件，未声称全新操作系统或容器验证。此记录仅覆盖TC-E02，S6其他门禁由主agent汇总。
