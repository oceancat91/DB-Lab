# 第二阶段实验日志

本文件按工作包记录第二阶段的实施。阶段二的开发与运行由作者在 2026-10-22 18:00–18:17（Asia/Shanghai）完成，证据是 `results/stage2/` 下的文件；文档整理（含本文件）在其后完成。条目里凡标【本次复核】的，是文档整理时实际重新执行的只读命令；其他“命令”行是该工作包的可复现命令，**不表示**本次重新运行过。

时间来源：`pytest.json`、`http-e2e.json`、`schema-check.json`、`migration.json` 的时间戳字段，以及文件修改时间；没有逐条记录的部分写“约”或“未逐条记录”，不补造精确时刻。

阶段划分对应 [WORKFLOW.md](../../WORKFLOW.md) 第 13 节的 T0–T7；每个工作包的门禁记录在 `results/stage2/gates-tN.md`。T7（报告、文档与交付）由本次文档整理承担，证据是 `results/stage2/gates-t7.md` 与 `submission-review.json`，见文末说明。

## EXP-101 规划与需求映射（T0）

- 时间：2026-10-22，约 17:30–18:05（Word 文件修改时间 17:29:53；具体开始时刻未逐条记录）。
- 目标：读完《大作业一：需求变更》八项变更，映射为 R15–R22，给每条需求定验收编号与决策主题；确认范围仍是一门课程的问卷系统，不引入关系库或现成问卷框架。
- 改动范围：新增 [REQUIREMENTS.md](REQUIREMENTS.md)、[DECISIONS.md](DECISIONS.md)；`progress.json` 的 T0 条目与 `results/stage2/gates-t0.md`。
- 命令：用 python-docx 直接读取 docx 正文（本次整理时重复了一次抽取，见下）；核对源文件 SHA-256。
- 实际结果：正文 76 段、0 个表格，八项变更齐全（“八”只有反馈与示例，没有“期望效果”列表）；源文件 SHA-256 `D9E5BDD8…B008DF1D`，与 `progress.json` 记录一致。八项对应 R15–R22，9 组用例编号 TC-L01–TC-L09，5 个文档验收编号 DOC-Q01–DOC-Q05。决策从 D11 续编到 D18（一阶段已用 D01–D10）。
- 证据路径：[REQUIREMENTS.md](REQUIREMENTS.md)、[DECISIONS.md](DECISIONS.md)、[gates-t0.md](../results/stage2/gates-t0.md)、[progress.json](../progress.json)。
- 未验证项：教师没有对“共享”“恢复”“统计范围”的语义另行确认，D11–D18 全部是项目解释；任务说明提到的抽取文本 `.runtime/audit-stage2/stage2-word-text.txt` 在工作树中不存在，本次改用 docx 直接抽取，抽取结果没有单独落盘。
- 【本次复核】：`python -c "import docx; …"` 打印 76 段并核对八项标题；`Get-FileHash` 复核 SHA-256；`git log` 确认仓库已被重组为两阶段结构。

## EXP-102 数据模型与 Schema（T1）

