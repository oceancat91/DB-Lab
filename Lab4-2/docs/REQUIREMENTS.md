# 第二阶段需求依据与追踪清单

来源文件：[大作业一：需求变更.docx](../大作业一：需求变更.docx)，18,037 字节，SHA-256 `D9E5BDD8594810923570495CB22B0D8A992889FFF9B140E1607C700CB008DF1D`，本机文件修改时间 2026-10-22 17:29:53（Asia/Shanghai）。2026-10-22 用 python-docx 直接读取 OOXML 正文段落共 76 段、表格 0 个，按“一”至“八”逐条核对。本文不声称已验证 Word 页码、版式、批注或修订记录。

任务说明中提到的抽取文本 `.runtime/audit-stage2/stage2-word-text.txt` 在当前工作树中不存在（`.runtime` 下只有 `mongo/`、`stage2/e2e_http.py`、`mongod.pid`、`mongod.log`）。因此本文的原文引用直接来自上述 docx 正文抽取，不是转述二手文本；这一点按“不补造来源”的纪律单独说明。

第一阶段需求 R01–R14 的定义、验收与真实结果见 [Lab4-1 需求清单](../../Lab4-1/docs/REQUIREMENTS.md)，本文只新增 R15–R22，不重述一阶段行为。阶段二新增决定的编号为 D11–D18，见 [DECISIONS.md](DECISIONS.md)；用例见 [TEST_PLAN.md](TEST_PLAN.md) 与 [TEST_REPORT.md](TEST_REPORT.md)。

## 来源分层：原文措辞、项目决策与未知

| 层次 | 内容 | 本文的处理 |
| --- | --- | --- |
| 原文硬要求（“期望效果”逐条） | 一至七每条给出 3–4 条“期望效果”；八只给用户反馈与示例，没有“期望效果”条目 | 全部落为 R15–R22 的“原文要点”；R22 的口径缺口显式标注 |
| 原文未定义、需项目解释 | “共享”是复制内容还是授予使用权；“恢复旧版本”是回滚还是追加；“历史版本”是否可删；题库条目跟随最新版还是钉住某版；跨问卷统计对被共享者可见多少；谁能改题、谁能建版本 | 由 D11–D18 定义为项目解释，标明不是教师另行确认 |
| 原文只有示例 | “你的年龄”“老师做的题目学生直接用”“A 问卷用旧题、B 问卷用新题”“v1 → v2 → v3” | 只作为理解场景的依据，不当作字段、界面或测试数据规范 |
| 一阶段既有语义 | 发布快照冻结、revision 乐观并发、登录后匿名、四类题型校验、发布后不可编辑 | 直接复用（R17 依赖一阶段冻结语义），不重新定义 |
| 未知 | 教师对“共享后仍可继续使用同一个题目”是否要求“所有者改版后被共享者同步看到新内容” | 未验证；本项目按“被共享者可自行选择版本、不自动跟随”实现，见 D13 |

原文“八”没有写出统计口径（按份数还是按人数、是否分版本、是否包含他人的问卷）。这些按一阶段 D08 与二阶段 D17 外推，属于项目解释。

## 验收编号定义

自动化测试编号（对应用例步骤见 [TEST_PLAN.md](TEST_PLAN.md)，真实结果见 [TEST_REPORT.md](TEST_REPORT.md)）：

| 编号 | 覆盖主题 |
| --- | --- |
| TC-L01 | 题目实体的创建、列表、检索与配置校验 |
| TC-L02 | 他人题目不可见与越权拦截 |
| TC-L03 | 版本追加式历史与恢复 |
| TC-L04 | 共享后的使用授权、另存（fork）与取消共享 |
| TC-L05 | 已发布问卷冻结与不同问卷钉不同版本 |
| TC-L06 | 客户端伪造 `question_version` 被剥离 |
| TC-L07 | 修订三模式（draft_only / new_version / fork）的副作用边界 |
| TC-L08 | 题库条目的版本钉住、显式更新与唯一性约束 |
| TC-L09 | 使用情况、跨问卷统计与一阶段数据迁移 |

文档验收编号：

| 编号 | 核对对象 |
| --- | --- |
| DOC-Q01 | [DATABASE.md](DATABASE.md) 与 [db.py](../survey_app/db.py)：五个新集合、字段校验、19 个索引与查询的对应关系 |
| DOC-Q02 | [API.md](API.md) 与 [main.py](../survey_app/main.py)：路由、请求/响应、权限矩阵与 403/404/409/422 语义 |
| DOC-Q03 | [LOGIC.md](LOGIC.md) 与 [DECISIONS.md](DECISIONS.md)：版本演进、冻结、共享、统计与迁移口径一致 |
| DOC-Q04 | [TEST_PLAN.md](TEST_PLAN.md)、[TEST_REPORT.md](TEST_REPORT.md) 与 [http-e2e.json](../results/stage2/http-e2e.json)：用例、自动化测试函数与 34 步 HTTP 证据可追踪 |
| DOC-Q05 | [REPORT_STAGE2.md](REPORT_STAGE2.md) 与 [AI_USAGE.md](AI_USAGE.md)：完成报告与 AI 记录真实、含未验证项 |

