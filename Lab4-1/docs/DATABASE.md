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

五个集合的完整字段样例见 [schema-examples.json](schema-examples.json)，以 Extended JSON 表示 BSON 日期；其中 `surveys` 是已发布形态（发布时 draft 已被移除）、`surveys_draft` 是草稿形态，`survey_versions` 样例含单选/多选/数字/文本四类题型与两条跳转规则，`responses` 样例含跳题后的实际路径。样例中的账号、token 与答案均为设计示例，不是实测结果或可登录凭据。

集合间用 ID 引用，题目/选项/约束在同一发布快照内嵌。此设计服务于整卷读取和单次答卷写入，避免为了模仿关系表而把每个选项拆成集合。MongoDB 同样可以表达关联，但本课程明确要求 MongoDB；不能以此推论关系数据库不适合问卷。

## 字段及索引约束

所有集合启用 strict/error 的 `$jsonSchema` 字段校验；时间为 BSON date，计数为 int/long，状态按枚举检查，题型与规则的具体配置由应用层校验。MongoDB 字段校验只约束文档形状；拥有者、图可达性、题型与值、状态转移及策略不能因此省略应用层验证。

索引与查询的对应关系如下（索引名与 `survey_app/db.py` 的 `INDEXES` 一一对应；S2 实测 9 个索引全部存在，字段、唯一性与条件过滤与代码一致）：

| 索引 | 字段与特性 | 服务的查询（代码位置） | 选择性与预期计划 |
| --- | --- | --- | --- |
| `uq_users_username_key` | username_key，唯一 | 登录按规范化用户名取账号（`service.py:37`） | 等值唯一键，命中单文档 |
| `ix_surveys_owner_created` | owner_id 升序 + created_at 降序 | 本人问卷列表（`service.py:74`） | 等值 + 排序前缀，避免内存排序 |
| `uq_surveys_share_code` | share_code，唯一 | 按分享码读问卷（`service.py:125`）；发布时分享码可用性检查（`service.py:131`） | 等值唯一键，命中单文档 |
| `uq_survey_versions_survey_version` | survey_id + version，唯一 | 读取发布快照（`service.py:49`） | 复合等值，命中单文档 |
| `ix_responses_survey_version` | survey_id + version | 统计与答卷明细按问卷/版本读取（`statistics.py:37-40`） | 复合等值后扫描该版本全部答卷；卷内答卷数增长时扫描量随之增长 |
| `uq_responses_request` | survey_id + respondent_id + request_id，唯一 | 幂等判重与回执重放（`submissions.py:39,47,69`） | 三字段等值唯一键；其 `survey_id` 前缀亦可服务按问卷读答卷 |
| `uq_responses_single_submission` | survey_id + respondent_id，唯一，条件 `single_submission=true` | 禁止同一账号重复成功提交（标志由 `submissions.py:42` 按冻结的 allow_repeat 写入） | 部分唯一索引，仅约束本问卷内标记为单次提交的答卷 |
| `ttl_sessions_expires_at` | expires_at，TTL 0 秒 | 过期会话清理（`security.py:48`；认证有效性由显式时间比较保证，不依赖删除时机） | 后台 TTL 扫描，与认证路径解耦 |
| `ix_sessions_user` | user_id | 预留：按账号列举或注销全部会话；当前代码未使用该索引 | 等值索引，当前无对应查询 |

常规业务查询都是索引前缀的等值访问或“等值 + 排序”访问，没有预期需要全集合扫描的路径；唯一随数据量线性增长的是统计按问卷/版本读取答卷。

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

### Schema 版本与演进思路（未执行，仅设计说明）

第一阶段所有集合写入 `schema_version=1`，校验器为 strict/error，因此**当前不存在“旧版本文档”**；本节的演进思路是为第二阶段可能的结构变更预留的，本次未实现脚本、未做迁移演练，不能当作已完成能力。

若第二阶段新增字段或改变结构，按以下顺序处理，保证旧数据可读、旧功能可用：

1. 判定变更类型：只加可选字段的兼容变更，与需要改变类型/语义或收紧约束的非兼容变更分开处理。
2. 先放宽校验器：把新增字段保持为可选，或为旧文档缺失字段定义明确的默认语义；`$jsonSchema` 的 `required` 只包含旧文档也一定有的字段，避免历史文档立即变成非法。
3. 分批回填：按 `_id` 分页、幂等、可中断续跑的脚本补齐新字段；先在隔离测试库做 dry-run，再对有备份的业务库执行。
4. 双读窗口：应用层在回填完成前同时接受“缺字段”和“带字段”两种文档，读取时补默认值；写入统一写新结构，避免出现第三种形态。
5. 收紧与换版：回填完成且回归通过后，把 `schema_version` 提升为 2、恢复严格的 `required`，并保留按版本分支的读取代码直到确认无 v1 文档。

配套的回滚方式：变更前用 `mongodump` 做 BSON 快照（S7 已演练备份恢复流程），回滚即恢复快照并把应用回退到上一版本；由于答卷与发布快照都带 `version`/`schema_version`，统计口径可以按版本分别计算，不会把两种结构混算。第一阶段不提供 v2 发布、重开或导出功能。
