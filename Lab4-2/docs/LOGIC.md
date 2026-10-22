# 第二阶段关键逻辑

本文件的依据是已采纳的 D11–D18（见 [DECISIONS.md](DECISIONS.md)）、[library.py](../survey_app/library.py)、[questions.py](../survey_app/questions.py) 与 [service.py](../survey_app/service.py)。一阶段的校验、路径、提交与统计逻辑未改动，见一阶段文档 `Lab4-1/docs/LOGIC.md`；本文只写第二阶段新增的关键路径与它们对一阶段行为的依赖。

## 1. 三个层次：实体、版本、问卷副本

- 实体 `questions`：身份与元数据。`current_version` 指向最新版本号，`owner_id` 决定权限，`title`/`type` 冗余最新版本的值，便于列表与检索。
- 版本 `question_versions`：不可变内容。`(question_id, version)` 唯一，写入后不再更新。
- 问卷副本：`surveys.draft.questions` 与 `survey_versions.questions` 里的一道题是“内容字段 + `id` + 可选 `question_version`”。填写、发布、统计只读问卷副本，因此题目库出问题不影响已发布问卷的填写与统计。

三者的关系是“复制内容 + 记录版本号”，不是实时引用。复制发生在导入时（`import_into_survey`），版本号由服务端按所选版本写入，客户端不能自选一个与内容不符的号码（见第 5 节）。

题目内容的校验复用一阶段的同一个校验器：`library._content`（`library.py:33-38`）把请求字段拼成一道“以题目 ID 为题号”的问卷题目，交给 `questions.check_definition`，因此“单选至少两个选项”“多选 min≤max”“数字界值有限”等规则与一阶段完全一致；`canonical`（`library.py:88-94`）反向把版本文档变成问卷题目对象，并补上 `question_version`。

## 2. 版本演进：追加、恢复、另存

| 操作 | 入口 | 新版本号 | `derived_from` | `supersedes` | `restored_from` | 对实体 |
| --- | --- | --- | --- | --- | --- | --- |
| 新建题目 | `create_question`（`library.py:151`） | 1 | null | null | null | 插入实体，`current_version=1` |
| 追加版本 | `new_version`（`:221`） | `current+1` | `{question_id, current}` | `current` | null | 条件更新 `current_version`、`title`、`type`、`updated_at` |
| 恢复旧版 | `restore_version`（`:244`） | `current+1` | `{question_id, 源版本}` | `current` | 源版本号 | 同上，内容取源版本 |
| 另存新题 | `fork`（`:265`） | 新题目的 1 | `{源题目, 源版本}` | null | null | **新建**实体，`origin=forked` |

规则细节：

- 版本号永远由服务端算，客户端不能提交 `version`。`new_version` 与 `restore_version` 都在事务里做两件事：插入新版本 + 以 `{_id, current_version: 旧值}` 为条件更新实体。并发下两个请求会算出同一个版本号，后插入者触发 `(question_id, version)` 唯一键冲突，被映射为 409 `revision`（“题目已被他人修改，请刷新后重试”）。
- 恢复不删除中间版本、不回滚 `current_version`。例：v1 → v2 → 恢复 v1 得到 v3（内容等于 v1），历史是 v1、v2、v3 三条，`current_version=3`；这满足“看到版本关系”与“找回旧版本”，同时保持“版本号只增”的可解释性。
- `fork` 只要求源题目**可访问**（所有者或被共享者），不要求所有权；新题目的所有者是当前用户，新题目的 v1 带着指回源题目的 `derived_from`，因此“另存”之后仍能追溯来源。`fork` 可以指定 `version` 参数另存旧版本，省略时用 `current_version`。
- 恢复的来源版本必须存在（否则 404），且内容要重新过一遍校验器（`_content(_content_of(source))`）；历史版本在写入时已合法，重跑校验是防御性的，正常情况下不会失败。

## 3. 发布冻结与版本共存

- 问卷侧冻结沿用一阶段：发布在事务内校验整卷、写入唯一 `survey_versions` 快照并 `$unset` 草稿；`published_version` 固定为 1，没有“问卷第二版”。
- 第二阶段的写接口都会先查问卷状态：`import_into_survey` 与 `revise_in_survey` 对非 `draft` 一律 409 `immutable`；一阶段的 `PUT /api/surveys/{id}` 同样只允许草稿。因此“已发布问卷里的题目不能被修改”由**状态检查**保证，而不是靠界面隐藏按钮。
- 题目实体的演进与问卷冻结互不影响：题目可以继续产生 v2、v3，问卷快照里仍是导入时的内容与版本号。不同问卷可以在导入时选不同版本（`version` 参数），这就是“多版本共存”。

