# S2 门禁审阅

日期：2026-10-15，Asia/Shanghai。审阅者：Codex 主 agent；内部 agent 分别进行 Schema 工程验证与设计审阅。

## G2.1 MongoDB 设计

通过。DATABASE 说明五个集合、访问模式、嵌入/引用与冗余取舍、Schema、索引、版本和资源边界；schema-examples.json 提供完整 Extended JSON 样例并标明非实测。可执行定义位于 survey_app/db.py。已修正原稿把嵌套题型检查误归给 MongoDB 的措辞，具体规则由应用层验证。

## G2.2 契约与一致性

通过。API/LOGIC 与 D01–D10 对齐，覆盖所有权、登录后匿名、四类题目、三类跳转、关闭/截止、重复/幂等、路径和统计。审阅发现的两个缺口已补齐：显式 null 区分跳过可选题与尚未作答；发布读取/验证/冻结同一 revision。真正 gate 写入、数据库 $$NOW 与关闭竞争协议已明确，不提前声称业务并发通过。

## G2.3 真实数据库约束

通过。python scripts/check_schema.py 在本项目独立副本集新建精确 UUID 测试库，43 项字段、索引、唯一性及幂等/条件唯一测试全部 PASS，退出 0；实际记录见 schema-check.json、schema-check.log。测试结束仅清理该新库并确认 remaining_collections=[]。TTL 仅核验定义，不声称异步删除时机已测试。

未验证范围：账号、页面、跳转求值、提交及统计业务均属于后续阶段。Git 首次入库的 CRLF 提示为行尾转换提醒，已用 .gitattributes 固定文本行为，不改变源 Word 字节或验收条件。
