# S3 门禁审阅

2026-10-15，Asia/Shanghai。执行及审阅：Codex 主 agent；内部 agent 提供独立测试和代码审阅。

- G3.1 PASS：真实 MongoDB 管理测试首次 23/23、边界修复后 35/35 通过，退出 0。覆盖 A01、A02 管理/填写入口、A03 已实现管理接口、Q01–Q03，含数据库读回及仅清理新 UUID 测试库。证据：admin-tests-repaired.json、admin-tests-repaired.txt；首次结果保留。
- G3.2 PASS：发布链接稳定、发布快照冻结、revision 竞争、未登录/越权和非法发布均有断言。简单管理页面已实现，JS 语法与静态引用检查通过；完整浏览器链路留到 S4/S6，未声称提交/统计已实现。

审阅修复：异常 Origin 返回403；流式请求超1MiB停止读取；日期拒绝数字时间戳，只接受有时区的ISO文本或null。新增回归均通过。

WARN说明：Starlette 提示 TestClient 对 httpx 的兼容路径未来弃用，现固定版本实际35项通过。保留原始提示，不隐藏；S6另用真实HTTP和浏览器验证。流程检查器只检查记录结构。
