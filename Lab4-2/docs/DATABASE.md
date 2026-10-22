# 第二阶段 MongoDB 数据库设计

本设计对应 R15–R22，Schema 版本仍为 1。第二阶段**没有改写一阶段的五个集合结构**，只新增五个集合并给两个既有集合加多键索引；一阶段字段与约束保留为基线，见下文“第一阶段基线”。初始化仍由 [db.py](../survey_app/db.py) 的 `initialize_schema` 完成：对已存在集合用 `collMod` 更新校验器，对新集合 `create_collection`，再按固定名称建索引，全程不删除集合或数据（`db.py:161-173`）。

数据校验与索引的对应关系以代码为准；本文不声称已用 `explain` 验证每个索引的执行计划（未验证项见第 6 节）。

## 1. 访问模式与集合边界

第二阶段新增的访问模式：

1. 创建者在题目库里按“所有者 + 最近修改”列自己的题目，按题型或标题关键词过滤。
2. 创建者查看一个题目的全部版本、共享名单、所在题库、被哪些问卷使用。
3. 创建者或协作者把某题目的某个版本导入自己**草稿**问卷（复制内容 + 记录版本号）。
4. 创建者基于某题某版本另存为新题目（fork），或给题目追加新版本，或恢复旧版本内容。
5. 创建者把题目加入题库，题库条目钉住版本并可显式更新。
6. 任一有权限的查看者按题目反查所有已发布问卷的回答并聚合。

这些访问都是“按题目 ID 取一小批文档”或“按题目 ID 反查问卷文档”，不需要跨集合事务的大范围扫描，因此集合边界按“身份 / 版本 / 授权 / 题库 / 题库条目”划分，而不是把所有东西塞进一个题目文档。

| 集合 | 角色 |
| --- | --- |
| `questions` | 题目身份与元数据（所有者、题型、标题、当前版本、状态、来源） |
| `question_versions` | 不可变内容版本（题目正文、选项、校验、血缘） |
| `question_shares` | 一次性使用授权（题目 → 被共享者） |
| `question_banks` | 所有者私有的命名题库 |
| `question_bank_items` | 题库条目，钉住某个题目版本 |

## 2. 新增集合的字段

### 2.1 questions

| 字段 | BSON 类型 / 约束 | 说明 |
| --- | --- | --- |
| `_id` | string，UUID 模式 | 题目 ID，同时作为问卷里该题的 `id`；由服务端生成 |
| `owner_id` | string，UUID | 所有者用户 ID；权限判断的唯一依据 |
| `type` | string，枚举 `single/multi/text/number` | 与最新版本的题型一致；新建/追加版本时同步写入 |
| `title` | string，非空 | 与最新版本标题一致，供列表与搜索使用 |
| `current_version` | int/long，≥1 | 最新版本号，指向 `question_versions` 中的一条 |
| `status` | string，枚举 `active/archived` | 列表只返回 `active`；当前没有任何路由会写入 `archived` |
| `origin` | string，枚举 `created/forked/migrated` | 创建 / 另存 / 一阶段迁移 |
| `created_at`、`updated_at` | BSON date | UTC |
| `schema_version` | int/long，枚举 `[1]` | 与一阶段一致 |

### 2.2 question_versions

| 字段 | BSON 类型 / 约束 | 说明 |
| --- | --- | --- |
| `_id` | string，UUID | 版本文档 ID |
| `question_id` | string，UUID | 所属题目 |
| `version` | int/long，≥1 | 版本号，与 `question_id` 组成唯一键 |
| `type`、`title`、`required` | string / string / bool | 内容字段，参与“副本是否与版本一致”的复核 |
| `options` | array&lt;object&gt; | 选项 `{id,label}`，形状由应用层校验，Schema 只要求是对象数组 |
| `validation` | object | 题型相关约束，形状由应用层校验 |
| `derived_from` | object 或 null | 血缘：`{question_id, version}`，表示改自哪一题哪一版；Schema 只约束类型，不约束内部字段 |
| `supersedes` | int/long 或 null | 该版本替代的当前版本号 |
| `restored_from` | int/long 或 null | 恢复来源版本号；普通新版本为 null |
| `note` | string | 修改说明，可为空串 |
| `created_by` | string，UUID | 写入该版本的用户（迁移时为问卷所有者） |
| `created_at` | BSON date | UTC |
| `schema_version` | int/long | 固定 1 |

版本写入后不再更新：`new_version`/`restore_version` 只调用 `insert_one`（`library.py:136-148`），代码中不存在对 `question_versions` 的 `update_one`。

### 2.3 question_shares

