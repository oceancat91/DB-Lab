# S7 第一阶段交付门禁

2026-10-16 Asia/Shanghai；Codex主agent逐项复核，内部agent分别编写/复核报告和真实恢复演示。以下为实际证据支持的项目验收，不预测课程分数。

- G7.1 PASS：Word四类材料齐备。survey_app后端及原生页面、db.py Schema/索引、environment.yml/.env.example和README可运行说明；SYSTEM/DATABASE/API/LOGIC实质设计说明；TEST_PLAN及26组TEST_REPORT和真实逐参数结果齐备。S6新conda/源码副本/独立MongoDB已真实复现245/245、Schema43/43、23步HTTP及新进程重启持久化。见submission-review.json、delivery-review.md与acceptance证据。
- G7.2 PASS：REPORT_STAGE1覆盖目标、系统/MongoDB设计、跳转/校验、AI过程、测试结果及问题/修复九项。AI_USAGE保留提示和生成/修改/验证记录；agent贡献与未提供的学生本人工作明确区分，未代填姓名学号、理解或分数。报告跨日说明保留旧业务实测日期。
- G7.3 PASS：BASELINE固定受验业务commit e7255c3332b3492691eff27a0a5ce7e395127422，21个应用/测试/依赖文件与基线一致（区分CRLF/LF）。Schema1/发布1、合法6题三答卷夹具保存。真实BSON双UUID恢复后五集合文档、strict/error Schema和索引相等，3份2人均值15、三原回执重放且无新写；双库精确清理PASS，sessions为空不冒称会话恢复。归档预检156文件已实际解压，清单摘要全匹配、所有当前文档链接和解压后workflow退出0，实际本机会话密钥/运行时/Git/缓存不入包。见backup-restore.json、code-baseline.json、unpacked-preflight.json及package-check.json。

完成状态等最后元数据变更后，使用同一package_stage1.py重建最终ZIP并再次解压核对；清单记录最终实际字节，清单/打包检查自身排除递归摘要，ZIP摘要单独在dist/*.sha256。预检摘要明确是旧元数据包，不冒充最终ZIP摘要。dist/verification.json记录最终解压核验，不进入ZIP以避免递归。

保留S7初次结构1ERROR（尚未落盘的BASELINE链接），补齐后0ERROR/0WARN；原失败未覆盖。所有阶段通过意味着第一阶段项目交付完成。未验收公网部署、容量性能、其他OS/浏览器和完整移动适配；统计焦点/滚动及人为畸形URL的非阻塞限制已在报告记录。学生本人工作说明须本人据实补充，未由AI虚构。
