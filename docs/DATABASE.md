# MongoDB 数据库设计

本设计对应 R01–R11，Schema 版本为 1。集合初始化由 `survey_app/db.py` 的 `initialize_schema` 执行；该函数创建或同步字段校验与索引，不删除集合/数据。真实 Schema 验证证据在 S2 产生，业务一致性在 S3–S6 验证。

## 访问模式与集合边界

用户按用户名登录，按拥有者列出问卷；填写者通过分享码读取固定发布版本并提交一份完整答卷；创建者按问卷/版本查询统计和答卷。采用以下集合：

- `users`：`_id`、显示用户名、规范化 `username_key`、密码哈希、注册时间、schema_version。账号独立于问卷生命周期。
- `sessions`：`_id` 为会话 token 的服务端摘要，user_id、created_at、expires_at、schema_version；过期会话每次请求仍由服务端检查，TTL 删除的时机不作为认证有效性依据。
- `surveys`：拥有者、分享码、标题/说明、匿名/重复策略、状态、UTC 截止时间、revision、gate_seq、published_version、创建/更新时间。草稿的 questions/rules 嵌入 `draft` 子文档，便于整体编辑及乐观并发校验。
- `survey_versions`：survey_id、version、questions、rules、created_at、schema_version。发布时将题目/选项/校验/规则作为不可变整体快照，发布问卷移除 draft；第一阶段每卷发布一次，version=1，不实现未知二阶段需求。
- `responses`：一次成功提交一文档，包含 survey_id、version、私有 respondent_id、request_id、payload_hash、answers、path、single_submission、anonymous、submitted_at、schema_version。不要向问卷文档持续追加答卷数组。

所有 `_id`、题目和选项 ID 都是稳定字符串。题目 ID 不含点号或 `$`，防止歧义查询键；选项以 ID 而非显示文字关联，改显示标签不会被误当成另一个选项。项目边界：标题 200 码点、说明 5000、题目标题 500、选项标签 200、题目 100、单题选项 50、跳转规则 500、单个文本回答 10000；题目/选项 ID 最长 64，请求 ID 最长 128。API 请求体、待存储发布快照及单份答卷均限制在 1 MiB（实际 UTF-8/BSON 编码字节），发布/提交时校验，避免无限增长。这些数量不是教师指定要求。

五个集合的完整字段样例见 [schema-examples.json](schema-examples.json)，以 Extended JSON 表示 BSON 日期；其中账号、token 与答案均为设计示例，不是实测结果或可登录凭据。

集合间用 ID 引用，题目/选项/约束在同一发布快照内嵌。此设计服务于整卷读取和单次答卷写入，避免为了模仿关系表而把每个选项拆成集合。MongoDB 同样可以表达关联，但本课程明确要求 MongoDB；不能以此推论关系数据库不适合问卷。

## 字段及索引约束

所有集合启用 strict/error 的 `$jsonSchema` 字段校验；时间为 BSON date，计数为 int/long，状态按枚举检查，题型与规则的具体配置由应用层校验。MongoDB 字段校验只约束文档形状；拥有者、图可达性、题型与值、状态转移及策略不能因此省略应用层验证。

- users.username_key 唯一：用户名 trim 后 casefold，避免仅大小写差异重复。
- surveys.share_code 唯一；owner_id + created_at 索引用于本人列表。
- survey_versions 的 survey_id + version 唯一。
- responses 的 survey_id + respondent_id + request_id 唯一，保证网络重试幂等。
- responses 的 survey_id + respondent_id 条件唯一，只覆盖 `single_submission=true` 的记录；服务器根据冻结的 allow_repeat 设置该值。允许重复的记录不受此索引限制。
- responses 的 survey_id + version 普通索引用于统计。
- sessions.expires_at TTL，user_id 普通索引。

先查询再插入无法消除竞争，最终唯一性由数据库索引保证。部分唯一索引只约束满足过滤条件的文档，依据 [MongoDB 部分索引说明](https://www.mongodb.com/docs/manual/core/index-partial/)（2026-10-15 核对）。

## 发布与提交事务

发布请求携带期望 revision；发布事务内读取并校验该版草稿，再按 owner_id、status=draft、同一 revision 条件写 surveys 状态/版本和 survey_versions 快照；任一步失败整体回滚。编辑竞争引发重试时必须重读重验，期望版不符返回 409，不发布旧快照。草稿编辑同样按期望 revision 条件更新，不静默覆盖。

新答卷提交事务先对 surveys 做真正的条件写入：匹配 published、版本一致，且 closes_at=null 或严格大于数据库 `$$NOW`；以更新管道增加 gate_seq，并将 last_accepted_at 设置为同一命令的 `$$NOW`。随后插入完整 response。事务采用 snapshot 读、majority 提交；关闭及调整截止时间也写同一个 survey 文档，因此会与受理写入冲突并确定先后。

“受理”是最终成功事务中 gate 条件更新采用的数据库时间和串行顺序，不是 HTTP 抵达时间。截止等于受理时刻拒绝；若先受理后关闭，答卷可在稍后提交事务完成。事务冲突重试必须重新读取状态和时间，回调不产生外部副作用。仅 snapshot 读 survey 再插答卷不足以阻止读到旧状态，依据 [MongoDB 事务注意事项](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) 及 [PyMongo 事务重试](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/)（2026-10-15 核对）。

请求 ID 与规范化内容摘要稳定。相同请求的成功回执优先重放，即使后来关闭也不新增答卷；相同 ID 不同内容冲突。并发唯一键冲突后查找同用户原回执，内容相同则重放，否则报幂等或重复填写冲突。事务失败时 gate_seq 与答卷同时回滚，不把计数当持久汇总成绩。

## 隐私、统计及演进

认证 token、密码哈希和私有填写者 ID 不返回问卷 API。匿名答卷及统计通过明确字段白名单投影；匿名只表示对创建者隐藏账号，仍需登录并可由服务端按私有 ID 判重。

统计从 responses 按 survey_id/version 查询生成，区分提交数与去重人数。跳过或空答不按 0 计均值；原文内容按答卷返回。在MongoDB snapshot事务中按问卷/版本查询固定答卷列表，再由statistics.py计算次数、人数和均值；统计结果不持久化为可能失真的副本。全部业务持久数据包括会话均在 MongoDB；日志、配置模板和合成夹具是工程文件，不充当业务数据库。

schema_version 和发布版本用于解释当前数据；S7 记录基线及恢复说明。本阶段不运行二阶段迁移，不删除旧 Lab 数据。测试清理仅限本次新建 `lab4_test_UUID` 数据库，初始化正常业务库不清库。