| 字段 | BSON 类型 / 约束 | 说明 |
| --- | --- | --- |
| `_id` | string，UUID | 授权记录 ID |
| `question_id` | string，UUID | 被共享的题目 |
| `owner_id` | string，UUID | 授权时的题目所有者（冗余，便于审计；权限判断仍读 `questions.owner_id`） |
| `grantee_id` | string，UUID | 被共享者用户 ID |
| `created_at` | BSON date | UTC |
| `schema_version` | int/long | 固定 1 |

一行表示一次授权，取消共享即删除该行；没有“过期时间”“权限级别”字段。

### 2.4 question_banks

| 字段 | BSON 类型 / 约束 | 说明 |
| --- | --- | --- |
| `_id` | string，UUID | 题库 ID |
| `owner_id` | string，UUID | 题库所有者；题库不共享 |
| `name` | string，非空 | 所有者内唯一（见索引） |
| `description` | string，可为空 | 说明 |
| `created_at`、`updated_at` | BSON date | UTC |
| `schema_version` | int/long | 固定 1 |

### 2.5 question_bank_items

| 字段 | BSON 类型 / 约束 | 说明 |
| --- | --- | --- |
| `_id` | string，UUID | 条目 ID |
| `bank_id` | string，UUID | 所属题库 |
| `question_id` | string，UUID | 题目 |
| `question_version` | int/long，≥1 | **钉住**的版本号；不等于题目当前版本时 `outdated=true` |
| `added_by` | string，UUID | 加入者 |
| `added_at` | BSON date | UTC；重新钉版本时会被更新 |
| `schema_version` | int/long | 固定 1 |

题库条目与题目版本是引用关系（只存版本号），题目内容不在题库里复制第二份。

## 3. 内嵌与引用的取舍

**题目内容内嵌在 `question_versions` 文档内。** 选项数组、校验对象都与题目正文同文档，不拆成 `options` 集合。理由：一次版本读取就要拿到完整定义（导入、统计、详细页），拆表只会增加无收益的关联；选项按 `id` 关联而不是按标签，改标签不会被误认成另一个选项（沿用一阶段约定）。

**问卷侧仍保存题目副本。** 草稿写 `surveys.draft.questions`，发布写 `survey_versions.questions`，每道题是“内容字段 + `id` + `question_version`”。这是有意冗余：填写、发布、统计只读问卷文档就能完成，不依赖题目库可用；已发布快照因此永远解释得了当时的题目（R17）。

**版本独立成集合而不是嵌进 `questions.versions` 数组。** 三个原因：版本不可变且只能追加，独立集合可以直接用 `(question_id, version)` 唯一索引兜住并发；题目列表与详情只常读 `current_version` 与最新一版，嵌数组会让每次列表都拖出全部历史；版本数量随修改线性增长，嵌进题目文档会逼近 1 MiB 单文档上限（`_insert_version` 对版本文档单独调用 `ensure_document_size`）。

**不引入 `question_usages` 链接集合。** 使用情况完全可以从既有数组反查：`surveys.draft.questions.id` 与 `survey_versions.questions.id` 各建一个多键索引即可。若再维护一张链接表，就必须在导入、草稿保存、发布、修订（三种模式）、删除问卷等每条写入路径上同步，一旦漏同步就会出现“第二份真相”，而数组本身不可能被绕过——它就是问卷内容。代价是反查需要匹配两个集合中命中索引的文档，并且不能给“使用关系”附加自己的属性（例如首次使用时间、使用备注）；当前需求不需要这些属性，因此不建。

## 4. 索引与查询的对应关系

第二阶段新增 10 个索引定义（2 个加在既有集合上、8 个在新集合上），加上一阶段 9 个共 19 个。名称与 [db.py](../survey_app/db.py) 的 `INDEXES` 一一对应。

### 4.1 第二阶段新增