## 一至八与 R15–R22 的对应

| 原文序号 | 原文标题 | 需求 ID |
| --- | --- | --- |
| 一 | 希望可以保存常用题目，方便以后重复使用 | R15 |
| 二 | 希望可以把题目分享给别人使用 | R16 |
| 三 | 希望修改题目时不要影响已经做好的问卷 | R17 |
| 四 | 希望系统能记录题目的修改历史 | R18 |
| 五 | 希望同一个题目的不同版本可以同时存在 | R19 |
| 六 | 希望能查看某个题被哪些问卷使用 | R20 |
| 七 | 希望能建立题目库 | R21 |
| 八 | 希望可以查看单个题目的统计结果（跨问卷） | R22 |

### R15 保存常用题目并在新问卷中复用（原“一”）

原文要点：“用户可以创建题目并保存”“创建新问卷时可以从已有题目中选择”“一个题目可以被多个问卷使用”；示例为“你的年龄”这个题在很多问卷里都用。

落地口径：题目是独立实体（`questions`），内容存在不可变版本（`question_versions`）里；导入问卷时把某一版本的内容**复制**进草稿并写入 `question_version`，因此“多个问卷使用同一题目”是指共享同一个题目 ID 与版本号，而不是共享同一份可被改写的文档。列表、详情与导入入口见 [library.py](../survey_app/library.py)：`create_question`（第 151 行）、`list_questions`（第 175 行）、`detail`（第 198 行）、`import_into_survey`（第 471 行）。

实施：EXP-101、EXP-102、EXP-103。验收：TC-L01、TC-L09；DOC-Q01、DOC-Q03。

自动化测试：`tests/test_library.py::test_question_creation_listing_and_validation`（创建返回 `current_version=1`、列表与按题型/关键词检索）、`::test_import_rejects_duplicates_and_published_surveys`（导入成功路径与重复导入）。

未覆盖：每卷 100 题上限只在代码里判断（`import_into_survey`），未构造“99 题后再导入”的边界用例；列表接口固定 `limit(200)`，未测超量截断。

### R16 把题目共享给别人使用（原“二”）

原文要点：“可以把题目共享给其他用户”“其他用户可以在自己的问卷里使用这些题目”“共享后仍然可以继续使用同一个题目”；示例为“老师做的题目，学生可以直接拿来用”。

落地口径：共享是**使用授权**，不是复制、不是转移所有权。`question_shares` 一条 `(question_id, grantee_id)` 表示授权；被共享者可以查看、导入自己的问卷、另存（fork）为新题目，但不能追加版本、不能再次共享、不能删除；取消共享后立即失去访问（接口返回 404）。实现见 `share`（第 273 行）、`unshare`（第 288 行）、`shared_with_me`（第 185 行）与 `_accessible`（第 63 行）。

实施：EXP-102、EXP-103。验收：TC-L02、TC-L04；DOC-Q02、DOC-Q03。

自动化测试：`tests/test_library.py::test_sharing_allows_reuse_but_not_modification`（共享后导入成功、被共享者建版本被拒 404、fork 成功且 `derived_from` 指向源版本、取消共享后 404）、`::test_question_of_another_owner_is_not_visible`、`::test_share_pairs_and_bank_items_are_unique`。

未覆盖：没有“共享给一组人/公开链接/只读 vs 可用”的授权级别；共享只按已存在用户名精确匹配，无邀请流程；撤销共享不会回收对方已导入问卷里的副本（这是版本快照的必然结果，但无专门用例）。

### R17 修改题目不影响已发布的问卷（原“三”）

原文要点：“已经发布的问卷里的题目不能被修改”“如果需要改题目，应该生成新的题目”“旧问卷仍然保持原来的内容”；示例为“去年的问卷不能因为今年改题而变”。

落地口径：草稿可以编辑；发布时把整卷题目冻结为一阶段既有的 `survey_versions` 快照；发布（含关闭）之后 `PUT /api/surveys/{id}`、导入、修订一律 409 `immutable`。改题只能落在题目实体上产生新版本，旧快照保持原内容。界面据此把“恢复/改版”与“旧卷不受影响”写在页面上（[library.html](../survey_app/templates/library.html) 第 79 行、[library.js](../survey_app/static/library.js) 第 309 行）。

