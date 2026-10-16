# 第一阶段测试报告

本报告记录已执行的结果；验收步骤和预期保存在 [TEST_PLAN.md](TEST_PLAN.md)，解释依据为已采纳的 [DECISIONS.md](DECISIONS.md)。仅覆盖第一阶段 26 组用例，不以第二阶段为验收前置。编制：Codex，2026-10-15，Asia/Shanghai；本次汇总只读取既有证据，未重复运行业务测试。

改版后复跑（2026-10-16 补记）：S7 之后填写页面做过一次改版，改版后重新运行全量测试仍为 **245 passed**（exit 0，证据 [results/local-run.json](../results/local-run.json)）；对照指导文件的第一阶段复核中再次复跑同样得 245 passed（证据 [复核证据](../results/stage1-audit/pytest-run.json)）。两次都是同一批 245 条断言，改版只涉及 `survey_app/static/app.css` 与 `survey_app/static/app.js` 两个表现层文件，21 个业务文件的基线差异见 [基线复核](../results/ui-refresh/code-baseline-check.json)。本报告正文的逐组结果仍以 S6 汇总（基线 e7255c3）为准。

## 证据、环境与计数口径

业务基线为 `e7255c3`（S5 通过后提交）。[full-tests.json](../results/S5/full-tests.json) 记录 2026-10-15 21:49:00.685782 至 21:49:24.365886 +08:00 的实际执行，selection=`tests`、seed=`20261015`、退出码0；[原始控制台](../results/S5/full-tests.txt) 为 245 passed、1 warning。JSON 含应用和测试源码 SHA-256，供与该次执行基线逐文件核对。

环境：Windows 10.0.26200，Python 3.11.17，pytest 9.1.1，FastAPI 0.143.1，PyMongo 4.19.0，HTTPX 0.28.1；真实 MongoDB 6.0.29，副本集 lab4rs、可写 primary、primary 读偏好、UTC 感知时间。测试库 `lab4_test_api_e3e0bf4ef2b944ccaf3a690b6e4e551e` 是本次创建的隔离 UUID 库。清理前 users125/sessions124/surveys95/survey_versions82/responses59，按该精确库名清理后 remaining_collections=[]、cleanup=PASS，未使用其他 Lab 数据。

245 条 `phase=call` 记录全部 passed；setup/teardown 各245通过，无失败、跳过、收集错误。模块分别为 admin35、rules155、submissions46、statistics9。题目校验/路径类包含直接调用的单元测试，next、管理、提交、统计类通过实际API访问真实MongoDB；不能把245条全部称为数据库集成测试。两个E组由独立浏览器/复现证据验收，不混入245。

逐组映射规则：从 JSON 的 `records` 筛选 `phase=call` 且 `cases` 包含该组ID，保留原始参数化 nodeid 和 outcome。一个测试可支持多个组（例如非法submit同时支持R02和V组）；以下“关联调用数”有重叠，不可相加冒充独立测试总数。每个参数的具体输入和期望断言见链接源码；JSON保存逐参数执行状态，未记录的完整HTTP响应不冒称存在。组内“实际”是这些原始断言在真实执行中通过的结果摘要，详细并发回执/ID/对账另见 JSON 的 `submission_experiments`。

截至2026-10-15 22:19:55 +08:00，24/24业务组 PASS，TC-E01 PASS，TC-E02 在清理补救验证后 PASS，共26/26组通过。TC-E02 原包装器退出1的失败记录保留；最终记录追加清理补救证据，不改写原始测试或原失败结果。此结论为S6用例验收，S7报告与交付基线仍须由其门禁单独审阅。

## 逐组结果

### TC-A01 注册与登录

