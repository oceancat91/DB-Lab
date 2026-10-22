# S6 集成与复现门禁

2026-10-15 Asia/Shanghai；主agent审阅原始JSON/源码/截图，内部agent执行独立环境复现、26组文档映射及代码复核。参与者均为AI，未代填学生本人贡献。

- G6.1 PASS：TEST_REPORT逐26组给出步骤、具体输入、预期、实际、PASS及原始JSON/参数化源码定位。业务24组+页面E01+复现E02全部通过；已解释Starlette/httpx弃用warning、S4旧进程故障及复现清理包装器故障，原始记录保留。
- G6.2 PASS：browser-e01.json串联同一合成问卷的S4创建/发布/回改校验、S5真实提交与整卷/单题/匿名明细、S6关闭后分享拒绝；数据库1答卷且closed。reproduction-final.json为新conda环境、git归档干净副本、独立27085/lab4repro与8005的真实复现；245测试、43Schema、23HTTP流程步骤通过，进程26896→19376后会话/答卷/统计/幂等回执保持。复用了同主机MongoDB二进制，不声称全新OS。
- G6.3 PASS：真实MongoDB测试精确UUID库清理PASS；四种10并发、权限、匿名、统计夹具均通过。单元校验不冒称全部是数据库集成；DB121故障/调度控制不以mock替代真实事务。源码/环境审计见reproduction-evidence-audit.json。

原reproduction.json exit1的原因是Windows命令行GBK输出被UTF8解码，业务本已全部通过。仅清理补救后，验证自有PID17332/端口27085/精确dbPath，实际优雅关闭并检查进程退出；最终证据与原失败分开保留。流程结构检查仅核对记录。

未覆盖范围：完整新OS/其他浏览器与手机、真实公网部署、容量性能。统计加载时焦点/滚动及人为畸形百分号URL的非阻塞健壮性限制见final-code-review.md。不以此推断全部异常输入或生产安全均通过。