实施：EXP-103。验收：TC-L05、TC-L06；DOC-Q03。

自动化测试：`::test_published_question_snapshot_survives_new_versions`（发布后建新版本，已发布卷仍是旧标题与 v1；对已发布卷 PUT 返回 409；新问卷导入到 v2）、`::test_import_rejects_duplicates_and_published_surveys`、`::test_client_cannot_claim_a_version_it_does_not_match`。

未覆盖：`closed` 状态走同一个 409 分支，但没有单独用例构造“发布→关闭→再编辑”。

### R18 题目修改历史与恢复（原“四”）

原文要点：“可以看到题目的历史版本”“可以知道新题是从哪个题改来的”“可以恢复旧版本”；示例为“v1 → v2 → v3，希望能看到这几个版本之间的关系”。

落地口径：版本**只追加**，`(question_id, version)` 唯一，任何操作都不原地改写旧版本或删除中间版本；“恢复旧版本”= 以旧版本内容**新增**一个版本（`restored_from` 记录来源版本号，`supersedes` 记录被替代的当前版本号），当前版本号因此继续增长。每个版本另有 `derived_from` 记录改自哪个题目的哪个版本。实现见 `new_version`（第 221 行）、`restore_version`（第 244 行）、`_insert_version`（第 136 行）。

实施：EXP-102、EXP-103。验收：TC-L03；DOC-Q01、DOC-Q03。

自动化测试：`::test_versions_are_append_only_and_restorable`（v2 的 `derived_from` 指向 v1、v1 在库中逐字段不变、恢复后 `current_version=3` 且 `restored_from=1`、重复插入同版本触发唯一键冲突）。

未覆盖：没有删除、归档或压缩历史的接口（`questions.status` 的枚举里有 `archived`，但没有路由会写入它）；恢复只支持“恢复到某个已存在版本”，不支持把恢复指定为新题目的 v1（那是 fork）。

### R19 同一题目的不同版本共存（原“五”）

原文要点：“可以基于一个题创建新版本”“新版本可以单独修改”“不同问卷可以使用不同版本”；示例为“A 问卷用旧题，B 问卷用新题”。

落地口径：`questions.current_version` 表示“最新版本”，但导入时可以用 `version` 参数钉住任意已存在版本；不同问卷可以钉不同版本，互不影响。问卷内改题提供三种模式：`draft_only`（只改本卷副本，脱离题目库，`question_version` 被去掉）、`new_version`（给题目实体追加新版本并让本卷指向它，仅所有者可用）、`fork`（另存为新题目并让本卷指向新题目的 v1，同时改写引用旧题号的跳转规则）。实现见 `revise_in_survey`（第 488 行）。

实施：EXP-103。验收：TC-L05、TC-L07；DOC-Q02、DOC-Q03。

自动化测试：`::test_two_surveys_can_pin_different_versions_and_usage_lists_both`（旧卷钉 v1、新卷钉 v2 并存）、`::test_revision_modes_change_only_what_they_should`（三种模式各自只改应改的部分）、`::test_fork_with_rules_rewrites_the_reference`。

未覆盖：同一问卷里同一题目只能出现一次（重复导入 409），因此不支持“一卷内两版本并存”；原文也没有提出该场景。

### R20 查看题目被哪些问卷使用（原“六”）

原文要点：“可以查看题目被哪些问卷使用”“修改时可以决定是否创建新版本”。原文这一条没有“期望效果”下的示例段落。

落地口径：使用情况不另建链接集合，而是从既有的两个题目数组反查：草稿 `surveys.draft.questions.id` 与发布快照 `survey_versions.questions.id`，分别由多键索引 `ix_surveys_draft_question`、`ix_survey_versions_question` 支撑。返回每行含问卷 ID、标题、状态、问卷版本、题目版本、是否本人问卷、是否可改；草稿行 `editable=true`，快照行 `editable=false`。“决定是否创建新版本”在页面上表现为三种修订模式（见 R19）。实现见 `usage`（第 391 行）。

实施：EXP-102、EXP-103、EXP-104。验收：TC-L05、TC-L09；DOC-Q01、DOC-Q02。

自动化测试：`::test_two_surveys_can_pin_different_versions_and_usage_lists_both`（两条使用记录，已发布行 `editable=false`、草稿行 `editable=true`，各自题目版本正确）。

未覆盖与已知边界：使用情况**不做可见范围过滤**——被共享者调用同一接口也能看到所有者问卷的标题与状态，这与 R22 的“被共享者只看自己问卷”不一致，见 D17 与 [REPORT_STAGE2.md](REPORT_STAGE2.md) 第 9 节；接口没有分页或条数上限。