- 步骤：注册合成账号，读取 MongoDB 用户文档；尝试重名、错误密码、正确登录及退出；补测注册字段和请求体边界。
- 具体输入：用户名 u_<UUID>；大小写变体/首尾空格重名；错误密码 wrong-password；短用户名 ab、空白用户名、短密码 short；超过 1 MiB 的合法 JSON；无 Content-Length 的分块 ASGI 输入。正常密码为测试夹具中的公开合成值。
- 预期：注册201且含 created_at，仅存 scrypt 哈希；注册后仍未登录；重名409、错密401、合法登录200；Cookie 为 HttpOnly/SameSite=Strict；退出后401；非法字段和超限请求422，不写用户。
- 实际：全部断言通过，实际 MongoDB 字段与会话读回符合预期；无长度头的流在第2块超限时停止，未读后续块。测试证据不捕获密码、Cookie 或原始局部变量。
- 状态：**PASS**；关联调用 6 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-A01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:86 `test_register_login_hash_uniqueness_and_logout`](../tests/test_admin.py#L86)；[test_admin.py:118 `test_registration_input_validation`](../tests/test_admin.py#L118)；[test_admin.py:352 `test_body_larger_than_one_mib_is_rejected_with_content_length`](../tests/test_admin.py#L352)；[test_admin.py:363 `test_stream_without_content_length_stops_reading_when_limit_exceeded`](../tests/test_admin.py#L363)。

### TC-A02 填写前认证

- 步骤：依次以未登录、过期会话、已登录填写者请求实际存在的管理、读取填写、next、submit、统计及明细路由；检查 Origin。
- 具体输入：匿名问卷仍需登录；expires_at 设为服务端时间前5秒；Origin=https://untrusted.invalid、http://[ 与合法 http://testserver；合法 version=1；无效 version=99。
- 预期：未登录或过期401，合法登录可填有效发布问卷；跨域/畸形 Origin403且无写入；合法同源可创建；匿名开关不绕过认证。
- 实际：S3 管理/入口、S4 next、S5 submit/统计/明细子用例均已覆盖并通过；权限测试先证实目标接口存在，未把未实现404当认证成功。
- 状态：**PASS**；关联调用 7 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-A02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:123 `test_unauthenticated_management_and_existing_fill_route`](../tests/test_admin.py#L123)；[test_admin.py:310 `test_expired_session_is_rejected_without_waiting_for_ttl`](../tests/test_admin.py#L310)；[test_admin.py:319 `test_cross_origin_write_is_rejected_and_same_origin_works`](../tests/test_admin.py#L319)；[test_admin.py:343 `test_malformed_origin_is_rejected_without_server_error`](../tests/test_admin.py#L343)；[test_rules.py:354 `test_next_requires_auth_and_real_published_version_without_saving_draft_answers`](../tests/test_rules.py#L354)；[test_statistics.py:191 `test_statistics_and_raw_response_routes_require_owner_and_login`](../tests/test_statistics.py#L191)；[test_submissions.py:234 `test_authenticated_filler_can_submit_but_only_owner_can_read_statistics_and_details`](../tests/test_submissions.py#L234)。

### TC-A03 服务端拥有者隔离

- 步骤：A 建草稿并发布，B 直接访问 A 的 ID、列表、修改、发布、deadline、关闭、整卷/单题统计与明细，前后核对 MongoDB。
- 具体输入：两个不同合成账号；B PUT title=Injected、PATCH closes_at=null、POST publish/close；A 的既有问卷 ID 和合法统计题 ID。
- 预期：B 列表不含 A 的问卷，各拥有者路由404且数据不变；未登录401；A 可读结果；B 可按分享填写权限合法提交。
- 实际：管理与结果两批均通过；越权前后问卷/答卷数量不变，合法填写者的私有身份在数据库中正确关联。未提供删除/导出接口，不将其列为已验证能力。
- 状态：**PASS**；关联调用 3 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-A03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:145 `test_owner_isolation_on_implemented_management_routes`](../tests/test_admin.py#L145)；[test_statistics.py:191 `test_statistics_and_raw_response_routes_require_owner_and_login`](../tests/test_statistics.py#L191)；[test_submissions.py:234 `test_authenticated_filler_can_submit_but_only_owner_can_read_statistics_and_details`](../tests/test_submissions.py#L234)。

### TC-Q01 创建问卷

- 步骤：创建完整元数据草稿及只含标题的最小草稿，查本人列表与 MongoDB，尝试空标题、服务端字段注入和时间类型。
- 具体输入：标题课程调查、说明第一行/换行/第二行；allow_anonymous=false、allow_repeat=true；默认草稿；空标题/空白；owner_id/status/gate_seq/unexpected；截止含时区 ISO、Z、null，以及1700000000、浮点、数字文本、布尔。
- 预期：创建201；完整字段/拥有者/UTC时间保留；默认 anonymous=true、repeat=false、description为空；非法输入422且无写入。
- 实际：完整与默认配置均持久化正确，列表可见性及全部正反时间类型断言通过。
- 状态：**PASS**；关联调用 16 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-Q01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:173 `test_create_preserves_metadata_defaults_and_ownership`](../tests/test_admin.py#L173)；[test_admin.py:196 `test_empty_title_rejected_without_write`](../tests/test_admin.py#L196)；[test_admin.py:331 `test_unknown_and_server_owned_fields_are_rejected`](../tests/test_admin.py#L331)；[test_admin.py:402 `test_numeric_or_boolean_deadline_rejected_at_all_write_entries`](../tests/test_admin.py#L402)；[test_admin.py:419 `test_timezone_iso_and_null_deadline_accepted_at_all_write_entries`](../tests/test_admin.py#L419)。

### TC-Q02 四类配置与发布冻结

- 步骤：保存 single/multi/text/number 题与规则，重读；发布后查看快照，再尝试改题、改判重策略及再次发布。
- 具体输入：q1 yes/no必答；q2 x/y/z多选min1/max2；q3文本max100；q4整数0..120；q1=no跳q3 priority10；伪造 owner_id/status/gate_seq/unknown 字段。
- 预期：稳定题/选项 ID、顺序、约束与规则保持；首次发布200且version1；发布后修改/再发布409、快照仍仅一份；未知字段422。
- 实际：数据库 snapshot 与保存配置逐字段相符；发布后 draft 字段移除、快照未变、分享码稳定，拒绝注入时原文档未变。
- 状态：**PASS**；关联调用 5 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-Q02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:204 `test_four_types_configuration_and_published_snapshot_freeze`](../tests/test_admin.py#L204)；[test_admin.py:331 `test_unknown_and_server_owned_fields_are_rejected`](../tests/test_admin.py#L331)。

### TC-Q03 发布与生命周期预检

- 步骤：读草稿/发布/关闭/到期分享，尝试旧 revision 保存/发布、双线程同时发布、非法存量草稿发布和截止输入。
- 具体输入：Barrier(2)同时发布；旧 revision；故障注入 missing_target/self_loop/duplicate_id/empty_questions；closes_at=服务端时间前5秒；version1；数值/布尔非法截止与时区ISO/null。
- 预期：草稿409、有效发布200、关闭/到期410；旧revision409；并发恰一份快照；坏配置422且仍draft、无快照；非法时间422。此组只做入口预检，最终提交见R05。
- 实际：两个发布响应为200/409；快照1份，旧revision不覆盖新草稿；四种故障草稿均被发布门禁拒绝；读取版本与生命周期符合预期。故障注入不是公开API允许非法草稿的声明。
- 状态：**PASS**；关联调用 17 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-Q03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_admin.py:228 `test_draft_published_closed_and_expired_fill_links`](../tests/test_admin.py#L228)；[test_admin.py:249 `test_stale_edit_and_publish_revision_cannot_replace_new_draft`](../tests/test_admin.py#L249)；[test_admin.py:266 `test_concurrent_publish_freezes_exactly_one_version`](../tests/test_admin.py#L266)；[test_admin.py:289 `test_publish_revalidates_invalid_stored_configuration`](../tests/test_admin.py#L289)；[test_admin.py:402 `test_numeric_or_boolean_deadline_rejected_at_all_write_entries`](../tests/test_admin.py#L402)；[test_admin.py:419 `test_timezone_iso_and_null_deadline_accepted_at_all_write_entries`](../tests/test_admin.py#L419)；[test_rules.py:403 `test_next_checks_draft_closed_expired_and_unknown_lifecycle`](../tests/test_rules.py#L403)。

### TC-V01 单选

- 步骤：直接调用服务端校验器，并通过 next/submit 复测；覆盖必答、可选、类型、未知与多个选项。
- 具体输入：选项a/b；必答输入 null、空串、missing、[a]、[a,b]、true、1、{}；合法 a/b；可选 null/空串；submit未知选项。
- 预期：仅配置中的单个字符串选项及可选空答通过；非法422含题ID；next/submit使用相同规则，非法提交不写答卷/gate。
- 实际：合法 a/b 原值返回，可选空答规范为null；必答/类型/选项错误与API无写入断言均通过。
- 状态：**PASS**；关联调用 32 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-V01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:70 `test_required_single_rejects_empty_unknown_multiple_and_wrong_types`](../tests/test_rules.py#L70)；[test_rules.py:76 `test_single_accepts_only_defined_one_option`](../tests/test_rules.py#L76)；[test_rules.py:81 `test_optional_single_can_be_skipped`](../tests/test_rules.py#L81)；[test_rules.py:422 `test_next_uses_same_server_validator_for_all_question_types`](../tests/test_rules.py#L422)；[test_submissions.py:138 `test_invalid_values_for_all_four_types_do_not_write_response_or_gate`](../tests/test_submissions.py#L138)。

### TC-V02 多选数量

- 步骤：逐项验证最少/最多/恰选边界、重复与非法类型；检查规范化顺序及输入不被修改；经 next/submit 复测。
- 具体输入：四选项a/b/c/d；min2、max3、min2/max3、exact2；选择1/2/3/4项；[a,a]、[a,unknown]、[a,1]、字符串/布尔/对象；配置顺序[c,a,d,b]时输入[b,c,a]。
- 预期：边界包含；重复先拒绝、不能去重后放行；合法输出按配置顺序；可选null/[]跳过数量约束；非法422且提交不写。
- 实际：计数边界及错误类型通过；规范化得到[c,a,b]且原输入未变；可选空答与真实API拒绝符合预期。
- 状态：**PASS**；关联调用 39 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-V02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:92 `test_multi_count_constraints_have_inclusive_boundaries`](../tests/test_rules.py#L92)；[test_rules.py:101 `test_multi_rejects_duplicates_unknown_values_wrong_types_and_required_empty`](../tests/test_rules.py#L101)；[test_rules.py:106 `test_multi_normalizes_to_configured_order_without_mutating_input`](../tests/test_rules.py#L106)；[test_rules.py:116 `test_optional_multi_empty_skips_nonempty_count_constraints`](../tests/test_rules.py#L116)；[test_rules.py:422 `test_next_uses_same_server_validator_for_all_question_types`](../tests/test_rules.py#L422)；[test_submissions.py:138 `test_invalid_values_for_all_four_types_do_not_write_response_or_gate`](../tests/test_submissions.py#L138)。

### TC-V03 文本长度

- 步骤：按 Unicode 码点测试 min2/max4 与空白，检查合法原文；经 next/submit 复测并加入不能编码为BSON的字符串。
- 具体输入：合法ab、甲乙、a🙂、甲乙丙丁、带空格的 ab；非法a/abcde/甲乙丙丁戊/家庭组合表情/数字/布尔/数组；e+组合重音、👍🏽各2码点；可选null/空串/空白；孤立代理字符U+D800。
- 预期：长度边界包含，原文保留；必答空白拒绝，可选空白视空；码点不等于用户可见字素数；非法/不可BSON编码422且无写入。
- 实际：合法原文未裁剪；组合重音/肤色表情按2码点通过，家庭组合因超长拒绝；非法提交和BSON编码边界无答卷/gate增长。
- 状态：**PASS**；关联调用 43 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-V03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:122 `test_text_preserves_raw_content_and_accepts_inclusive_lengths`](../tests/test_rules.py#L122)；[test_rules.py:128 `test_text_rejects_required_blank_lengths_and_nontext_values`](../tests/test_rules.py#L128)；[test_rules.py:134 `test_text_counts_unicode_codepoints_instead_of_grapheme_clusters`](../tests/test_rules.py#L134)；[test_rules.py:141 `test_optional_text_blank_skips_length_constraints`](../tests/test_rules.py#L141)；[test_rules.py:422 `test_next_uses_same_server_validator_for_all_question_types`](../tests/test_rules.py#L422)；[test_submissions.py:138 `test_invalid_values_for_all_four_types_do_not_write_response_or_gate`](../tests/test_submissions.py#L138)；[test_submissions.py:149 `test_non_bson_or_nonfinite_json_answers_are_422_without_writes`](../tests/test_submissions.py#L149)。

### TC-V04 数字边界

- 步骤：直接校验数学整数、范围、小数与类型；经 next/submit 验证非有限JSON及BSON整数范围。
- 具体输入：整数0..120：-1/0/120/121/1.5/1.0/0.0；允许小数范围-1.5..2.5的端点及2.50001；字符串10、布尔、NaN/±Infinity/null/数组/对象；API 1e309与2**80。
- 预期：0/120有效、1.0规范为int1；允许小数时保留；非有限、布尔、字符串与超BSON整数拒绝422，不能静默截断或写入。
- 实际：所有端点、有限性、严格类型及规范化断言通过；0未当作空答，非法提交gate/答卷保持0。
- 状态：**PASS**；关联调用 41 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-V04`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:147 `test_integer_numeric_boundaries_and_normalization`](../tests/test_rules.py#L147)；[test_rules.py:155 `test_number_rejects_range_fraction_nonfinite_coercion_and_boolean`](../tests/test_rules.py#L155)；[test_rules.py:160 `test_fractional_numbers_are_preserved_when_allowed_and_zero_is_not_empty`](../tests/test_rules.py#L160)；[test_rules.py:422 `test_next_uses_same_server_validator_for_all_question_types`](../tests/test_rules.py#L422)；[test_submissions.py:138 `test_invalid_values_for_all_four_types_do_not_write_response_or_gate`](../tests/test_submissions.py#L138)；[test_submissions.py:149 `test_non_bson_or_nonfinite_json_answers_are_422_without_writes`](../tests/test_submissions.py#L149)。

### TC-V05 配置自身合法性

- 步骤：逐项构造不相容限制、结构/字段错误及坏图，并检查必答可满足性与可选空答。
- 具体输入：min>max、负计数、布尔伪整数、exact超选项/与minmax冲突、非法/重复题或选项ID、单选不足2选项、未知字段/类型；required multi max0/exact0、text max_length0、integer min0.1/max0.9；可选同配置及整数0..0对照。
- 预期：保存/发布配置时422，不留到填写时才发现必答无解；相同可选约束可通过且null可跳过；整数0..0可满足；规则限制同J04。
- 实际：17个约束参数、4个必答无解、合法零区间、7个结构故障和12个坏规则及priority口径全部通过；未通过降低原断言来使无解配置成功。
- 状态：**PASS**；关联调用 42 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-V05`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:184 `test_impossible_or_wrongly_typed_constraints_are_rejected`](../tests/test_rules.py#L184)；[test_rules.py:193 `test_required_nonempty_answer_must_exist_but_optional_null_is_allowed`](../tests/test_rules.py#L193)；[test_rules.py:199 `test_integer_interval_with_exactly_zero_is_satisfiable`](../tests/test_rules.py#L199)；[test_rules.py:206 `test_question_and_option_structure_rejected`](../tests/test_rules.py#L206)；[test_rules.py:228 `test_rule_configuration_and_graph_are_checked_before_publication`](../tests/test_rules.py#L228)；[test_rules.py:248 `test_priority_uniqueness_is_per_source_question`](../tests/test_rules.py#L248)。

### TC-J01 单选数据驱动分支

- 步骤：以配置的 source/target 求值，修改目标后重算并检查输入配置不变；真实发布版next接口读取配置。
- 具体输入：三题start/middle/end；规则start=a跳end，start=b默认middle；副本规则目标改middle；真实API version1、start=a。
- 预期：按配置指定目标执行，修改配置无需改求值代码；原配置不被求值修改；已发布快照冻结在Q02/Q03另验证。
- 实际：a到end、b到middle，目标改middle后按新数据执行；next返回路径[start,end]并停于待答end，未保存草稿答案。原计划Q1→Q5/Q3的题数仅为示例，此处用最小三题证明同一行为。
- 状态：**PASS**；关联调用 2 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-J01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:261 `test_single_rule_targets_are_data_driven`](../tests/test_rules.py#L261)；[test_rules.py:354 `test_next_requires_auth_and_real_published_version_without_saving_draft_answers`](../tests/test_rules.py#L354)。

### TC-J02 多选ANY/ALL与优先级

- 步骤：分别评估ANY/ALL空、部分、全命中，增加两条同时命中的不同priority规则并故意倒置输入次序。
- 具体输入：规则条件固定[a,b]；ANY答案[a]、[b,c]、[c]、[]；ALL答案[a]、[a,b]、[b,a,c]、[]；另用两条同时匹配start=a的single规则验证priority20→end在前、priority10→middle在后。
- 预期：ANY有交集命中，ALL目标非空且全包含才命中；空集合不命中；priority数值升序首命中，与输入次序无关。
- 实际：8个集合组合及显式priority用例通过，双命中时进入middle。空条件公开配置拒绝由V05/J04覆盖；此处空答案集合[]不命中。ANY/ALL与共享优先级机制分别验证，未把single双命中输入写成多选输入。
- 状态：**PASS**；关联调用 9 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-J02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:279 `test_multi_any_all_and_empty_sets`](../tests/test_rules.py#L279)；[test_rules.py:298 `test_explicit_priority_beats_input_order_when_rules_both_match`](../tests/test_rules.py#L298)。

### TC-J03 数字分支

- 步骤：对五种运算符分别用阈值下/等/上值求值，并先验证源答案。
- 具体输入：阈值10，运算eq/lt/lte/gt/gte，输入9/10/11共15项；另输入NaN。
- 预期：命中与比较真值一致，未命中顺序前进；非法源值先422，不能参与比较。
- 实际：15个运算边界全部按预期目标执行；NaN在条件比较前被拒绝。
- 状态：**PASS**；关联调用 16 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-J03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:292 `test_all_numeric_operators_below_equal_and_above_threshold`](../tests/test_rules.py#L292)；[test_rules.py:346 `test_source_answer_is_validated_before_condition_evaluation`](../tests/test_rules.py#L346)。

### TC-J04 默认路径与发布图校验

- 步骤：运行无命中默认顺序和末题结束，测试部分路径；配置缺源/缺目标、自环、回跳、同源priority冲突及不支持操作符。
- 具体输入：first→optional→last无规则路径；规则target不存在/等于source/向前；同源priority10重复；不同source可同priority；single使用gt、text作为source、multi空all/未知option、number不支持操作符。
- 预期：无匹配顺序前进，末题正常完成；坏图/算子422；优先级唯一限制按source；不存在死循环。
- 实际：默认顺序、结束及所有坏规则断言通过；不同source复用priority10允许，同source重复拒绝；生命周期门禁不允许草稿/关闭/到期next。
- 状态：**PASS**；关联调用 17 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-J04`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:228 `test_rule_configuration_and_graph_are_checked_before_publication`](../tests/test_rules.py#L228)；[test_rules.py:248 `test_priority_uniqueness_is_per_source_question`](../tests/test_rules.py#L248)；[test_rules.py:298 `test_explicit_priority_beats_input_order_when_rules_both_match`](../tests/test_rules.py#L298)；[test_rules.py:309 `test_partial_missing_key_stops_but_explicit_optional_null_advances`](../tests/test_rules.py#L309)；[test_rules.py:387 `test_next_handles_explicit_null_then_recomputes_changed_branch`](../tests/test_rules.py#L387)；[test_rules.py:403 `test_next_checks_draft_closed_expired_and_unknown_lifecycle`](../tests/test_rules.py#L403)。

### TC-J05 路径重算与必答（a/b）

- 步骤：J05a直接求值及next：跳过必答，回改早期答案，区分缺键与显式null；J05b实际submit发送相同路径篡改并核对数据库；页面回改证据另列E01。
- 具体输入：start=a跳过必答middle到end；改b后middle变可达；旧middle答案、unknown题、客户端path/respondent_id/rules、旧version99；partial缺键停止，可选null继续；必答缺失。
- 预期：只校验可达题，跳过必答可成功；回改后新路径必答不可漏；路径外/未知/客户端控制字段422，旧版409；非法提交答卷/gate0；页面清理后续旧答案。
- 实际：J05a与J05b均通过；合法跳过写入path[single,number]，不含被跳过题答案；浏览器回改首题后路径从4题变2题且后续数字先清空，见S4路径证据。
- 状态：**PASS**；关联调用 22 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-J05`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_rules.py:309 `test_partial_missing_key_stops_but_explicit_optional_null_advances`](../tests/test_rules.py#L309)；[test_rules.py:328 `test_skipped_required_question_and_changed_answer_recalculation`](../tests/test_rules.py#L328)；[test_rules.py:341 `test_unknown_wrongly_typed_or_unreachable_payload_rejected`](../tests/test_rules.py#L341)；[test_rules.py:346 `test_source_answer_is_validated_before_condition_evaluation`](../tests/test_rules.py#L346)；[test_rules.py:354 `test_next_requires_auth_and_real_published_version_without_saving_draft_answers`](../tests/test_rules.py#L354)；[test_rules.py:379 `test_next_rejects_path_out_unknown_answers_and_client_control_fields`](../tests/test_rules.py#L379)；[test_rules.py:387 `test_next_handles_explicit_null_then_recomputes_changed_branch`](../tests/test_rules.py#L387)；[test_submissions.py:169 `test_submit_recomputes_path_and_rejects_tampering_without_write`](../tests/test_submissions.py#L169)；[test_submissions.py:186 `test_submit_accepts_skipped_required_questions_on_recomputed_valid_branch`](../tests/test_submissions.py#L186)。

### TC-R01 成功提交与持久化

- 步骤：从合法四题或跳转路径提交，直接读真实MongoDB；创建独立app lifespan/MongoClient复读统计。独立OS进程重启另见E02。
- 具体输入：version1、新request_id、single=a、multi=[y,x]、text=合成回答、number=1.0；跳转路径single=a、number10。
- 预期：保存独立完整答卷，答案规范化、path/版本/问卷/私有判重/时间字段完整；gate与答卷同事务；新应用实例可读。
- 实际：正常答卷multi为[x,y]、number为整数1；path四题，hash64字符、schema_version1；gate1且last_accepted_at等于submitted_at；独立应用实例统计submissions1。未将同进程新实例冒充OS进程重启。
- 状态：**PASS**；关联调用 2 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-R01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_submissions.py:105 `test_success_is_a_complete_persistent_document_readable_by_new_application_instance`](../tests/test_submissions.py#L105)；[test_submissions.py:186 `test_submit_accepts_skipped_required_questions_on_recomputed_valid_branch`](../tests/test_submissions.py#L186)。

### TC-R02 非法提交无成功写入

- 步骤：逐题替换非法值、删除可达必答、注入路径外/未知题及客户端控制字段/旧版；插入前故障注入真实Mongo校验失败，观察事务回滚再重试。
- 具体输入：16个四类非法值；孤立代理字符/2**80/JSON1e309；7种路径/字段/版本篡改；真实insert文档schema_version99触发Mongo错误121。
- 预期：校验类422、旧version409，错误可定位且无答卷/gate增长；真实存储失败必须同时回滚gate，恢复后同request_id可成功。
- 实际：全部非法HTTP请求均拒绝且responses=gate_seq=0；注入存储失败捕获真实OperationFailure(code121)，重试前0/0，恢复后同ID200且1/1。注入用例直接服务调用异常，不声称正常API应向用户返回Mongo内部异常。
- 状态：**PASS**；关联调用 27 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-R02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_submissions.py:138 `test_invalid_values_for_all_four_types_do_not_write_response_or_gate`](../tests/test_submissions.py#L138)；[test_submissions.py:149 `test_non_bson_or_nonfinite_json_answers_are_422_without_writes`](../tests/test_submissions.py#L149)；[test_submissions.py:169 `test_submit_recomputes_path_and_rejects_tampering_without_write`](../tests/test_submissions.py#L169)；[test_submissions.py:450 `test_actual_mongodb_validation_failure_rolls_back_gate_and_retry_can_succeed`](../tests/test_submissions.py#L450)。

### TC-R03 允许重复与重试幂等

- 步骤：分别关闭/开启repeat主动提交两次；固定request_id重放规范等价内容，再变内容，关闭后重复这些请求。
- 具体输入：repeat=false/true；两个新ID；同ID multi[y,x]→[x,y]、number1.0→1；文本改为不同回答；关闭后原ID/冲突ID/全新ID。
- 预期：禁重复200/409共1份；允许200/200共2份；规范等价重放同回执而不增加；同ID异内容409；关闭后已成功ID仍可重放，新ID410。
- 实际：主动重复与规范等价/冲突断言全部通过；原始及重放id/submitted_at相同，replayed=true；关闭后仍只有1份、gate1。
- 状态：**PASS**；关联调用 3 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-R03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_submissions.py:197 `test_repeat_switch_applies_to_new_requests`](../tests/test_submissions.py#L197)；[test_submissions.py:209 `test_canonical_retry_replays_same_receipt_and_conflicting_payload_rejected_even_after_close`](../tests/test_submissions.py#L209)。

### TC-R04 匿名与身份隔离

- 步骤：以另一个登录账号填写匿名及非匿名问卷，重复提交；拥有者读取整卷/单题统计与明细，对响应作字段及原身份值检查。
- 具体输入：anonymous=true/false；禁repeat；responses白名单id/version/answers/path/submitted_at/anonymous，非匿名可额外username；检查respondent_id/user_id/request_id/payload_hash/password_hash等。
- 预期：匿名不对创建者暴露账号或私有标识；非匿名仅按契约显示username；数据库保留私有身份支持判重，第二次409；非owner无读取权限。
- 实际：匿名/非匿名两组均通过；匿名序列化结果无填写者username和私有ID/哈希，请求标识不泄漏；非匿名username与真实存储身份对应。当前无导出接口。
- 状态：**PASS**；关联调用 5 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-R04`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_statistics.py:226 `test_response_whitelist_and_anonymity`](../tests/test_statistics.py#L226)；[test_submissions.py:234 `test_authenticated_filler_can_submit_but_only_owner_can_read_statistics_and_details`](../tests/test_submissions.py#L234)；[test_submissions.py:254 `test_anonymous_projection_and_private_duplicate_identity`](../tests/test_submissions.py#L254)。

### TC-R05 并发、关闭与截止竞争

- 步骤：四种Barrier(10)同步请求并读真实数据库；用事件控制真实gate前后与关闭/截止更新的顺序；已打开分享后改截止；同命令$$NOW相等探针；真实错误121回滚。
- 具体输入：10个独立账号、同账号10新ID、同ID10次、repeat=true的10新ID；closes_at为服务端当前+60秒/-5秒；close/deadline分别先于gate及gate先行；相等探针将$closes_at替换为该命令$$NOW。
- 预期：四模式分别10成功10份、1成功9冲突1份、10回执1份且一次新建、10成功10份；先close/deadline则410与0/0，先gate则200与1/1；相等拒绝；失败事务回滚。
- 实际：四模式响应200/409及数据库/gate/去重人数逐项相符；close_before_gate与deadline_before_gate为410/0/0，gate_before_close和gate_before_deadline为200/1/1，随后新提交410；截止前200、后410；相等探针410/0/0；错误121恢复重试200/1/1。完整ID与回执在submission_experiments。此10并发夹具不证明性能容量。
- 状态：**PASS**；关联调用 12 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-R05`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_submissions.py:279 `test_ten_synchronized_submissions_reconcile_receipts_and_database`](../tests/test_submissions.py#L279)；[test_submissions.py:322 `test_lifecycle_write_before_actual_gate_rejects_submission`](../tests/test_submissions.py#L322)；[test_submissions.py:357 `test_actual_gate_before_lifecycle_write_commits_accepted_response`](../tests/test_submissions.py#L357)；[test_submissions.py:404 `test_deadline_before_and_after_server_time_rechecks_already_opened_link`](../tests/test_submissions.py#L404)；[test_submissions.py:418 `test_exact_deadline_equality_is_rejected_by_real_gate_comparison_expression`](../tests/test_submissions.py#L418)；[test_submissions.py:450 `test_actual_mongodb_validation_failure_rolls_back_gate_and_retry_can_succeed`](../tests/test_submissions.py#L450)。

### TC-S01 可手算统计夹具

- 步骤：发布一次并开启repeat，以两名填写者通过submit API写三份合法路径，读整卷及每一道单题；关闭后复读；补测大有限数均值。
- 具体输入：u1:r1 A,[X,Y],甲,gate=answer,10；u2:r2 B,[Y],乙,answer,20；u1:r3 A,[X],丙,gate=skip跳end，不答number；end均null。大数夹具为3个最大double、3个最小负double、[1e308,-1e308,1e308]。
- 预期：3份/2人；单选A2次1人/B1次1人；多选X2次1人/Y2次2人；文本甲乙丙；数字2份2人、values10/20、mean15；每单题等于整卷对应项，关闭后结果仍可读；有限均值无溢出。
- 实际：手算值全部匹配；r3数据库path不含number且answers无number，三份均真实API成功；end回答数0；大数三组mean有限且等于预期近似，原始values保留，单题/整卷一致。
- 状态：**PASS**；关联调用 4 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-S01`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_statistics.py:108 `test_hand_calculated_fixture_and_every_single_question_match`](../tests/test_statistics.py#L108)；[test_statistics.py:264 `test_large_finite_numeric_mean_via_actual_submissions`](../tests/test_statistics.py#L264)。

### TC-S02 空答、零数据与当前版本隔离

- 步骤：创建两卷相同number/text题ID；查询零数据，给另一卷99，给本卷空答后再给0；检查每卷唯一发布快照及当前version1；审阅统计查询过滤。
- 具体输入：两卷同id/同名可选题；other:number99,text另一份问卷；first:number=null,text空白；再number0,text字符串0；大数三组同S01；草稿统计对照。
- 预期：另一卷不污染零数据；空答保存空answers且path保留，可提交但不参与均值；零有效数字mean=null；0有效mean0；每卷version1且结果隔离；草稿409。
- 实际：first零数据0份/0人；other99后first不变；空答后1份1人、values空/mean null；再0后2份1人、数字仅[0]且mean0；other仍1份/mean99。每卷发布快照恰1份，输出version1；源码查询同时按survey_id和当前version过滤。未提供或伪造v2，未实测多次发布迁移。
- 状态：**PASS**；关联调用 5 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-S02`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_statistics.py:149 `test_zero_data_optional_null_zero_and_same_question_in_other_survey`](../tests/test_statistics.py#L149)；[test_statistics.py:208 `test_draft_has_no_statistics_and_owner_check_precedes_state_disclosure`](../tests/test_statistics.py#L208)；[test_statistics.py:264 `test_large_finite_numeric_mean_via_actual_submissions`](../tests/test_statistics.py#L264)。

### TC-S03 统计权限与原文内容

- 步骤：拥有者读三份手算夹具的整卷/单题/明细，陌生及未登录用户逐路由请求；查未知题和草稿；匿名/非匿名白名单逐字段比较数据库。
- 具体输入：三份合法夹具与A/B不同账号；statistics、statistics/single、responses；unknown题ID；draft；anonymous true/false。
- 预期：拥有者得到选项计数/人数及全部文本数字原文；未知题404、草稿409；外人404、未认证401，且先owner再披露状态；匿名仅白名单。
- 实际：各路由权限与未知题/草稿状态符合预期，读请求未改3份答卷；原文与持久化答案逐项相符，非匿名仅追加username、匿名不含身份。页面提交份数/人数区别见E01。
- 状态：**PASS**；关联调用 4 条，全部 passed（多组共享调用不重复计总数）。
- 证据：[全量原始记录](../results/S5/full-tests.json)，筛选 `phase=call, cases包含TC-S03`；[控制台](../results/S5/full-tests.txt)。
- 测试源码：[test_statistics.py:191 `test_statistics_and_raw_response_routes_require_owner_and_login`](../tests/test_statistics.py#L191)；[test_statistics.py:208 `test_draft_has_no_statistics_and_owner_check_precedes_state_disclosure`](../tests/test_statistics.py#L208)；[test_statistics.py:226 `test_response_whitelist_and_anonymity`](../tests/test_statistics.py#L226)。

### TC-E01 简单页面完整链路

- 步骤：S4 在真实页面注册创建者、创建四类题/单选跳转并发布，另一用户登录填写，触发校验并回改首题；S5 同一问卷实际提交，拥有者看整卷/单题及匿名明细；S6 关闭并在填写页验证拒绝。
- 具体输入：合成问卷“第一阶段浏览器验收问卷”，S4多选空答、文本“甲”、数字11触发错误，回改早期单选验证路径变为2题及后续值清空；S5最终成功提交为“完整填写”、多选“校验”、文本“页面提交”和数字8，version1。S4预览文本“测试通过”没有当作S5最终提交内容。
- 预期：页面校验和服务端路径一致；合法提交真实落库，拥有者可读统计/原文；匿名身份不显示；关闭后分享入口拒绝且原答卷不丢失。
- 实际：页面原4题路径/回改2题、必答/长度/范围错误及清空行为符合预期；提交回执 `4e44da8d-62e6-4ac2-b1ad-21f82d55b5b6`；真实MongoDB1份答卷/1人、均值8，匿名不显示填写者用户名；关闭后拥有者DOM显示closed、分享页显示关闭/到期，数据库status=closed且答卷仍1份。不是一次全新连续自动脚本：证据明确串联S4、S5、S6同一合成问卷的分阶段浏览器操作。
- 状态：**PASS**；浏览器汇总时间2026-10-15 22:06:36 +08:00，基线e7255c3；浏览器测试库 `lab4_test_browser_c1c681babaaa4f6ea467e211959d4878`。具体数据库状态核对由主agent读取完成，浏览器库为验收留证数据，不包含于245项测试库清理声明。
- 证据：[E01实际记录](../results/acceptance/browser-e01.json)、[S4门禁/错误与回改说明](../results/S4/gates.md)、[完整路径](../results/S4/browser-full-path.txt)、[回改后路径](../results/S4/browser-jump-path.txt)、[S5最终提交读回](../results/S5/browser.json)、[提交回执截图](../results/S5/browser-receipt.jpg)、[单题统计截图](../results/S5/browser-single-statistics-visible.jpg)、[匿名明细](../results/S5/browser-anonymous-response.txt)、[最终统计截图](../results/acceptance/browser-final-statistics.jpg)、[关闭后的拥有者DOM](../results/acceptance/browser-closed-owner.txt)、[关闭后的分享DOM](../results/acceptance/browser-closed-share.txt)、[关闭分享截图](../results/acceptance/browser-closed-share.jpg)。
- 源码/执行方式：人工驱动真实浏览器，步骤见E01 JSON；业务断言源码对应J05的 `tests/test_rules.py` 及统计/提交文件，不能把它们当作本次浏览器操作脚本。关闭点击的CUA工具曾返回CDP timeout，随后DOM与MongoDB均证实操作已成功，未盲目重试；工具超时原样记录。

### TC-E02 干净环境复现

- 步骤：从业务基线e7255c3导出独立源目录，校验105个文件摘要；按README从environment.yml新建conda环境、从示例生成配置；独立端口/目录初始化真实MongoDB副本集及Schema/索引；运行全量测试和真实HTTP流程；停止应用后以不同PID启动，重读同一统计、明细、会话和回执；最后核对并停止自有MongoDB实例。
- 具体输入：新环境 `lab4-survey-repro-be6b0d`；源目录 `.runtime/reproduction/project`；MongoDB端口27085、副本集lab4repro、HTTP端口8005、业务库lab4_reproduction、数据目录为该源目录下的`.runtime/mongo`；seed20261015；合成创建者/填写者与四类题、跳转、version1。HTTP问卷ID `9a566d50-7896-48c7-85b4-b749afd81030`，回执ID `f518d39e-34e1-478c-b03f-bb2d909ff592`。
- 预期：README命令可执行，Schema/索引正确，业务只持久化MongoDB；新环境测试通过，独立进程重启仍能读同一答卷且幂等重放不增加；只停止本次创建并核验归属的进程，仅清理精确测试库，保留需要留证的数据。
- 实际：新conda环境创建命令最终exit0；Python3.11.17、FastAPI0.143.1、Uvicorn0.54.0、PyMongo4.19.0、Pydantic2.14.1、Jinja2 3.1.6、HTTPX0.28.1、pytest9.1.1、python-dotenv1.2.4。Schema43/43通过、全量245/245通过（无失败/跳过，exit0），各自UUID测试库精确清理PASS。真实HTTP流程23步（含两次启动健康检查）状态均符合预期；应用PID26896→19376，重启前后统计/明细相等，会话与原回执幂等重放仍有效；1份/1人、数字均值10，关闭后分享读取410。应用进程清理PASS。
- 清理异常与补救：原包装器在读取PowerShell的GBK进程命令输出时按UTF-8解码失败，随后清理读取器触发AttributeError，原 `reproduction.json` 为FAIL、exit1，错误输出保留。补救仅处理自有MongoDB端口27085、PID17332；先核对命令行、精确dbPath与副本集归属，再正常shutdown并验证进程退出，exit0；保留业务库users2/sessions2/surveys1/survey_versions1/responses1及数据目录。没有重跑或改写原245条测试、43项Schema检查或23步HTTP结果。
- 状态：**PASS**；实际复现开始22:14:31 +08:00，清理补救及最终汇总22:19:55 +08:00；[最终记录](../results/acceptance/reproduction-final.json)状态PASS、最终exit0，原包装器exit1仍可定位。验证范围是同一Windows主机、复用已安装的MongoDB可执行文件，使用新的conda环境、源目录、配置、MongoDB实例/目录、端口及应用进程；没有声称新操作系统/另一台机器复现。
- 证据：[源快照摘要](../results/acceptance/reproduction-source.json)、[conda最终创建记录](../results/acceptance/reproduction-conda-result.json)、[安装日志](../results/acceptance/reproduction-conda-install.txt)、[环境/拓扑](../results/acceptance/reproduction-environment.json)、[真实Schema结果](../results/acceptance/reproduction-schema.json)、[真实全量测试结果](../results/acceptance/reproduction-tests.json)、[测试控制台](../results/acceptance/reproduction-tests.txt)、[原包装器FAIL](../results/acceptance/reproduction.json)、[原错误输出](../results/acceptance/reproduction-runner-error.txt)、[清理补救](../results/acceptance/reproduction-cleanup-repair.json)、[最终PASS](../results/acceptance/reproduction-final.json)。最终JSON的commands保留逐命令/时间/退出码/输出位置，http_steps保留23步预期与实际，processes保留两次PID及停止前归属核验。
- 执行命令/源码位置：[README](../README.md)、[配置生成](../scripts/configure_env.py)、[副本集初始化](../scripts/init_mongo.py)、[数据库初始化](../scripts/init_db.py)、[Schema检查](../scripts/check_schema.py)、[测试夹具/证据收集](../tests/conftest.py)、[完整业务断言](../tests/test_admin.py)及本报告各业务组源码。实际命令为 `conda env create --file environment.yml --name <new-reproduction-environment> --yes`、`python scripts/configure_env.py`、`python scripts/init_mongo.py --port 27085 --replica-set lab4repro --output results/acceptance/reproduction-environment.json`、`python scripts/init_db.py`、`python scripts/check_schema.py --output results/acceptance/reproduction-schema.json`、`python -m pytest tests --evidence results/acceptance/reproduction-tests.json -q`、`python -m uvicorn survey_app.main:app --host 127.0.0.1 --port 8005`；运行前后均执行流程结构检查。

## 范围澄清、异常与修复证据

TC-S02 原计划写“不同发布版本的同名题”，但S1已采纳D07一期一次发布且冻结配置。S6将不可合法构造的v2子例显式修订为当前version1查询过滤及同题ID跨问卷隔离：公开API实测每卷唯一快照/输出version1/两卷0与99不混合；[统计源码](../survey_app/statistics.py#L27)的查询同时约束survey_id与当前version。此为源码审阅加合法API证据，不是以伪造v2进行的跨发布迁移测试。计划中的零数据、空答、跳过、原文、均值和隔离预期未降低。

TC-R05“恰好截止”使用真实MongoDB表达式探针：保留原门禁表达式后，将截止操作数 `$closes_at` 替换成同一命令的 `$$NOW`，使严格大于成为 `$gt:["$$NOW","$$NOW"]`，实际410、responses/gate均0。该探针只验证同一数据库表达式的相等边界；实际字段的截止前后及生命周期并发另外实测，不能声称两个命令在同一毫秒恰好相等。

保留的历史问题与处理：

- S3审阅发现畸形Origin、无长度头流式超限和日期数字转换问题，修复后管理回归35/35；[首次控制台](../results/S3/admin-tests-initial.txt)、[修复后记录](../results/S3/admin-tests-repaired.json)、[门禁](../results/S3/gates.md)均保留。首次23项是当时范围的通过结果，不冒称它发现了所有新增边界。
- S4首次浏览器进程仍载入旧questions模块，next导入失败；核对并重启自己进程后重新走链路通过。[原错误日志](../results/S4/first-browser-error.log)及[S4门禁](../results/S4/gates.md)保留，未删除失败历史。
- 数字均值初始诊断显示3个或7个最大有限double在旧算法上OverflowError；[纯Python诊断](../results/S5/mean-diagnostic.json)保留，修复后3个真实API大数回归包含于S01/S02，不把诊断本身当MongoDB验收。
- Schema旧CLI曾忽略help造成一次额外实际运行，[额外运行记录](../results/S5/schema-unplanned-rerun.json)保留并与[S5门禁](../results/S5/gates.md)说明；修复后的[CLI检查](../results/S5/schema-cli-check.json)43项通过。Schema证据验证字段/索引，不能替代业务断言。
- 原始控制台的Starlette/HTTPX弃用warning保留：固定依赖当前实际测试通过，且E01真实HTTP浏览器验证通过；未来兼容性不能由当前结果保证。该warning有解释，不改为无警告。流程结构检查的0ERROR/0WARN与此运行时warning是不同计数。
- E01关闭点击CDP timeout已记录，后续独立DOM/数据库核对成功；未把工具异常隐去，也未因超时重复关闭写操作。
- E02前3次conda调用编排记录分别为exit1、exit_code=null（不能当作成功）、exit1；[尝试1](../results/acceptance/reproduction-conda-result-attempt1.json)、[尝试2](../results/acceptance/reproduction-conda-result-attempt2.json)、[尝试3](../results/acceptance/reproduction-conda-result-attempt3.json)及各自输出保留，最终新建环境exit0。之后业务验证通过，但MongoDB清理包装器曾exit1；[原失败](../results/acceptance/reproduction.json)与[错误输出](../results/acceptance/reproduction-runner-error.txt)保留，[补救](../results/acceptance/reproduction-cleanup-repair.json)只核验并停止自有进程，未重跑业务、未删除保留数据。[最终PASS](../results/acceptance/reproduction-final.json)明确引用原失败和补救，而非覆盖原记录。

报告汇总期间只审阅既有JSON、日志及源码，不运行应用或重复业务测试。26组已按上述证据验收；S6阶段门禁及S7最终交付仍由主执行者依workflow核对、记录并推进，本报告不代替其状态操作。

## 附：六类要求的真实响应片段

正文各组的“输出”以预期断言表述；为补足“输入→输出”成对证据，这里按指导文件六类要求各取一次真实 HTTP 请求与响应，全部来自隔离实例与隔离库的一次连续执行（脚本 `.runtime/audit-stage1/capture_samples.py`，完整片段见 [http-response-samples.json](../results/stage1-audit/http-response-samples.json)）。ID、分享码与时间为该次运行的真实值，未保存凭据与会话 cookie。

| 类别 | 请求 | 状态 |
| --- | --- | --- |
| 创建问卷 | `POST /api/surveys` | 201 |
| 添加题目与跳转规则 | `PUT /api/surveys/{id}` | 200 |
| 发布问卷 | `POST /api/surveys/{id}/publish` | 200 |
| 跳转逻辑（q1 选“手机”） | `POST /api/fill/{code}/next` | 200 |
| 校验（多选超过上限） | `POST /api/fill/{code}/next` | 422 |
| 校验（数字题非整数） | `POST /api/fill/{code}/next` | 422 |
| 提交问卷 | `POST /api/fill/{code}/submit` | 200 |
| 统计（整卷） | `GET /api/surveys/{id}/statistics` | 200 |
| 统计（单题） | `GET /api/surveys/{id}/statistics/q3` | 200 |
| 答卷明细 | `GET /api/surveys/{id}/responses` | 200 |

```json
// 创建问卷 → 201
{"id":"9bb337bc-0085-441d-8d66-083ec80e21fa","title":"响应片段样例问卷","description":"用于测试报告附录",
 "allow_anonymous":false,"allow_repeat":true,"closes_at":null,"status":"draft","revision":0,"version":null,
 "share_code":"IiOk2tsoChvEfIjg","share_url":"/survey/IiOk2tsoChvEfIjg","questions":[],"rules":[],
 "created_at":"2026-10-16T13:22:57.443612+00:00","updated_at":"2026-10-16T13:22:57.443612+00:00"}

// 跳转逻辑：q1 选“手机”(o4) 后，服务端把下一题定为 q4 并返回实际路径 → 200
{"path":["q1","q4"],"next_question_id":"q4","complete":false,"answers":{"q1":"o4"}}

// 校验：多选超过“最多 2 项” → 422
{"error":{"code":"validation","message":"多选答案超过最多选择数量","question_id":"q2"}}

// 校验：整数题给 1.5 → 422
{"error":{"code":"validation","message":"此数字题必须填写整数","question_id":"q3"}}

// 提交问卷 → 200（回执；同 request_id 重试会返回同一 id 且 replayed=true）
{"id":"4a94ece0-0525-4d49-ab80-7e8e7ad6d9fc","submitted_at":"2026-10-16T13:22:57.575000+00:00","replayed":false}

// 统计（整卷）→ 200，节选
{"survey_id":"9bb337bc-0085-441d-8d66-083ec80e21fa","version":1,"submissions":1,"respondents":1,
 "questions":[{"id":"q1","type":"single","answered_submissions":1,"answered_people":1,
   "options":[{"id":"o1","label":"笔记本电脑","count":1,"people":1},{"id":"o2","label":"台式机","count":0,"people":0}]},
  {"id":"q3","type":"number","answered_submissions":1,"answered_people":1,"values":[30],"mean":30.0}]}
```
