# 第一阶段基线与恢复说明

本文件记录第一阶段业务代码、Schema、合成夹具、恢复方法与证据。恢复演示实测日期为 2026-10-16，时区 Asia/Shanghai；各阶段最终状态以 progress.json 及门禁证据为准。

受验业务代码提交为 `e7255c3332b3492691eff27a0a5ce7e395127422`。应用、测试及依赖定义共 21 个文件与该提交按 CRLF/LF 规范化后相符，证据见 [代码基线](../results/S7/code-baseline.json)。Schema 版本为 1；第一阶段每个问卷只发布一次，发布版本为 1。S7 新增说明、夹具及交付工具的最终字节摘要由打包清单另行记录。

合成[夹具](fixtures/statistics.json)取自 `tests/test_statistics.py` 的六题问卷：单选、多选、文字、必答数字前的 gate、数字及可选 end；gate=skip 跳至 end。三份成功答卷由两名填写者提交，数字有效值 10、20，期望均值 15；第三份合法跳过数字。夹具只包含合成问卷与答案，不含账号、会话或私有哈希。固定数据种子为 20261015，运行隔离标识和账号密码另用 UUID/安全随机值生成。

恢复演示命令为 `python scripts/backup_restore_demo.py`。先按 README 配置 conda 环境和本地 `.env`，启动 `scripts/start_mongo.ps1`，再运行 `python scripts/init_mongo.py --output results/local-environment.json` 核验项目实例。脚本仅自行创建本次两个 UUID 隔离库，不接受任意源库、目标库或覆盖参数。通过现有 SurveyService 注册合成账号、发布问卷并真实提交三份答卷，在静止源库以同一个 snapshot 事务读取五个集合，导出 BSON 文档流，再在另一个全新空库使用基线代码 `initialize_schema` 重建 Schema/索引并恢复 BSON。`schema-indexes.json` 留存源定义供对账，不作为 Schema 恢复输入；恢复依赖 BSON 数据和当前基线代码二者。

脚本核验文档等值、strict/error Schema、全部索引、统计及原请求的幂等回执；最后只清理本次确实创建的精确库名。备份文件留在被排除出提交包的 `.runtime/backup-demo/` 中，其中含密码及请求私有哈希，不能复制到报告、日志或交付包。本演示不创建 sessions 文档，不证明会话恢复；也不证明在线持续写入期间的备份操作或任意历史 Schema 的兼容性。

恢复演示实测 PASS，退出码 0，时间 2026-10-16 13:48:47–13:48:49 +08:00，证据见[恢复结果](../results/S7/backup-restore.json)和[本次环境](../results/S7/restore-environment.json)。五集合文档数依次为 users=3、sessions=0、surveys=1、survey_versions=1、responses=3，恢复后逐文档等值，Schema/索引相同；成功提交 3 次、去重填写 2 人、数字均值 15，整卷与六个单题统计一致。三个原请求均返回原 ID/时间且 replayed=true，未新增答卷或推进 gate；三个恢复账号的密码校验成功。本次两个精确 UUID 库均已清理，BSON 备份文件保留。本脚本再次运行会产生新隔离库并归档已有结果，不删除失败证据。

回归依据为 [测试报告](TEST_REPORT.md)、[S6 门禁](../results/acceptance/gates.md)及[干净环境复现](../results/acceptance/reproduction-final.json)。其中 S6 的 2026-10-15 历史时间保持原样，S7 续作使用实际运行时间。干净复现是在同一主机的新 conda 环境、干净源码归档和独立 MongoDB 进程完成，不代表另一个操作系统。

提交包命令为 `python scripts/package_stage1.py`，输出 `dist/Lab4-stage1.zip`，排除 `.env`、`.runtime`、`.git`、缓存及历史嵌套包。`results/S7/manifest.json` 记录提交文件大小和 SHA-256，`results/S7/package-check.json` 记录 ZIP 核验结果；本文件不代替最终清单及包核验。