### R21 建立题目库（题库）（原“七”）

原文要点：“可以管理题库”“可以把题加入题库”“可以从题库选题”“题库里的题可以更新版本”。

落地口径：`question_banks` 是所有者私有的命名集合，`question_bank_items` 的每个条目**钉住一个具体版本**（`question_version`），并可与题目当前版本比较得出 `outdated`；`PATCH /api/banks/{bank_id}/items/{question_id}` 把条目显式更新到指定版本或最新版本，不自动跟随。“从题库选题”的实现是题库面板 + “加入我的草稿问卷”（导入接口），不是一步生成整卷。实现见 `create_bank`（第 296 行）、`bank_detail`（第 321 行）、`add_bank_item`（第 355 行）、`update_bank_item`（第 370 行）、`remove_bank_item`（第 383 行）。

实施：EXP-102、EXP-103、EXP-104。验收：TC-L08；DOC-Q01、DOC-Q02。

自动化测试：`::test_bank_items_pin_versions_and_can_be_updated`（同名题库 409、重复加入 409、升级后 `outdated=true` 而钉住版本不变、PATCH 后变 v2、移出后计数归零）、`::test_share_pairs_and_bank_items_are_unique`。

未覆盖：题库不能共享给他人（原文只要求共享题目，没有要求共享题库）；被共享者可以把他人题目加入**自己的**题库（`add_bank_item` 使用可访问性检查），但页面只在“我是所有者”时才显示“加入题库”，该路径只有接口层可达、无界面入口。

### R22 跨问卷的单题统计（原“八”）

原文要点（无“期望效果”列表，只有反馈与示例）：“系统的统计只能看某个问卷的结果，我希望能看某一道题在所有问卷中的回答情况”“‘你的年龄’这个题，我在很多问卷里都用了，我想知道所有问卷里大家年龄的总体分布”。

落地口径：以题目 ID 反查所有 `survey_versions` 快照，按每份快照的 `survey_id + version` 读取 `responses`，只统计该版本里题目的实际定义；结果给出总体聚合、按题目版本分桶（`by_question_version`）、按问卷明细（`surveys`）、`total_answered` 与 `survey_count`。可见范围用 `scope` 明示：所有者 `all surveys`，被共享者 `own surveys only`（只聚合自己的问卷）。题型口径沿用一阶段 D08：选择计次并可给标签、文本给原值（最多 200 条）、数字给均值（跳过空答）。实现见 `cross_survey_statistics`（第 420 行）与 `_accumulate`/`_summary`（第 558、577 行）。

实施：EXP-103、EXP-104。验收：TC-L09；DOC-Q02、DOC-Q03。

自动化测试：`::test_cross_survey_statistics_aggregate_one_question`（3 份问卷 3 条回答、`scope=all surveys`、按版本 2/1 分桶；被共享者 `scope=own surveys only` 且只统计自己 1 份）、`::test_cross_survey_statistics_of_number_and_text`（数字均值 25、文本值重复保留）。

未覆盖与已知边界：只统计已发布快照里的回答（草稿不能填写，因此无回答可统计）；没有分页、没有时间范围、没有按问卷版本过滤的参数；`by_question_version` 的键是 Python `str()` 结果，本地修改（无 `question_version`）的题目会得到字符串 `"None"`，而这个分支没有自动化用例覆盖（详见 [REPORT_STAGE2.md](REPORT_STAGE2.md) 第 9 节）。

## 与第一阶段的关系

- 复用而非重写：题目配置校验仍走一阶段的 `questions.check_definition`，第二阶段只是把同一校验器套到题目实体的内容上（`library._content`，第 33 行），因此单选题“至少两个选项”等规则与一阶段完全一致（TC-L01 验证了单选项被拒 422）。
- 冻结语义复用一阶段的发布快照；第二阶段没有引入“问卷第二版”，`published_version` 仍固定为 1（[service.py](../survey_app/service.py) 第 99 行）。
- 一阶段数据不迁移也能读：第二阶段所有查询都按题目 ID 从既有数组反查，因此老问卷在迁移前后都能被使用情况与统计接口识别（迁移只是补齐题目实体，见 [LOGIC.md](LOGIC.md) 与 [migrate_question_library.py](../scripts/migrate_question_library.py)）。

## 未采纳或未实现的部分

原文字面上可以延伸、但本项目**没有**实现的能力，单独列出以免被误读为已完成：题目市场/公开题库、题库共享、题目删除与归档、历史版本删除或压缩、共享权限分级（只读/可改）、跨问卷统计的选项标签统一映射、统计与使用情况的分页、把“修改时决定是否创建新版本”做成发布后的追认操作。以上均无接口、无页面、无测试。