| 索引 | 字段与特性 | 服务的查询（代码位置） | 说明 |
| --- | --- | --- | --- |
| `ix_questions_owner_updated` | `owner_id` 升序 + `updated_at` 降序 | 我的题目列表（`library.py:177-183`） | 等值 + 排序前缀，避免内存排序 |
| `ix_questions_owner_title` | `owner_id` + `title` | 预留：按所有者 + 标题检索 | 当前搜索用未锚定的 `$regex`（`library.py:181`），通常无法有效利用该索引；实际计划未用 `explain` 验证 |
| `uq_question_versions_version` | `question_id` + `version`，唯一 | 取指定版本（`library.py:74`）、版本列表（`:208`）、统计与使用情况关联；并发追加版本的冲突判定 | 唯一键同时是并发保护：两个请求抢同一版本号时后者触发 409 |
| `uq_question_shares_pair` | `question_id` + `grantee_id`，唯一 | 可访问性判断（`:69`）、重复共享 409（`:281-285`） | 同一对 (题目, 用户) 只有一条授权 |
| `ix_question_shares_grantee` | `grantee_id` + `created_at` 降序 | 共享给我的列表（`:186`） | 等值 + 排序 |
| `uq_question_banks_owner_name` | `owner_id` + `name`，唯一 | 新建/改名时的同名冲突（`:301-304`、`:349-352`）、题库列表（`:315`） | 同一所有者内题库同名被数据库拒绝 |
| `uq_bank_items_pair` | `bank_id` + `question_id`，唯一 | 重复加入 409（`:362-367`）、重新钉版本与移出（`:376`、`:385`）、题库详情（`:324`） | 一题在同一题库里只有一条 |
| `ix_bank_items_question` | `question_id` | 题目详情里的 `bank_count`（`:133`）与所在题库（`:212`） | 反查“这题在哪些题库” |
| `ix_surveys_draft_question` | `draft.questions.id`（多键） | 使用情况的草稿分支（`:394`） | 多键索引直接匹配数组内对象的字段 |
| `ix_survey_versions_question` | `questions.id`（多键） | 使用情况的快照分支（`:402`）、跨问卷统计（`:423`） | 支撑“按题目反查所有已发布问卷” |

### 4.2 第一阶段基线（保留，未改结构）

| 索引 | 字段与特性 | 服务的查询 |
| --- | --- | --- |
| `uq_users_username_key` | `username_key`，唯一 | 登录、共享时按用户名找人 |
| `ttl_sessions_expires_at` | `expires_at`，TTL 0 | 会话过期清理（认证有效性由显式时间比较保证） |
| `ix_sessions_user` | `user_id` | 预留，当前代码未使用 |
| `uq_surveys_share_code` | `share_code`，唯一 | 按分享码读取问卷 |
| `ix_surveys_owner_created` | `owner_id` + `created_at` 降序 | 本人问卷列表 |
| `uq_survey_versions_survey_version` | `survey_id` + `version`，唯一 | 读取发布快照 |
| `uq_responses_request` | `survey_id` + `respondent_id` + `request_id`，唯一 | 幂等回执 |
| `uq_responses_single_submission` | `survey_id` + `respondent_id`，唯一，条件 `single_submission=true` | 禁止重复提交（部分唯一索引） |
| `ix_responses_survey_version` | `survey_id` + `version` | 一阶段统计；二阶段跨问卷统计同样按 `(survey_id, version)` 读答卷 |

对跨问卷统计而言，每条快照内部的答卷读取复用了 `ix_responses_survey_version`，所以单题统计的代价是“命中快照数 × 每卷答卷数”，随数据量线性增长，没有预聚合副本。

## 5. Schema 校验与边界

- 所有集合启用 `validationLevel: strict`、`validationAction: error` 的 `$jsonSchema`；`additionalProperties: false`，`required` 列出除显式可选外的全部字段（`_schema` 构造，`db.py:26-32`）。写入多余字段会被数据库拒绝，应用层另有 `extra='forbid'`（[models.py](../survey_app/models.py)）双重把关。
- 新集合中没有任何可选字段；`surveys.draft` 仍是可选（发布时 `$unset`），因此一阶段的“已发布形态没有 draft”不变。
- `questions._id` 与 `question_versions.question_id` 必须是 UUID 形式的字符串，因此一阶段用短题号（如 `q1`）写下的问卷题目**不能**成为实体，迁移只能报告 `skipped_non_uuid` 并让它们留在问卷内；这类问卷仍可填写、可统计，但不会出现在题目库。
- `options`、`validation`、`derived_from` 只约束到“对象/对象数组”这一层：选项数量、边界相容性、血缘内部字段由应用层校验（`questions.check_definition`），数据库不重复实现业务规则。
- 题目副本上的 `question_version` 没有加进 `$jsonSchema`：它在 `OBJECT_ARRAY` 里，Schema 不深入数组元素；校验由 `questions.py:196-201` 完成（必须是不小于 1 的整数，布尔值被拒）。这是第二阶段**不需要**提升 `schema_version` 的原因——新字段是可选的、且落在不受 Schema 深入约束的位置。
- 应用层还复核“副本内容是否等于所声称版本”（D18）。数据库无法表达这种跨文档约束，因此它是服务端逻辑，不是 Schema。
- 大小边界：版本文档与题目实体各自调用 `ensure_document_size`（1 MiB）；`PUT /api/surveys/{id}` 会检查整卷文档大小（`service.py:87`）。导入与修订走 `_save_draft`（`library.py:539-551`），只做逐字段校验、**没有**重新检查整卷文档大小——逐题上限（标题 500 码点、50 选项 × 200 码点、100 题）使越界需要极端构造，本轮未验证是否可达 1 MiB。
- 时间统一为 BSON date（UTC）；`tz_aware=True` 的连接设置使读出的日期带时区（`db.py:150-158`）。
- 多文档一致性：新建题目在事务中插入实体 + v1；追加/恢复版本在事务中“插入版本 + 条件更新实体 `current_version`”，条件为 `{_id, current_version: 旧值}`，冲突由 `(question_id, version)` 唯一索引转为 409。共享、题库、题库条目的写入是单文档操作，不需要事务。