## 4. 导入与三种修订模式

导入（`import_into_survey`，`:471-486`）：校验问卷属于本人且为草稿 → 取可访问的题目实体 → 确定钉住版本（参数或 `current_version`）→ 该版本必须存在 → 草稿里不能已有同 ID 题目（409 `exists`）→ 题目数不得达到 100（422）→ 追加 `canonical(version_doc)` → 以 revision 条件保存整卷。

修订（`revise_in_survey`，`:488-528`）在同一份草稿上替换一道题，三种模式的副作用边界：

| 模式 | 前置条件 | 对题目库 | 对草稿 | 对跳转规则 |
| --- | --- | --- | --- | --- |
| `draft_only` | 该题在草稿里 | 不改 | 用请求内容替换，且**删除** `question_version`（变成本地题） | 不改（题号不变） |
| `new_version` | 该题在题目库且当前用户是所有者（否则 403） | 追加版本，`current_version+1` | 换成新版本的 `canonical`（带新版本号） | 不改（题号不变） |
| `fork` | 该题在题目库 | 新建题目（`origin=forked`） | 换成新题目的 v1（`id` 改变） | 把 `source`/`target` 等于旧题号的规则改写为新题号 |

`draft_only` 的“删除版本标记”是有意的：内容已与库中版本不同，若继续声称是某版本，统计与使用情况会把它错算成库中题目。删除标记后它成为问卷本地题目，只参与本卷统计。

`fork` 必须改写规则：题目 ID 变了，若规则仍指向旧 ID，保存时 `check_definition` 会因“规则来源/目标题不存在”而拒绝整卷。改写只针对该题号，其他规则原样保留。

## 5. 版本标记的复核（`normalize_question_refs`）

`normalize_question_refs`（`library.py:96-122`）在一阶段保存问卷的路径上被调用（`service.py:81-85`），规则是“保留标记当且仅当四项都成立”：

1. 该题 ID 存在对应实体；
2. 当前用户对该实体有权限（所有者或被共享者）；
3. `(question_id, question_version)` 对应的版本文档存在；
4. 问卷里这道题的五个内容字段（`type`、`title`、`required`、`options`、`validation`）与版本文档逐字段相等（深比较）。

任一不成立就 `pop("question_version")`，把该题降级为问卷本地题目，**不报错**。理由：报错会让“导入后微调”的正常流程无法保存；删除标记能同时阻止“声称是 v7 却提交别的内容”的伪造，以及“被取消共享后继续保留标记”的越权引用。

注意它只清理标记，不校验内容本身——内容合法性仍由随后的 `check_definition` 负责；两步顺序不能颠倒，否则伪造的标记会先被写进校验器的输入。

## 6. 共享与权限判定

- 可访问性 `_accessible(question_id, user_id, owner_only=False)`（`:63-71`）：先取实体（不存在 404），所有者直接通过；`owner_only=True` 时非所有者一律 404；否则查 `question_shares`，有记录才通过，无记录 404。
- 共享 `share`：先 `_accessible(owner_only=True)`，再按 `username_key = username.casefold()` 找被共享者（不存在 404），共享给自己 422，重复共享由唯一索引转 409。
- 取消共享 `unshare`：删除 `(question_id, grantee_id)`，删除数为 0 返回 404。取消后对方再访问题目、使用情况、统计都得到 404，但对方**已经导入自己问卷的副本**不受影响（副本是快照，不回收）。
- 题库：所有题库操作都按 `{_id, owner_id}` 查，非所有者一律 404；题库条目引用题目时用 `_accessible`（不要求所有权），因此被共享者可以把他人题目收进**自己的**题库——这是接口层能力，页面只为所有者显示该入口（见 [REQUIREMENTS.md](REQUIREMENTS.md) R21 的未覆盖项）。

状态码的分工：题目级越权用 404（不泄露存在性）；问卷修订里“题目存在但你不是所有者”用 403（题目已通过问卷上下文暴露）；其余冲突用 409，输入不合法用 422。

## 7. 使用情况的推导

`usage`（`:391-417`）不读链接集合，直接查两处：