- 时间：2026-10-22，约 18:00–18:07（`db.py` 等文件修改时间集中在 18:03–18:07）。
- 目标：设计题目实体、不可变版本、共享授权、题库与题库条目五个集合；给使用情况与统计补多键索引；保持一阶段五个集合结构不变。
- 改动范围：[db.py](../survey_app/db.py)（5 个新集合的 `$jsonSchema`、10 个新索引定义）、[DATABASE.md](DATABASE.md)。
- 命令：`python scripts/init_db.py`（建/同步集合与索引，不清库）；`python scripts/check_schema.py --output results/stage2/schema-check.json`。
- 实际结果：10 个集合、19 个非 `_id_` 索引全部存在；58 项检查 PASS、退出码 0；非法文档被拒、唯一约束触发 11000、重复初始化不丢文档；检查库 `lab4_test_schema_a2259475ccde4d10b805d64bd2ca3084` 用后删除。Schema 版本仍为 1——新字段 `question_version` 落在 Schema 不深入约束的对象数组里，新集合本身是新增而不是改造。
- 证据路径：[schema-check.json](../results/stage2/schema-check.json)、[gates-t1.md](../results/stage2/gates-t1.md)、[DATABASE.md](DATABASE.md)、[results/stage2/environment.json](../results/stage2/environment.json)。
- 未验证项：没有对任何查询跑 `explain`，`ix_questions_owner_title` 能否被未锚定正则利用未确认；`questions.status` 的 `archived` 枚举值没有写入路径；导入/修订路径不复查整卷 1 MiB 上限（只有 `PUT /api/surveys/{id}` 复查）。
- 【本次复核】：读取 `db.py` 的 `SCHEMAS`/`INDEXES`，与 `schema-check.json` 的 10 个集合、19 个索引逐项对齐。

## EXP-103 服务与 API（T2）

- 时间：2026-10-22，约 18:05–18:12（`library.py`、`main.py`、`models.py`、`test_library.py` 的修改时间在 18:04–18:11 之间）。
- 目标：实现题目创建/列表/详情、追加版本、恢复、fork、共享/取消共享、题库与条目、使用情况、跨问卷统计，以及问卷侧的导入与三种修订模式；补齐请求模型与路由。
- 改动范围：[library.py](../survey_app/library.py)（新增服务，约 600 行）、[main.py](../survey_app/main.py)（22 条路由 + `/library` 页面）、[models.py](../survey_app/models.py)（8 个新请求模型）、[service.py](../survey_app/service.py)（保存草稿前调用 `normalize_question_refs`）、[questions.py](../survey_app/questions.py)（接受并校验 `question_version`）。
- 命令：`python -m pytest tests/test_library.py --evidence results/stage2/pytest.json -q`（该工作包的命令；最终全量运行见 EXP-105）。
- 实际结果：14 个接口/服务测试全部通过（含版本追加式、恢复、共享与越权、发布冻结、伪造标记、两版本共存与使用情况、三种修订模式、题库钉版、跨问卷统计、唯一约束）；接口语义与权限矩阵整理为 [API.md](API.md) 与 [LOGIC.md](LOGIC.md)。
- 证据路径：[pytest.json](../results/stage2/pytest.json)（`tests/test_library.py` 14 项 call 记录全部 passed）、[gates-t2.md](../results/stage2/gates-t2.md)、[test_library.py](../tests/test_library.py)。
- 未验证项：新接口没有并发夹具；`current_version` 条件更新未检查 `matched_count` 的异常窗口只在代码阅读层面分析过；被共享者通过接口把自己的题库加入他人题目这条路径没有界面入口也没有用例。
- 【本次复核】：`python -m pytest --collect-only -q`（只收集，不运行）确认 `tests/test_library.py` 14 项；按文件统计与 `pytest.json` 的 call 记录一致。

## EXP-104 题目库页面（T3）

- 时间：2026-10-22，约 18:09–18:12（`library.html`、`library.js`、`library.css` 的修改时间；精确时刻未逐条记录）。
- 目标：给题目库一个可用页面：新建题目、我的/共享给我、详情、版本历史与恢复、共享、题库、加入草稿问卷、跨问卷统计；复用一阶段的视觉令牌，不改一阶段 `app.js`。
- 改动范围：[library.html](../survey_app/templates/library.html)、[library.js](../survey_app/static/library.js)、[library.css](../survey_app/static/library.css)；`main.py` 的 `/library` 路由。
- 命令：`node --check survey_app/static/library.js`；对运行实例（127.0.0.1:8012）发起 `GET /library`、`/static/library.js`、`/static/library.css`、`/static/app.css`、`/health`。
- 实际结果：`node --check` 退出码 0；五个请求全部 200（页面 4,880 字节、`library.js` 23,051 字节、`library.css` 3,644 字节、`app.css` 32,802 字节、`/health` 返回 `{"status":"ok","database":"connected"}`）。页面在未登录时只显示登录面板。
- 证据路径：[gates-t3.md](../results/stage2/gates-t3.md)、本文档“【本次复核】”记录。
- 未验证项：**没有**截图，**没有**登录后的交互式浏览器会话；表单提交、恢复按钮、共享弹窗、统计面板渲染都未在浏览器里验证。页面质量只到“能返回 200 且脚本语法正确”。
- 【本次复核】：2026-10-22 文档整理时对 8012 实例重做上述 5 个只读 GET（全部 200），并重跑 `node --check`（退出码 0）。

