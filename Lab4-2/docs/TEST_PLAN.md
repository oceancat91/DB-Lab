# 第二阶段验收用例计划

本文件保存第二阶段的用例步骤与预期，不替代测试报告。预期依据 [DECISIONS.md](DECISIONS.md) 的 D11–D18 与 [REQUIREMENTS.md](REQUIREMENTS.md) 的 R15–R22，不按运行结果倒改断言。实际状态、失败历史与证据见 [TEST_REPORT.md](TEST_REPORT.md)。

覆盖面：8 条需求（R15–R22）→ 9 组用例（TC-L01–TC-L09）。每组用例对应至少一个真实自动化测试函数；能在 HTTP 层复现的，另给 [http-e2e.json](../results/stage2/http-e2e.json) 的步骤号。用例标题格式固定为 `### TC-Lxx`，供流程检查器识别。

## 通用前置与执行分层

- 环境：conda `lab4-survey`（Python 3.11.17）、MongoDB 6.0.29 单节点副本集 `lab4rs`（127.0.0.1:27084），证据 [results/stage2/environment.json](../results/stage2/environment.json)。全部自动化测试运行在真实副本集上的 `lab4_test_api_<uuid>` 库，会话结束删除该精确库。
- 账号：每次运行由 `tests/conftest.py` 生成随机用户名（`u_` + uuid 片段），密码为合成密码；不读取或复用任何真实账号。
- 数据：题目、问卷、答卷全部由用例现场构造；一阶段迁移用例另造一份“遗留问卷”，题号用 UUID。
- 分层：T4 执行接口/服务自动化测试（`tests/test_library.py`），T5 执行迁移测试（`tests/test_migration.py`），T6 用独立进程与真实 HTTP 走端到端脚本（`.runtime/stage2/e2e_http.py`，输出 `results/stage2/http-e2e.json`）。
- 判定：自动化用例以 pytest 断言为判定，HTTP 用例以“期望状态码 = 实际状态码”为判定；两者都不看界面截图。
- 反例要求：权限、冻结、重复、伪造标记这四类必须由真实请求或真实数据库状态验证，不以“界面上没按钮”代替。

## 用例与需求、实现的对应

| 用例 | 需求 | 自动化测试函数 | HTTP 步骤 | 状态 |
| --- | --- | --- | --- | --- |
| TC-L01 | R15 | `test_question_creation_listing_and_validation` | 5 | PASS |
| TC-L02 | R15/R16 | `test_question_of_another_owner_is_not_visible` | 10（同类的被共享者越权） | PASS |
| TC-L03 | R18 | `test_versions_are_append_only_and_restorable` | 6、7 | PASS |
| TC-L04 | R16 | `test_sharing_allows_reuse_but_not_modification` | 8、9、10、33、34 | PASS |
| TC-L05 | R17/R19 | `test_published_question_snapshot_survives_new_versions`、`test_import_rejects_duplicates_and_published_surveys`、`test_two_surveys_can_pin_different_versions_and_usage_lists_both` | 11–25、26 | PASS |
| TC-L06 | R17 | `test_client_cannot_claim_a_version_it_does_not_match` | — | PASS |
| TC-L07 | R19 | `test_revision_modes_change_only_what_they_should`、`test_fork_with_rules_rewrites_the_reference` | — | PASS |
| TC-L08 | R21 | `test_bank_items_pin_versions_and_can_be_updated`、`test_share_pairs_and_bank_items_are_unique` | 29、30、31、32 | PASS |
| TC-L09 | R20/R22 | `test_cross_survey_statistics_aggregate_one_question`、`test_cross_survey_statistics_of_number_and_text`、`test_two_surveys_can_pin_different_versions_and_usage_lists_both`、`test_migration_backfills_legacy_questions_without_rewriting_surveys` | 26、27、28 | PASS |

“PASS”指 pytest 的证据文件记录该用例对应的测试函数通过（[pytest.json](../results/stage2/pytest.json)：260 收集 / 260 通过 / 0 失败 / exit 0），以及 HTTP 步骤在 [http-e2e.json](../results/stage2/http-e2e.json) 中 `ok=true`；本文件不声称执行者重新运行过这些用例。

### TC-L01 题目创建、列表、检索与配置校验

关联 R15。前置：已登录用户 A。

步骤与输入：

1. A 创建单选题“你的年龄段”，两个选项，`required=true`，`note="初版"`。
2. 读取响应，再调用 `GET /api/questions` 列表；分别按 `type=text`、`q=年龄`、`q=不存在的题` 过滤。
3. 创建只含一个选项的单选题（应被拒）；创建时额外带 `owner_id`（应被拒）。

预期：创建返回 201，`current_version=1`、`owned=true`、`current.title` 与请求一致；本人列表恰含该题，题型过滤为 `[]`，关键词命中该题，未命中为 `[]`；两个非法请求都返回 422，且库中题目数仍为 1（非法请求不落库）。

