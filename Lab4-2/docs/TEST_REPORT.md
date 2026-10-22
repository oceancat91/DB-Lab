# 第二阶段测试报告

本文件记录第二阶段的真实执行结果、失败历史和未执行项。判定依据是仓库内的证据文件，不是本文的叙述；本文不声称作者之外的任何人重新运行过这些测试。

## 1. 结论摘要

| 项 | 实际结果 | 证据 |
| --- | --- | --- |
| 全量自动化测试 | 收集 260 项，**260 通过**，0 失败、0 跳过、0 收集错误，退出码 0 | [pytest.json](../results/stage2/pytest.json) |
| 二阶段自动化用例 | 15 项（`tests/test_library.py` 14 + `tests/test_migration.py` 1） | 同上，按文件统计 |
| 一阶段基线用例 | 245 项（管理 35、规则 155、提交 46、统计 9） | 同上 |
| Schema / 索引 / 校验器 | 58 项检查全部 PASS，10 个集合、19 个索引 | [schema-check.json](../results/stage2/schema-check.json) |
| 真实 HTTP 全链路 | 34 步全部 PASS，失败 0 | [http-e2e.json](../results/stage2/http-e2e.json) |
| 一阶段数据迁移 | `--apply` 对已含实体的库执行：`created=0`、`skipped_existing=2`（幂等） | [migration.json](../results/stage2/migration.json) |
| 页面可达性 | `/library` 与三个静态资源、`/health` 均 200；`library.js` 通过 `node --check` | [gates-t3.md](../results/stage2/gates-t3.md) 与第 6 节 |
| 失败历史 | 两次运行各失败 1 项（同一个迁移用例），已修复后重跑通过；原始失败文件保留 | [pytest-20261022T181406663390.json](../results/stage2/pytest-20261022T181406663390.json)、[pytest-20261022T181551828673.json](../results/stage2/pytest-20261022T181551828673.json) |

计数口径：260 = 一阶段 245 + 二阶段 15。`pytest --collect-only` 独立复核同样是 260 项（本次文档整理时执行，只收集不运行）。若在其他材料里见到“261”或“二阶段 16 项”，应以本表与 `pytest.json` 的 260/15 为准。

## 2. 运行环境与隔离

- 时间：2026-10-22 18:12–18:16（Asia/Shanghai）。`pytest.json` 记录 started `2026-10-22T18:15:15.545161+08:00`、finished `2026-10-22T18:15:51.822558+08:00`。
- 解释器与依赖：Python 3.11.17、pytest 9.1.1、FastAPI 0.143.1、PyMongo 4.19.0、httpx 0.28.1（conda 环境 `lab4-survey`）。
- 数据库：真实 MongoDB 6.0.29，单节点副本集 `lab4rs`，`writable_primary=true`，`read_preference=primary`，`tz_aware=true`。**没有使用 mock 证明事务、唯一约束或权限。**
- 测试库：`tests/conftest.py` 每次会话生成 `lab4_test_api_<32 位 uuid>`；会话结束统计各集合文档数后 `drop_database`，并断言库中不再有集合。`pytest.json` 的 `cleanup` 记录为：`status=PASS`，删除前文档数 users 143、sessions 141、surveys 110、survey_versions 91、responses 65、questions 19、question_versions 27、question_shares 2、question_banks 2、question_bank_items 1，`remaining_collections=[]`。
- 合成数据：用户名 `u_` + uuid 片段，密码为固定的合成测试密码，不读取真实账号；用例之间共享同一个测试库（同一会话），因此迁移用例用“相对基线”的断言，失败与修复见第 5 节。
- Schema 检查用独立库 `lab4_test_schema_a2259475ccde4d10b805d64bd2ca3084`，同样在结束时删除（`cleanup.status=PASS`、`remaining_collections=[]`）。

## 3. 逐组用例结果

用例步骤与预期见 [TEST_PLAN.md](TEST_PLAN.md)；下表只记实际结果。