## EXP-105 测试（含失败与修复，T4）

- 时间：2026-10-22，18:12:42–18:15:51（三次运行的起止时间见 `pytest.json` 与两个存档）。
- 目标：用真实 MongoDB 覆盖 R15–R22，并修掉实现缺陷与测试自身的错误；失败记录必须保留。
- 改动范围：[test_library.py](../tests/test_library.py)（14 个测试）、[test_migration.py](../tests/test_migration.py)（1 个测试）、[models.py](../survey_app/models.py) 的 `BankVersionInput`、[main.py](../survey_app/main.py) 的题库条目 PATCH 路由。
- 命令：`python -m pytest tests --evidence results/stage2/pytest.json -q`。
- 实际结果：最终一次 260 收集 / 260 通过 / 0 失败 / exit 0，测试库 `lab4_test_api_952858181b2d4336a719ef7bb3051b62` 用后删除（`cleanup.status=PASS`、`remaining_collections=[]`）。此前两次运行各 259 通过 / 1 失败（exit 1），失败项都是迁移用例，已修复（见下）。
- 证据路径：[pytest.json](../results/stage2/pytest.json)、[pytest-20261022T181406663390.json](../results/stage2/pytest-20261022T181406663390.json)、[pytest-20261022T181551828673.json](../results/stage2/pytest-20261022T181551828673.json)、[gates-t4.md](../results/stage2/gates-t4.md)、[TEST_REPORT.md](TEST_REPORT.md)。

失败与修复（区分“有落盘证据”与“作者记录、原始输出未保留”）：

1. **题库条目 PATCH 返回 422**（有代码证据，原始响应未保留）。端到端脚本第 31 步对 `/api/banks/{bank_id}/items/{question_id}` 发空请求体，期望 200，实际得到 422，错误体指向缺少 `body.question_id`。修复：新增只含 `version` 的 `BankVersionInput`（`models.py:117-119`），路由改为 `BankVersionInput | None` 并把题号只从路径取（`main.py:269-273`）。修复后第 31 步在 [http-e2e.json](../results/stage2/http-e2e.json) 中为 200。首次 422 的响应正文没有落盘，此处只能记录作者复述的现象与修复后的代码。
2. **迁移用例断言在共享测试库里不成立**（有落盘证据）。两次运行都失败在 `test_migration_backfills_legacy_questions_without_rewriting_surveys`（`AssertionError`）。原因是同一会话前面的用例已在测试库建了题目实体，绝对计数断言不成立。修复：先跑一次 dry-run 取 `baseline`，断言改成相对 `baseline`（`tests/test_migration.py:54-66`）。存档只记录用例名与异常类型，没有断言消息；修复前源码未进 git，无法逐字重放。
3. **测试自身的三处断言错误**（作者记录，原始输出未保留，修复后的写法可在当前测试里核对）：①把“题目版本”断言成 `version` 键，实际接口字段是 `question_version`；②唯一性测试里用了非 UUID 的 `_id`，被 Schema 拒绝，改用 `uuid4()`（当前 `test_share_pairs_and_bank_items_are_unique` 中可见）；③发布前用了过期的 revision，改成先 `GET` 再取最新 `revision`（当前 `publish` 辅助函数先重读，`tests/test_library.py:57-61`）。这三处属于测试代码问题，不是产品缺陷，修复后未再复现。