1. `surveys.find({"draft.questions.id": qid})` —— 草稿问卷（多键索引 `ix_surveys_draft_question`）。每行 `version=null`、`editable=true`、`question_version` 取草稿里该题的值（可能为 null，表示本地修改）。
2. `survey_versions.find({"questions.id": qid})` —— 已发布快照（多键索引 `ix_survey_versions_question`）。每行 `version=快照版本`、`status="published"`、`editable=false`；问卷标题与所有者从 `surveys` 批量补取。

因为发布时 `$unset` 草稿，同一份问卷不会同时出现在两个分支里，所以不会重复计数。`usage_count` 就是行数。可见性没有过滤：被共享者也能看到所有者问卷的行（与统计不同，见下节与 [REPORT_STAGE2.md](REPORT_STAGE2.md) 第 10 节）。

## 8. 跨问卷统计

`cross_survey_statistics`（`:420-468`）的算法：

1. 取实体并判断 `is_owner`；不可访问 404。
2. 反查所有含该题 ID 的发布快照：`survey_versions.find({"questions.id": qid})`，同时批量取这些问卷的 `title`、`owner_id`。
3. 逐份快照过滤：问卷不存在则跳过；**非所有者且问卷不属于自己则跳过**（`scope="own surveys only"` 的实现点，`:435-436`）。
4. 在该快照的题目数组里找该题定义；找不到则跳过（理论上不会发生）。
5. 读该快照的答卷：`responses.find({"survey_id", "version"})`（走 `ix_responses_survey_version`），逐份取 `answers[qid]`；值为 `None` 视为未答，不计入。
6. 每有一个非空回答，就在两个桶里各计一次：总桶 `buckets`（按题型）与版本桶 `per_version[question_version]`；同时累加该快照的 `answered`。
7. 汇总：`aggregate` 由总桶生成，`by_question_version` 由版本桶生成，`surveys` 是每份问卷的明细，`total_answered` 是明细之和，`survey_count` 是明细条数，`scope` 按第 1 步的身份给出。

分桶与汇总的细节（`_accumulate`/`_summary`，`:558-595`）：单选按选项值计次；多选对每个被选项各计一次；数字收集为浮点列表并算均值；文本收集原值（每桶最多 200 条）。选项标签从**该快照的题目定义**里取，按选项 ID 合并进 `labels`。

为什么要按快照而不是按当前版本统计：答卷是在某个发布版本下提交的，选项含义由那一版定义。若把不同版本的选项按 ID 硬合并，标签可能已经变了；因此结果同时给总聚合与按版本分桶，让读者自己判断是否可合并。已知的不完美：同一选项 ID 在不同版本里标签不同时，总聚合的标签取“最后写入 labels 的定义”，`by_question_version` 才能看到各版本自己的标签。

## 9. 一阶段数据迁移

`migrate_question_library.migrate(db, apply=...)` 的算法：

1. 先 `initialize_schema(db)`，保证目标集合与索引存在。
2. `collect(db)` 扫描 `surveys`（草稿）与 `survey_versions`（快照），按题目 ID 归并出“该题的一份内容 + 它出现在哪些位置”；所有者取所在问卷的 `owner_id`。
3. 过滤：非 UUID 题号记入 `skipped_non_uuid`（实体主键要求 UUID）；同一 ID 内容不同记入 `content_variants`（不选边）。
4. 逐条处理：实体已存在 → `skipped_existing`；定义过不了 `check_definition` → `invalid`；否则准备实体（`origin=migrated`）与 v1 两个文档，`apply=True` 时才写入，单条失败记 `failed` 并继续。
5. 返回报告（`questions_found`、`created`、`skipped_existing`、`skipped_non_uuid`、`content_variants`、`invalid`、`applied`），CLI 追加 `database_scope` 与 `finished_at` 后落盘。

为什么从不改写问卷文档：一阶段快照是历史答卷的唯一解释依据，改写它会让“当时的题目是什么”无法证明；而第二阶段所有读取路径都按题目 ID 查数组，所以“问卷不动、只补实体”足以让老数据参与使用情况与统计。测试用 `sha256(repr(sorted(document.items())))` 对 `surveys` 与 `survey_versions` 全文档做指纹，断言迁移前后相同。

## 10. 并发、事务与错误边界