自动化：`tests/test_library.py::test_question_creation_listing_and_validation`。HTTP：第 5 步（创建 201）。证据：[test_library.py](../tests/test_library.py)。

### TC-L02 他人题目不可见与越权拦截

关联 R15/R16。前置：用户 A 建题，用户 B 登录。

步骤：B 依次请求该题的详情、追加版本、跨问卷统计。

预期：三者都返回 404，且 A 的题目没有任何新增版本。用例同时检查“被共享者”在未共享时与普通用户一致（共享后的权限差别在 TC-L04）。

自动化：`tests/test_library.py::test_question_of_another_owner_is_not_visible`。HTTP：第 10 步是用例的近似场景（被共享者尝试追加版本得到 404），不是同一前置，不能互相替代。证据：[test_library.py](../tests/test_library.py)。

### TC-L03 版本追加式历史与恢复

关联 R18。前置：一道 v1 题目。

步骤与输入：

1. 追加 v2（改标题、加第三个选项），读取详情与版本列表。
2. 直接查数据库中的 v1 文档，确认标题与选项数未变。
3. 调用 `POST /api/questions/{id}/versions/1/restore`。
4. 用同一 `(question_id, version=1)` 再插一条版本（构造并发重复）。

预期：`current_version=2`；版本列表为 [1,2]；v2 的 `derived_from={question_id, version:1}`；v1 内容与最初逐字段相同；恢复返回 201 且 `current_version=3`，v3 的 `restored_from=1`、内容等于 v1；重复插入触发唯一键冲突（`DuplicateKeyError`）。

自动化：`tests/test_library.py::test_versions_are_append_only_and_restorable`。HTTP：第 6 步（新建 v2，201）、第 7 步（恢复 v1，201，`current_version=3`）。证据：[http-e2e.json](../results/stage2/http-e2e.json) 第 6–7 步。

### TC-L04 共享、复用、另存与取消共享

关联 R16。前置：用户 A（所有者）、用户 B（同事）。

步骤与输入：

1. A 按用户名把题目共享给 B。
2. B 查询“共享给我的”列表，并读取题目详情。
3. B 建一份自己的问卷，从题目库导入该题（默认当前版本）。
4. B 尝试给该题追加版本；再对同一题 `fork` 一份自己的新题。
5. A 取消共享；B 再查共享列表与题目详情。
6. A 共享给一个不存在的用户名。

预期：共享 201；B 的共享列表恰含该题且 `owned=false`、`shared_with_me=true`；导入后草稿里 `question_version=1`；B 追加版本返回 404；fork 返回 201，`owner_id` 为 B，新题 v1 的 `derived_from` 指向源题 v1；取消共享 200，B 的共享列表变 `[]`、详情 404；共享给不存在用户返回 404。

自动化：`tests/test_library.py::test_sharing_allows_reuse_but_not_modification`。HTTP：第 8 步（共享 201）、第 9 步（共享列表 200）、第 10 步（越权 404）、第 33 步（fork 201）、第 34 步（血缘 200）。

### TC-L05 已发布问卷冻结与不同问卷钉不同版本

关联 R17/R19。前置：一道题目、一份已发布问卷。

步骤与输入：

1. 建问卷一，导入该题 v1，发布，读取问卷（应为快照）。
2. 给题目追加 v2（改标题与选项）。
3. 重读问卷一；对问卷一执行 `PUT /api/surveys/{id}`；再建问卷二并导入该题（默认当前版本）。
4. 再建一份问卷，重复导入同一题；对已发布问卷再导入一次。
5. 查询使用情况，核对两份问卷各自钉住的题目版本与可改标志。

预期：问卷一发布后 `questions[0].question_version=1`、标题仍是旧标题，快照文档同样；追加 v2 后问卷一完全不变；对已发布问卷 PUT 返回 409；问卷二导入得到 v2；重复导入返回 409；对已发布问卷导入返回 409；使用情况中问卷一是已发布行（`question_version=1`、`editable=false`），问卷二仍是草稿行（`question_version=2`、`editable=true`）。

自动化：`test_published_question_snapshot_survives_new_versions`、`test_import_rejects_duplicates_and_published_surveys`、`test_two_surveys_can_pin_different_versions_and_usage_lists_both`。HTTP：第 11–25 步（三份问卷各自建卷、导入、发布、打开、提交），第 26 步（使用情况显示 v1 与 v2 并存）。

### TC-L06 客户端伪造 `question_version` 被剥离

关联 R17。前置：草稿问卷里已导入该题 v1。

步骤与输入：

1. 读出草稿里的题目对象，把 `title` 改成“伪造的标题”，保留 `question_version=1`。
2. 用 `PUT /api/surveys/{id}` 保存整卷。

预期：保存返回 200；返回的题目里**没有** `question_version`（服务端发现内容与 v1 不一致而剥离标记），题目成为问卷本地题；题目库中的版本与内容不变。