- 未验证项：三处断言错误的原始 pytest 输出没有保留；没有做并发夹具；没有单独跑“只失败一次”的定位命令记录。
- 【本次复核】：`pytest --collect-only` 复核 260 项（245 + 15）；读取两个存档确认失败用例与最终通过状态。

## EXP-106 一阶段数据迁移与 HTTP 全链路（T5/T6）

- 时间：2026-10-22，18:13–18:16（`migrate_question_library.py` 18:15:58、`migration.json` finished 18:16:00、`http-e2e.json` 18:11:44）。
- 目标：把一阶段内嵌题目回填成实体，证明问卷文档不被改写、迁移幂等；再用两个真实用户走完整 HTTP 链路验收。
- 改动范围：[migrate_question_library.py](../scripts/migrate_question_library.py)（`skipped_non_uuid`、`content_variants` 与说明字段）、[test_migration.py](../tests/test_migration.py)、`.runtime/stage2/e2e_http.py`（端到端脚本，不在提交物里）。
- 命令：`python scripts/migrate_question_library.py --dry-run`；`python scripts/migrate_question_library.py --apply`；`python .runtime/stage2/e2e_http.py`。
- 实际结果：迁移报告 `questions_found=2`、`created=0`、`skipped_existing=2`、`skipped_non_uuid=[]`、`content_variants=[1dd2156d-…, 4902a2f4-…]`、`applied=true`——这是在已含实体的配置库上重跑，证明幂等而非首次回填。首次回填与“问卷逐字节不变”由迁移用例证明（最终运行通过）。HTTP 链路 34 步全 PASS：两名用户、v1→v2→恢复 v3、共享、三份问卷（含他人问卷）建卷/导入/发布/打开/提交、使用情况（`published_usage_count=3`、`versions_used=[1,2]`）、所有者统计（3 份 3 条、按版本 2/1）、被共享者统计（`scope="own surveys only"`、1 份）、题库（钉 v1 → outdated → 改钉 v3）、fork 与血缘（`derived_from` 指向 v3）。
- 证据路径：[migration.json](../results/stage2/migration.json)、[http-e2e.json](../results/stage2/http-e2e.json)、[gates-t5.md](../results/stage2/gates-t5.md)、[gates-t6.md](../results/stage2/gates-t6.md)。
- 未验证项：`--dry-run` 单独一次的输出没有落盘（`migration.json` 只有 `applied=true` 的版本）；`skipped_non_uuid`、`content_variants` 的实际分支没有构造数据；端到端脚本连的是 8012，而文档给出的默认端口是 8004；脚本没有覆盖被共享者改题、已关闭问卷、并发等路径。
- 【本次复核】：读取 `migration.json` 与 `http-e2e.json`，核对 34 步状态、关键计数字段与 `base_url`。

## T7 说明（报告、文档与交付）

T7 不是独立工作包，而是本次文档整理：补齐 [SYSTEM.md](SYSTEM.md)、[DATABASE.md](DATABASE.md)、[API.md](API.md)、[LOGIC.md](LOGIC.md)、[TEST_PLAN.md](TEST_PLAN.md)、[TEST_REPORT.md](TEST_REPORT.md)、[EXPERIMENT_LOG.md](EXPERIMENT_LOG.md)、[AI_USAGE.md](AI_USAGE.md)、[REPORT_STAGE2.md](REPORT_STAGE2.md)，并按 [progress.json](../progress.json) 的 T7 门禁核对交付物。

已知未完成/未核验：文档写完后运行 `python scripts/check_workflow.py`，结果为 ERROR=3（写报告前为 ERROR=12，其中 9 项由缺少 `REPORT_STAGE2.md` 与跨文档链接造成，补齐后消失），剩余 3 项都不在文档范围：

