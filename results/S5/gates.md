# S5 门禁审阅

2026-10-15 Asia/Shanghai；Codex主agent实际运行，内部agent分别实现统计/页面和独立测试。

- G5.1 PASS：真实MongoDB提交专项46项通过，含四类型校验API复测、J05b路径伪造/漏答/旧版、A02/A03认证及所有权、匿名白名单、重复与幂等。非法提交无答卷且gate不增加；独立应用实例重读成功答卷。见submission-tests.json/txt。
- G5.2 PASS：四种Barrier(10)同时起跑：多用户10成功/10答卷；同账号禁重复1成功9冲突/1答卷；同ID10成功回执同一ID且仅一次新建；允许重复10成功/10答卷。真实事务调度验证关闭及截止的gate先后顺序；MongoDB非法文档插入失败使gate回滚。截止等于边界为同一数据库表达式中将截止操作数绑定$$NOW的探针，不冒称两个独立命令精确同毫秒。预期与对账详见JSON的submission_experiments。
- G5.3 PASS：三份合法API提交、两名用户手算夹具，单选A2次/1人、B1次/1人，多选X/Y各2次、数字2份均值15。整卷/单题一致，空答/跳过/零数据和匿名权限通过；最大有限double均值回归通过。见full-tests.json中统计9项。

全量245/245 PASS，退出0，真实测试库精确清理PASS。Schema CLI修复后43/43 PASS见schema-cli-check.json。实际浏览器成功回执、整卷/单题均值8及匿名明细已检查，数据库一答卷/gate1一致，见browser.json及对应jpg/txt。浏览器控制台无error。

保留mean-diagnostic.json中的初始溢出诊断，以及Schema旧CLI忽略--help导致的额外真实运行；原S2证据已恢复。Starlette/httpx弃用提示保留，固定依赖当前兼容，独立浏览器真实HTTP通过。10并发只证明正确性，不宣称容量/性能指标。学生本人贡献未代填。