| 用例 | 关联需求 | 状态 | 自动化测试函数 | 证据 |
| --- | --- | --- | --- | --- |
| TC-L01 题目创建、列表、检索与配置校验 | R15 | PASS | `tests/test_library.py::test_question_creation_listing_and_validation` | [pytest.json](../results/stage2/pytest.json)、[http-e2e.json](../results/stage2/http-e2e.json) 第 5 步 |
| TC-L02 他人题目不可见与越权拦截 | R15/R16 | PASS | `::test_question_of_another_owner_is_not_visible` | pytest.json |
| TC-L03 版本追加式历史与恢复 | R18 | PASS | `::test_versions_are_append_only_and_restorable` | pytest.json、http-e2e 第 6–7 步 |
| TC-L04 共享、复用、另存与取消共享 | R16 | PASS | `::test_sharing_allows_reuse_but_not_modification` | pytest.json、http-e2e 第 8–10、33–34 步 |
| TC-L05 已发布冻结与不同问卷钉不同版本 | R17/R19 | PASS | `::test_published_question_snapshot_survives_new_versions`、`::test_import_rejects_duplicates_and_published_surveys`、`::test_two_surveys_can_pin_different_versions_and_usage_lists_both` | pytest.json、http-e2e 第 11–26 步 |
| TC-L06 伪造 `question_version` 被剥离 | R17 | PASS | `::test_client_cannot_claim_a_version_it_does_not_match` | pytest.json |
| TC-L07 修订三模式与规则改写 | R19 | PASS | `::test_revision_modes_change_only_what_they_should`、`::test_fork_with_rules_rewrites_the_reference` | pytest.json |
| TC-L08 题库钉版、显式更新与唯一性 | R21 | PASS | `::test_bank_items_pin_versions_and_can_be_updated`、`::test_share_pairs_and_bank_items_are_unique` | pytest.json、http-e2e 第 29–32 步 |
| TC-L09 使用情况、跨问卷统计与迁移 | R20/R22 | PASS | `::test_cross_survey_statistics_aggregate_one_question`、`::test_cross_survey_statistics_of_number_and_text`、`::test_two_surveys_can_pin_different_versions_and_usage_lists_both`、`tests/test_migration.py::test_migration_backfills_legacy_questions_without_rewriting_surveys` | pytest.json、http-e2e 第 26–28 步、[migration.json](../results/stage2/migration.json) |

## 4. 二阶段 15 个测试函数各自证明什么

| 测试函数 | 断言的核心事实 |
| --- | --- |
| `test_question_creation_listing_and_validation` | 创建返回 v1 与 `owned=true`；列表、题型过滤、关键词过滤正确；非法定义与多余字段被 422 拒绝且不落库 |
| `test_versions_are_append_only_and_restorable` | v2 的 `derived_from` 指向 v1；v1 在库中未被改写；恢复生成 v3 且 `restored_from=1`、内容等于 v1；同版本重复插入触发唯一键冲突 |
| `test_question_of_another_owner_is_not_visible` | 非所有者对详情、追加版本、统计都得到 404 |
| `test_sharing_allows_reuse_but_not_modification` | 共享后对方可见、可导入、可 fork；追加版本 404；取消共享后 404；共享给不存在用户 404 |
| `test_published_question_snapshot_survives_new_versions` | 发布后题目升版不影响已发布卷与快照；对已发布卷 PUT 409；新问卷导入到新版本 |
| `test_client_cannot_claim_a_version_it_does_not_match` | 内容与所声称版本不符时，保存成功但 `question_version` 被删除 |
| `test_two_surveys_can_pin_different_versions_and_usage_lists_both` | 两份问卷分别钉 v1 与 v2；使用情况两行，已发布行不可改、草稿行可改 |
| `test_revision_modes_change_only_what_they_should` | `draft_only` 去掉标记且不动题目库；`new_version` 推进到 v2；`fork` 换 ID 且不动源题目 |
| `test_fork_with_rules_rewrites_the_reference` | fork 后引用旧题号的跳转规则被改写为新题号 |
| `test_bank_items_pin_versions_and_can_be_updated` | 题库默认钉当前版本；升版后 `outdated=true` 而钉住版本不变；空体 PATCH 更新到最新；移出后计数归零；同名/重复加入冲突 |
| `test_cross_survey_statistics_aggregate_one_question` | 3 份问卷 3 条回答的聚合与按版本 2/1 分桶；被共享者范围仅自己 1 份 |
| `test_cross_survey_statistics_of_number_and_text` | 数字题 `count=2`、`mean=25`；文本题原值保留且重复值计数正确 |
| `test_import_rejects_duplicates_and_published_surveys` | 重复导入 409；已发布问卷再导入 409 |
| `test_share_pairs_and_bank_items_are_unique` | 重复共享对与重复题库条目都触发唯一键冲突（直接对数据库写入） |
| `test_migration_backfills_legacy_questions_without_rewriting_surveys` | dry-run 不写库；apply 新建实体与 v1；`surveys` 与 `survey_versions` 的文档哈希不变；重复 apply 全部跳过；迁移后题目参与使用情况与统计；升版不影响已发布卷 |

## 5. 失败历史与修复

| 运行 | 时间（+08:00） | 结果 | 失败项 |
| --- | --- | --- | --- |
| 第 1 次 | 18:12:42–18:13:19 | 259 通过 / 1 失败，exit 1 | `tests/test_migration.py::test_migration_backfills_legacy_questions_without_rewriting_surveys`，`AssertionError` |
| 第 2 次 | 18:13:29–18:14:06 | 259 通过 / 1 失败，exit 1 | 同上 |
| 第 3 次 | 18:15:15–18:15:51 | **260 通过**，exit 0 | — |

失败原因与修复：该用例在同一会话的共享测试库里运行，前面的用例已经创建了题目实体，因此“迁移应新建 1 个实体”的绝对断言与库中已有状态冲突。修复方式是先跑一次 `migrate(apply=False)` 取 `baseline`，断言改为 `baseline+1`（当前代码 `tests/test_migration.py:54-66`），并保留“dry-run 不写库”“问卷指纹不变”“重复 apply 幂等”的原断言。