1. `T6：gate_review 缺少门禁 G6.2` —— `results/stage2/gates-t6.md` 只有 G6.1，缺第二条门禁记录；
2. `T7 evidence[2]：文件缺失 results/stage2/manifest.json` —— `progress.json` 把交付包清单列为 T7 证据，但该文件不存在，应由 `python scripts/package_stage2.py` 生成；
3. `progress.json：current_stage 应为 complete` —— 八个阶段都已 `passed`，`current_stage` 仍写 `T7`。

这三项需要修改 `results/` 与 `progress.json`，属交付步骤，不在文档整理范围内；本文件不把 T7 记为已验证。

## 失败记录留存说明

- 两次失败运行的结果文件保留为 `pytest-20261022T181406663390.json` 与 `pytest-20261022T181551828673.json`，没有删除或改名成通过。
- 题库 PATCH 的 422 与测试自身三处断言错误没有独立的原始输出文件，本文件明确标注为“作者记录、原始输出未保留”，不把它们写成有落盘证据的失败。
- 所有“PASS”都指向具体证据文件；没有证据的项写“未验证”。

## EXP-107 题目库页面的浏览器核验尝试（2026-10-22 Asia/Shanghai）

目标：在真实浏览器中走一遍“注册 → 打开 /library → 新建题目”，补上 EXP-103 声明的未验证项。

执行：用 agent-browser（会话 lab4-stage2-ui）依次 open /、click #register-tab、fill #username/#password、click #auth-submit，再 open /library、fill #question-title 与两个选项、click #question-submit；截图与页面文本读取各尝试一次。

实际结果：**交互流程未完成**。agent-browser 的 fill/click 返回的是命令用法文本而非执行结果，screenshot 与 errors 子命令在 Windows 管道下挂起并被终止；随后直接查询业务库确认：users 仍为 4、questions 仍为 3，且三条题目的 created_at 全部是 HTTP 全链路运行时的 10:11（UTC），没有 EXP-107 期间的写入。因此不能声称注册或建题在浏览器里成功。

有效证据：改用 Chrome 无头模式抓取未登录视图，得到 results/stage2/browser/library-anonymous.png（1280x900）。该截图显示顶栏“问卷工作台 / 我的问卷 / 题目库（当前）”、面板“登录后管理题目库”与“去登录”按钮——说明页面 HTML 与 CSS 正常加载，library.js 也已执行：登录面板正是脚本在 /api/auth/me 返回 401 后切换出来的，说明 fetch 与路由可用。

未验证（与 EXP-103 一致，不因本次尝试而改变）：登录后的题目列表、新建表单提交、版本/共享/统计面板等交互行为仍无浏览器证据，只有 HTTP 与自动化测试证据。工具限制已记录：agent-browser 在该 Windows 环境下的输出管道会挂起，后续同类验证应改用其他方式（例如自带 Playwright 或 Chrome CDP 直连）。

## 修复轮（2026-10-22 Asia/Shanghai）：按不足清单逐项修复

本轮按“风险从高到低”的清单处理了五项，其余项见文末“仍未处理”。