- 事务：`LibraryService.transaction` 使用 `snapshot` 读、`majority` 写、`primary` 读偏好；新建题目（实体 + v1）与追加/恢复版本（版本 + 实体条件更新）在这类事务里完成。共享、题库、题库条目是单文档写入，不开事务。
- 唯一索引是并发正确性的最终依据：`(question_id, version)`、`(question_id, grantee_id)`、`(owner_id, bank name)`、`(bank_id, question_id)`；应用层只把 `DuplicateKeyError` 翻译成 409，不用“先查再插”冒充唯一性。
- 不一致的可能窗口（代码阅读，未构造复现）：追加/恢复版本的实体条件更新没有检查 `matched_count`；若 `current_version` 已被别的原因改变而同号版本尚未插入，可能出现“版本已插入、实体 `current_version` 未推进”。当前只有这两条写入路径会改 `current_version`，且都伴随同号插入，因此窗口需要异常路径才能触发。
- 错误映射：404 不存在/无权；403 只有两处（跨站 Origin、修订模式 `new_version` 但非所有者）；409 分 `exists`/`revision`/`immutable`/`not_stored`；422 输入或配置不合法；503 数据库不可用。

## 11. 实现入口

| 文件 | 职责 |
| --- | --- |
| [library.py](../survey_app/library.py) | 题目、版本、共享、题库、使用情况、跨问卷统计、问卷集成 |
| [db.py](../survey_app/db.py) | 五个新集合的校验器、19 个索引、`initialize_schema` |
| [main.py](../survey_app/main.py) | 22 条新路由与 `/library` 页面 |
| [models.py](../survey_app/models.py) | 请求模型（`QuestionInput`、`ShareInput`、`BankInput`、`BankPatch`、`BankItemInput`、`BankVersionInput`、`ImportQuestionInput`、`RevisionInput`） |
| [service.py](../survey_app/service.py) | 草稿保存时调用 `normalize_question_refs`；发布冻结沿用一阶段 |
| [questions.py](../survey_app/questions.py) | `question_version` 字段校验；题目/规则/答案校验 |
| [library.js](../survey_app/static/library.js) | 页面交互；所有判断以服务端返回为准 |

## 12. 已知缺口（未修复、未验证）

- 跨问卷统计按题目 ID 匹配，不校验该快照里的题目是否真的来自题目库（没有 `question_version` 也计入，键为 `None`→字符串 `"None"`）。代码阅读推断：任意登录用户可在自己的问卷里用同一题目 ID 建一道本地题并发布、作答，其回答会被计入所有者的跨问卷统计；若同一题目同时存在整数版本键与 `None` 键，`sorted(per_version.items())` 可能抛 `TypeError` 导致 500。**本轮没有构造复现**，也没有对应用例。
- 使用情况与统计的可见范围不一致（第 7、8 节）。
- 题库条目钉住的版本号没有“版本已删除”的清理路径（版本本身不可删除，因此只会长期保留）。
- 统计没有分页，也没有按时间或问卷版本过滤的参数。

## 补充（2026-10-22）：题库 pin 与“加入问卷”的版本选择

`LibraryService.import_into_survey` 的版本选择顺序：显式 `version` → 题库条目 `question_version` →
题目 `current_version`。因此题库条目钉住的版本是**推荐的默认值**，不是强制锁定；问卷加入后仍以
`question_version` 记录当次实际使用的版本，已发布快照继续冻结在该版本上。

## 补充（2026-10-22 第二轮）：归档与分享链接

- **归档**只改 `questions.status`，不删除任何版本：已发布问卷、统计与已加入的草稿继续可用；归档后该题从“我的题目/共享给我的”列表消失、拒绝新的加入请求、并吊销全部分享链接；恢复为 `active` 后重新可选。
- **分享链接**保存 `sha256(token)` 而不是令牌明文，链接本身不绑定账号；任何登录用户可预览并“领取”，领取即在 `question_shares` 写入一条授权（唯一索引保证幂等），领取者随后可像普通被共享者一样使用该题；吊销或归档后令牌立即失效。
- 权限边界：创建/吊销链接只有所有者；链接不能把“修改题目”的权限授予他人（被共享者仍只能 fork）。

### 补充（2026-10-22 第四轮）：链接时效、题库归档与统计上限

- 分享链接在 `_link_by_token` 里统一校验：吊销 → 404；`expires_at <= now` → 410 `expired`；`uses >= max_uses` → 410 `exhausted`。`uses` 只在**首次**插入 `question_shares` 时递增，所以同一账号重复领取不消耗次数。
- 题库条目在返回时带 `archived` 标记；`add_bank_item` 拒绝已归档题目。归档不删除条目，避免与“题目仍可统计”矛盾。
- 跨问卷统计的问卷上限改为参数 `limit`（默认 200、上限 500），并继续用 `truncated` 标明截断，取代原先写死的 200。