自动化：`tests/test_library.py::test_client_cannot_claim_a_version_it_does_not_match`。HTTP：无对应步骤（该行为只在自动化中验证）。

### TC-L07 修订三模式的副作用边界与规则改写

关联 R19。前置：草稿问卷里有一道来自题目库的题，另加一道本地文本题，并配一条“该题选 a 跳到文本题”的规则。

步骤与输入：

1. 对导入题执行修订 `draft_only`，改标题。
2. 再执行 `new_version`，改标题。
3. 再执行 `fork`，改标题。
4. 检查规则引用与题目实体状态；另跑一次带规则的 fork。

预期：`draft_only` 后本卷标题变化且 `question_version` 消失，题目库 `current_version` 仍为 1；`new_version` 后本卷 `question_version=2`、题目库 `current_version=2`；`fork` 后本卷题目 ID 改变、标题为分叉标题、题目库 `current_version` 仍为 2；fork 时引用旧题号的规则 `source`/`target` 被改写为新题号。

自动化：`test_revision_modes_change_only_what_they_should`、`test_fork_with_rules_rewrites_the_reference`。HTTP：无对应步骤。

### TC-L08 题库条目的版本钉住、显式更新与唯一性

关联 R21。前置：一道 v1 题目。

步骤与输入：

1. 新建题库“常用题”；再建同名题库（应冲突）。
2. 把题目（默认当前版本）加入题库；重复加入（应冲突）。
3. 给题目追加 v2，读题库详情（应显示钉住 v1、`outdated=true`）。
4. `PATCH /api/banks/{bank_id}/items/{question_id}` 空请求体（更新到当前版本）。
5. 移出条目；再查题库列表计数。
6. 直接在数据库里重复插入同一 `(bank_id, question_id)` 与同一 `(question_id, grantee_id)`。

预期：首次建库 201、同名 409；加入 201、重复 409；详情 `question_version=1`、`outdated=true`；PATCH 200 后 `question_version=2`、`outdated=false`；移出后 `items=[]`、列表计数 0；两次重复插入都触发唯一键冲突。

自动化：`test_bank_items_pin_versions_and_can_be_updated`、`test_share_pairs_and_bank_items_are_unique`。HTTP：第 29 步（建库 201）、第 30 步（加入题库 201，`outdated=true`）、第 31 步（空体 PATCH 200，改钉 v3）、第 32 步（他人看不到题库 404）。

### TC-L09 使用情况、跨问卷统计与一阶段数据迁移

关联 R20/R22（迁移部分关联 R15/R18 的兼容性）。前置：题目被 3 份已发布问卷使用（其中 1 份属于被共享者），各 1 条答卷；另有一份“一阶段遗留问卷”。

步骤与输入：

1. 所有者查询使用情况与跨问卷统计。
2. 被共享者查询同样两个接口。
3. 建一阶段遗留问卷（题目 ID 用 UUID，直接 PUT + 发布，不经过题目库），跑迁移 `--dry-run`、`--apply` 与重复 `--apply`，并在迁移前后对问卷文档取哈希。
4. 迁移后查询该题的使用情况与统计，再追加 v2，重读遗留问卷。
5. 数字题与文本题各建一份问卷、各提交两条答卷，查询单题统计。

预期：所有者 `usage_count=3`、`scope=all surveys`、`survey_count=3`、`total_answered=3`、`by_question_version` 含 1 与 2 且分别 2/1 条；被共享者 `scope=own surveys only`、只统计自己 1 份；迁移 dry-run 不写库、apply 新建 1 个实体与 v1、问卷指纹不变、重复 apply 全部 `skipped_existing`；迁移后使用情况 1 行、统计 1 份问卷；追加 v2 后遗留问卷仍是旧标题；数字题 `count=2`、`mean=25`，文本题原值重复保留。

自动化：`test_cross_survey_statistics_aggregate_one_question`、`test_cross_survey_statistics_of_number_and_text`、`test_two_surveys_can_pin_different_versions_and_usage_lists_both`、`tests/test_migration.py::test_migration_backfills_legacy_questions_without_rewriting_surveys`。HTTP：第 26 步（使用情况）、第 27 步（所有者统计）、第 28 步（被共享者统计 `own surveys only`）。

## 未纳入本计划的场景

以下场景在需求或代码里存在，但没有用例，测试报告中按“未覆盖”记录，不写成 PASS：

- 已关闭（`closed`）问卷上的导入/修订：走同一个 409 分支，只验证了已发布状态。
- 并发追加版本、并发共享、并发导入：只用唯一索引与代码路径支持，没有并发夹具。
- 每卷 100 题上限、题库条数上限：只有代码判断。
- 使用情况/统计在大量问卷下的响应时间与分页。
- 非 UUID 题号迁移（`skipped_non_uuid`）与 `content_variants` 的实际分支：脚本有实现，自动化未构造。
- 浏览器交互（点击、弹窗、恢复按钮、统计面板渲染）。