1. **usage 权限口径（安全）**：原实现只校验“所有者或被共享者”就返回所有使用该题的问卷行，被共享者能看到他人问卷标题与状态；cross_survey_statistics 却做了范围限制。已统一为同一口径：被共享者只看到自己问卷的行，另有 other_surveys 计数与 scope 字段说明范围。测试 	est_usage_scope_hides_other_owners_surveys 实测：所有者 usage_count=2、被共享者 usage_count=1 且 other_surveys=1，行内不出现他人标题。
2. **二阶段包混入一阶段编号目录**：init_mongo.py 默认输出仍是 
esults/S1/environment.json，导致 Lab4-2/results/S1/ 被打进二阶段包。默认路径改为 
esults/stage2/environment.json，旧文件已移动、
esults/S1 已删除；重打包后二阶段包不再含该目录。
3. **版本并发**：
ew_version/
estore_version 改为**先抢占 current_version 指针再插入版本**（唯一索引仍作第二道防线），抢占失败直接 409，避免事务重试产生重复版本。测试 	est_concurrent_new_versions_keep_a_contiguous_history 用两个已登录客户端并发提交，断言结果只可能是 201/409、至少一次成功、版本序列必须为 1..n 且 current_version 等于最大值。**说明**：TestClient 可能串行化请求，因此该测试断的是不变量而非“必然一次冲突”，这一点已在测试 docstring 写明。
4. **迁移的 non-UUID 题目**：	est_migration… 增加断言，含 q_local 这类非 UUID 题目时迁移报告必须把它列进 skipped_non_uuid，而不是静默失败（此前的失败正是数据库校验错误 121 暴露的）。
5. **保存草稿的 N+1 查询**：
ormalize_question_refs 原来在列表推导里逐题查 question_shares，已改为一次 $in 查询取“我拥有的题”与“共享给我的题”两个集合，题目数量增加时不再线性增加往返。
6. **统计上限**：cross_survey_statistics 增加 survey_limit=200 与 	runcated 标志，超过上限时如实标注，不再无界扫描。

实测：全量 python -m pytest tests --evidence results/stage2/pytest.json -q 得 **262 passed**（245 一阶段 + 17 二阶段），exit 0；其中二阶段新增 	est_usage_scope_hides_other_owners_surveys 与 	est_concurrent_new_versions_keep_a_contiguous_history 两项。

仍未处理（下一轮）：题库条目 pin 与“加入问卷”默认版本仍未打通；题目删除/归档、分享链接、CI 均未做；二阶段报告尚无 PDF/Word；README.md 正文叙事仍以一阶段为主（链接已修）；一阶段旧提交中的本人姓名未重写（待本人决定）。

## 修复轮（2026-10-22 第二轮）：题库 pin、报告载体、README 与统一检查

1. **题库 pin 打通**：`import_into_survey` 新增可选 `bank_id`，未显式给版本时使用题库条目钉住的版本
   （顺序：显式 version → 题库 pin → current_version）；接口 `POST /api/surveys/{id}/questions/import`
   与请求模型同步。测试 `test_import_from_bank_uses_the_pinned_version`：建题 → 入题库钉 v1 → 出新版本 v2 →
   用 `bank_id` 加入得到 v1、显式 `version=2` 得到 v2、不在题库中的 `bank_id` 返回 404。
2. **二阶段报告 PDF/Word**：把一阶段的生成脚本复制到 `Lab4-2/scripts/` 并改源文件与封面（第二阶段、
   2026-10-22、仓库链接），生成 `dist/Lab4-stage2-report.pdf`（752575 字节、8 页、1 个链接注释）与
   `dist/Lab4-stage2-report.docx`（53923 字节、103 段、13 张表、12 个标题、页脚含 PAGE 域），
   内容检查 8 项全 PASS。
3. **README 改为两阶段叙事**：开头改为“两阶段交付”的总述并分别指向 `Lab4-1/`、`Lab4-2/` 的测试报告，
   不再写成“只覆盖第一阶段”。
4. **统一检查脚本**：新增 `Lab4/scripts/check_all.ps1`，依次跑两个阶段的结构检查与全量测试并汇总退出码；
   不写死解释器路径（默认 PATH 上的 `python`，可用 `-Python` 覆盖），`-SkipTests` 只跑结构检查。

实测：`pytest tests/test_library.py` 17 项通过；二阶段报告生成与检查见上；`check_all.ps1` 实跑结果见
本轮命令输出。尚未处理：历史中本人姓名的重写（待本人决定）、题目删除/归档与分享链接（需求外，未做）、
题目库登录后的浏览器交互验证（受工具限制，见 EXP-107）。