诚实边界：证据文件只记录了失败用例名与异常类型（`AssertionError`），没有保留 pytest 的断言消息；修复前的源码也没有进入 git（唯一相关提交 `c34d04d` 已包含修复后的版本），因此**无法**逐字重放当初失败的那一行断言。两次失败记录按要求保留，未被覆盖成通过。

## 6. 真实 HTTP 与页面

- [http-e2e.json](../results/stage2/http-e2e.json)：`base_url=http://127.0.0.1:8012`，`generated_at=2026-10-22T10:11:44.802887+00:00`（即 18:11:44 +08:00），`passed=34`、`failed=0`、`status=PASS`。脚本为 `.runtime/stage2/e2e_http.py`，两名用户（`u_owner_*`、`u_mate_*`）走完版本演进、恢复、共享、三份问卷（含他人问卷）的建卷/导入/发布/打开/提交、使用情况、两种范围的统计、题库、fork 与血缘。
- 端口说明：脚本连的是 8012；README 与本文档给出的默认启动端口是 8004。两者只是运行参数不同，不能据此认为验证发生在 8004 上。
- 页面：`gates-t3.md` 记录 `/library` 与静态资源经真实 HTTP 返回 200、`library.js` 通过 `node --check`。本次文档整理时对同一运行实例（127.0.0.1:8012）做了只读 GET 复验：`/library` 200（4,880 字节）、`/static/library.js` 200（23,051 字节）、`/static/library.css` 200（3,644 字节）、`/static/app.css` 200（32,802 字节）、`/health` 200（`{"status":"ok","database":"connected"}`），`node --check survey_app/static/library.js` 退出码 0。
- **没有**截图，**没有**执行登录后的交互式浏览器会话；页面的表单、弹窗、恢复/共享/统计渲染均未验证。

## 7. Schema 与索引检查

[schema-check.json](../results/stage2/schema-check.json)：`status=PASS`、`exit_code=0`、58 项检查、命令 `python scripts/check_schema.py`、库 `lab4_test_schema_a2259475ccde4d10b805d64bd2ca3084`（已删除）。覆盖内容：

- 副本集主节点与 10 个集合存在；
- 10 个集合的 `$jsonSchema` 与代码定义一致（strict/error、`additionalProperties:false`）；
- 19 个非 `_id_` 索引全部存在，字段、唯一性与条件过滤一致（含二阶段新增的 10 个）；
- 非法文档被拒、唯一约束触发 11000、TTL 定义存在但不断言异步过期、重复初始化不丢文档。

注意：该报告内部的 `stage` 字段写 `S2`、`requirements` 写 `R01/R13`，因为复用的是第一阶段 `scripts/check_schema.py`，没有针对二阶段改标签；它实际核对到了二阶段新增的集合与索引（`validator_questions` 等检查项）。这不影响结论，但不应把该文件引用成“二阶段专用检查器”。

## 8. NOT_RUN 与未覆盖

以下项目**未执行**，不得当作通过：

- 浏览器交互与会话（含题目库页面的点击、表单、恢复、共享、统计面板渲染）。
- 二阶段接口的并发夹具（并发追加版本、并发共享、并发导入）。
- 关闭（`closed`）状态问卷上的导入/修订（只验证了已发布状态的 409）。
- 每卷 100 题上限、字段超长、导入导致整卷超过 1 MiB 的边界。
- 使用情况/统计在大量问卷与答卷下的响应时间、分页行为。
- 迁移脚本的 `skipped_non_uuid`、`content_variants`、`invalid`、`failed` 分支（有实现，没有构造数据）。
- 跨问卷统计中“同一题目 ID 被本地题复用”和 `by_question_version` 出现 `None` 键的路径（代码阅读推断的缺口，见 [LOGIC.md](LOGIC.md) 第 12 节，未复现）。
- 与其他浏览器、移动端、公网部署、TLS、认证相关的能力。

## 9. 证据索引

| 文件 | 说明 |
| --- | --- |
| [pytest.json](../results/stage2/pytest.json) | 最终一次全量运行（260 通过，exit 0） |
| [pytest-20261022T181406663390.json](../results/stage2/pytest-20261022T181406663390.json)、[pytest-20261022T181551828673.json](../results/stage2/pytest-20261022T181551828673.json) | 两次失败运行的存档（259 通过 / 1 失败） |
| [schema-check.json](../results/stage2/schema-check.json) | 集合、校验器、索引的 58 项检查 |
| [http-e2e.json](../results/stage2/http-e2e.json) | 34 步真实 HTTP 链路 |
| [migration.json](../results/stage2/migration.json) | 迁移幂等结果 |
| [gates-t0.md](../results/stage2/gates-t0.md) – [gates-t7.md](../results/stage2/gates-t7.md) | 逐门禁记录 |
| [results/stage2/environment.json](../results/stage2/environment.json) | 环境基线（MongoDB 6.0.29、`lab4rs`、27084、事务探针 PASS） |