## 6. 一阶段数据的迁移路径

现状：一阶段的题目只存在于 `surveys.draft.questions` 与 `survey_versions.questions` 的副本里，没有 `questions` 实体；使用情况与跨问卷统计按题目 ID 反查，因此**不迁移也能查**，但没有可管理的题目、版本与共享。迁移脚本 [migrate_question_library.py](../scripts/migrate_question_library.py) 负责补齐实体：

1. `initialize_schema(db)`：先建/同步集合与索引，保证写入目标存在。
2. `collect(db)`：扫描全部 `surveys`（草稿形态）与 `survey_versions`（快照），按题目 ID 归并；所有者取所在问卷的 `owner_id`。非 UUID 的历史题号（如一阶段文档示例里的 `q1`）无法满足 `questions._id` 的 UUID 校验，记入 `skipped_non_uuid` 并保留在原问卷里；同一 ID 在不同问卷中内容不同时记入 `content_variants`，脚本自带说明“不同问卷引用不同版本时内嵌内容本就不同，不是迁移冲突”，两种情况都不猜测、不覆盖。
3. 逐条处理：已有实体 → `skipped_existing` 计数（幂等）；定义不合法（`check_definition` 抛错）→ 记入 `invalid`，不猜内容；否则准备 `questions`（`origin=migrated`、`current_version=1`）与 `question_versions`（`version=1`、`note="由第一阶段内嵌题目迁移"`）两个文档。
4. `--dry-run` 只统计不写库；`--apply` 才插入，单条失败记入 `failed` 并继续其他条目。
5. 问卷与快照文档**从不被改写**：脚本没有对 `surveys`/`survey_versions` 的任何写操作。自动化用例用“对 surveys + survey_versions 全文档做 SHA-256 指纹”证明迁移前后逐字节相同（`tests/test_migration.py::test_migration_backfills_legacy_questions_without_rewriting_surveys`）。
6. 运行命令与落盘：`python scripts/migrate_question_library.py --dry-run` / `--apply`，默认写 `results/stage2/migration.json`，可用 `--output` 改路径。仓库里的 [migration.json](../results/stage2/migration.json) 是**对已含实体的配置库执行 `--apply`** 的结果：`questions_found=2`、`created=0`、`skipped_existing=2`、`applied=true`、`skipped_non_uuid=[]`，说明重复执行不会重复建实体（幂等），但它不证明“首次回填”也正确；首次回填与“问卷逐字节不变”的证明在 `tests/test_migration.py`（其结果见 [TEST_REPORT.md](TEST_REPORT.md) 与 [pytest.json](../results/stage2/pytest.json)）。
7. 回滚方式：问卷文档未被改写，所以回滚只需删除本次新建的 `questions` 与 `question_versions` 文档（按报告中列出的题目 ID）。没有提供回滚脚本，需要手工执行并先备份；本文不声称已演练。

## 7. 未验证与已知限制

- 所有索引只核对了定义与调用点，没有对真实数据集跑 `explain`，`ix_questions_owner_title` 是否能被未锚定正则利用尚未确认。
- 使用情况与跨问卷统计的反查规模未做压力测试；它们会随“命中快照数 × 每题答卷数”增长。
- `questions.status` 的 `archived` 值有定义、无写入路径；`ix_sessions_user` 仍未被使用。
- 迁移脚本对“同一题目 ID 在不同问卷里内容不同”只报告不修复，这类历史数据的统计口径仍然按 ID 合并，可能混入不同题目定义的回答（与 [REPORT_STAGE2.md](REPORT_STAGE2.md) 第 10 节的 ID 复用问题同源）。
- 数据库层没有外键：`question_shares.question_id`、`question_bank_items.question_id` 指向不存在的题目时数据库不会拒绝，只能靠应用层保证；当前没有删除题目的接口，因此不会主动产生孤儿引用。
