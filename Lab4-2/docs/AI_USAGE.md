# 第二阶段 AI 使用日志

本文件只记录实际发生的 AI 辅助，格式与一阶段 `Lab4-1/docs/AI_USAGE.md` 相同（阶段目录之间不互相链接）。学生本人的设计、修改与理解需要本人确认，agent 不代填；不得为丰富报告而编造提示词、模型版本或“AI 犯错”事件。

工具：Codex 桌面应用中的 AI agent（含内部子 agent）；底层模型的具体版本未通过工具核验，记为**未知**。第二阶段的代码、测试、页面与运行证据由 agent 生成并执行；本次文档整理也是 agent 完成，因此在“学生贡献”一栏只记录可核验的用户指令，不代写理解与验收。

编号说明：一阶段使用 AI-000 至 AI-012 及若干续段；第二阶段从 AI-101 起编号（三位数用于区分阶段，不表示条目数量）。

## AI-101 需求变更解读与二阶段规划

- 日期：2026-10-22，Asia/Shanghai（约 17:30–18:05；Word 修改时间 17:29:53）。
- 工具：当前 Codex agent；模型版本未知。
- 用户原始提示词（逐字引用；两条为同一次任务的重复表述，第二条见 AI-104）：

> 「大作业一：需求变更」是第二阶段的任务指导文件，结合该文件和一阶段文件，以及agent、workflow，完成二阶段工作。要求：更新仓库内容，一、二阶段分别打包为单独文件夹，workflow、agent、readme为公共文件，所有文件放在Lab4文件夹下

- 输入资料：`Lab4-2/大作业一：需求变更.docx`（SHA-256 `D9E5BDD8…B008DF1D`）、一阶段 `Lab4-1/docs` 下的需求/决策/系统/数据库/API/逻辑文档、根目录 `AGENTS.md` 与 `WORKFLOW.md`。
- AI 产物：[REQUIREMENTS.md](REQUIREMENTS.md)（八项变更 → R15–R22，附 TC-L01–L09 与 DOC-Q01–Q05 编号）、[DECISIONS.md](DECISIONS.md)（D11–D18）、`results/stage2/gates-t0.md`、`progress.json` 的 T0 条目。
- 是否采纳与修改：采纳“一条变更一条需求、每条需求有验收编号”的结构；修改了两处——①一阶段已用 D01–D10，新增决定不再按草稿的 D07–D14 编号，改为 D11–D18，并在文末加“主题索引”保持与草稿的一一对应；②任务说明提到的抽取文本 `.runtime/audit-stage2/stage2-word-text.txt` 实际不存在，改为直接读 docx 正文（76 段、0 表格），并在文档中说明来源差异。
- 验证：`progress.json` 的 `source.sha256` 与文件实测摘要一致；八项变更的“期望效果”逐条落在需求段落；`pytest --collect-only` 与文档中的用例编号无冲突（本次复核）。门禁记录 [gates-t0.md](../results/stage2/gates-t0.md)。
- AI 错误：初次规划照抄了“D07–D14”的占位编号，与一阶段已采纳的 D07（生命周期）、D08（统计口径）冲突；发现后改为 D11–D18。另有一处表述错误：早期的需求草稿把“八”当成有“期望效果”列表的条目，实际原文只有用户反馈与示例，已在 REQUIREMENTS 中更正。
- 未验证：教师未确认“共享/恢复/统计范围”的语义；规划阶段没有运行任何业务测试，不能把文档完成当作系统完成。
- 学生贡献：提出任务、指定两阶段分目录与三份公共文件（见提示词原文）；对需求解释与决策的采纳仍需本人确认。

## AI-102 数据模型、服务与 API（题目库核心）

- 日期：2026-10-22，Asia/Shanghai（约 18:00–18:12）。
- 工具：当前 Codex agent（含内部实现/测试子任务）；模型版本未知。
- 用户提示词：同 AI-101（同一次任务；没有为子任务另写提示词）。
- AI 产物：[db.py](../survey_app/db.py) 的五个新集合与 10 个新索引；[library.py](../survey_app/library.py)（题目、版本、共享、题库、使用情况、跨问卷统计、问卷集成）；[main.py](../survey_app/main.py) 的 22 条新路由与 `/library` 页面；[models.py](../survey_app/models.py) 的 8 个请求模型；[service.py](../survey_app/service.py) 的保存钩子；[questions.py](../survey_app/questions.py) 的 `question_version` 字段校验。
- 是否采纳与修改：整体采纳“实体/版本/问卷副本”三层结构（D11）与“追加式历史、恢复=新增版本”（D12）；修改过一处接口契约——题库条目 PATCH 最初要求请求体带 `question_id`，导致空体请求 422，改为只从路径取题号、请求体只含可选 `version`（`BankVersionInput`）。
- 验证：`python scripts/check_schema.py --output results/stage2/schema-check.json` 58 项 PASS、10 集合 19 索引；`tests/test_library.py` 14 项在最终全量运行中全部通过（[pytest.json](../results/stage2/pytest.json)）；真实 HTTP 34 步覆盖创建/版本/恢复/共享/导入/发布/统计/题库/fork（[http-e2e.json](../results/stage2/http-e2e.json)）。
- AI 错误：①题库 PATCH 的 422（上面已述，端到端脚本第 31 步发现，原始响应未保留）；②跨问卷统计的 `by_question_version` 用 `str()` 生成键，本地修改的题目会得到 `"None"`，与前端期望的 `"null"` 不一致，且与整数版本混排时 `sorted()` 可能抛错——该缺陷**没有**被测试覆盖，也没有修复，记录在 [LOGIC.md](LOGIC.md) 第 12 节；③使用情况接口没有像统计那样限制被共享者的可见范围，两处口径不一致，已记录在 [DECISIONS.md](DECISIONS.md) D17 与报告的限制一节。
- 未验证：新接口的并发夹具；`current_version` 条件更新未检查 `matched_count` 的异常窗口；被共享者把他人题目加入自己题库的接口路径没有界面入口与用例。
- 学生贡献：尚未由学生本人填写；对上述取舍的理解需本人确认。

## AI-103 题目库页面与二阶段测试

- 日期：2026-10-22，Asia/Shanghai（约 18:08–18:15）。
- 工具：同 AI-102。
- 用户提示词：同 AI-101。
- AI 产物：[library.html](../survey_app/templates/library.html)、[library.js](../survey_app/static/library.js)、[library.css](../survey_app/static/library.css)；[test_library.py](../tests/test_library.py)（14 个测试）、[test_migration.py](../tests/test_migration.py)（1 个测试）。
- 是否采纳与修改：采纳页面结构（左侧新建/题库，右侧列表/详情/统计）；修改过页面的一处交互判断——题库条目“更新版本”按钮只在 `outdated=true` 时出现，`PATCH` 发空请求体，与服务端可选请求体一致。
- 验证：最终全量 260 项通过、exit 0（[pytest.json](../results/stage2/pytest.json)）；失败历史保留在两个存档里（两次 259/1，失败项均为迁移用例）；页面与资源实测 200、`node --check` 通过（[gates-t3.md](../results/stage2/gates-t3.md)）。
- AI 错误：①测试自身三处断言错误（把 `question_version` 写成 `version`；唯一性测试用非 UUID 的 `_id`；发布前用了过期 revision），均已修正，原始输出未保留；②迁移用例在共享测试库里用绝对计数断言，导致两次运行失败，改为相对 `baseline` 后通过；③页面只做了可达性与语法检查，没有真正的浏览器交互验证，早期在日志里把“HTTP 200”当成页面可用的证据，措辞已在 [TEST_REPORT.md](TEST_REPORT.md) 收窄为“页面可达、交互未验证”。
- 未验证：浏览器会话、弹窗与统计面板渲染；新接口并发；关闭状态问卷的导入/修订。
- 学生贡献：尚未由学生本人填写。

## AI-104 仓库重组、两阶段公共文件与二阶段文档

- 日期：2026-10-22，Asia/Shanghai（重组提交 `a3ed940`；二阶段提交 `c34d04d` 18:16:38；文档整理 18:15 之后）。
- 工具：当前 Codex agent（仓库重组与文档整理）；模型版本未知。
- 用户原始提示词（两条，第二条是同一要求的重复强调）：

> 「大作业一：需求变更」是第二阶段的任务指导文件，结合该文件和一阶段文件，以及agent、workflow，完成二阶段工作。要求：更新仓库内容，一、二阶段分别打包为单独文件夹，workflow、agent、readme为公共文件，所有文件放在Lab4文件夹下

> （重复同一条，并再次强调）所有文件放在 Lab4 文件夹下。

- AI 产物：
  - 仓库重组由 **agent 实际执行**：提交 `a3ed940`（“Restructure the repository into shared documents plus one folder per stage”）把 222 个文件从仓库根迁入 `Lab4-1/`，`AGENTS.md`、`WORKFLOW.md`、`README.md` 留在 `Lab4/` 根作为两阶段公共文件；提交 `c34d04d` 加入 `Lab4-2/` 的二阶段代码、测试、脚本、证据与 `progress.json`。
  - 公共文件补充二阶段内容：`WORKFLOW.md` 第 13 节给出 T0–T7 与门禁，`README.md` 增加“两阶段仓库结构”与“第二阶段：可复用题目库”两节及运行/迁移/打包命令，`AGENTS.md` 改为“两阶段共用的行为规范、阶段目录内不放这三份文件”。
  - 本次文档整理新增 `Lab4-2/docs/` 下 11 个文件（需求、决策、数据库、API、逻辑、系统、测试计划、测试报告、实验日志、AI 记录、二阶段报告），并修正了文档之间的编号引用。
- 是否采纳与修改：采纳“公共文件 + 每阶段一个目录”的结构与“每阶段独立 `progress.json`、`environment.yml`、`results/`”的打包方式；修改了两处——①初稿把新决定编为 D07–D14，与一阶段冲突，改为 D11–D18；②初稿在文档里直接链接 `Lab4-1/docs/...`，被二阶段只读检查器的路径规则禁止（链接不得越出阶段目录，公共文件除外），改为在正文用代码格式标注一阶段路径，公共文件用相对链接。
- 验证：`git show --stat a3ed940` 核对 222 个文件的迁移；`git ls-tree HEAD` 确认根目录只剩三份公共文件与 `Lab4-1`/`Lab4-2`；`git status` 确认二阶段已被 `c34d04d` 收录；文档写完后运行 `python scripts/check_workflow.py`，文档、链接与需求/用例追踪检查通过，剩余 3 项 ERROR 全部在文档范围之外——`gates-t6.md` 缺 G6.2、`results/stage2/manifest.json` 缺失、`progress.json` 的 `current_stage` 应为 `complete`（写报告前是 ERROR=12，另有 9 项由缺少 `REPORT_STAGE2.md` 与跨文档链接造成）。
- AI 错误：①编号冲突（同上）；②初稿把“全量 261 项、二阶段 16 项”的转述照抄进测试章节，与 `pytest.json` 的 260 项（245 + 15）不符，已按证据改为 260/15，并在 [TEST_REPORT.md](TEST_REPORT.md) 说明计数口径；③初稿在数据库文档里写“仓库中没有 migration.json”，该文件随后由作者生成，已按实际内容改写；④初稿把“任务说明提到的 Word 抽取文件”当成存在的输入，实际不存在，已改为直接读 docx 并说明。
- 未验证：`results/stage2/manifest.json`（T7 要求的交付包清单）在文档整理时不存在，`python scripts/check_workflow.py` 会因此报错，本次未生成（应由 `python scripts/package_stage2.py` 生成，属交付步骤）；根 `README.md` 前半段仍按一阶段单目录描述 `docs/`、`progress.json` 等路径，重组后这些文件在 `Lab4-1/` 下，本次未修改该公共文件，链接是否失效未逐条验证；二阶段文档没有经过教师或学生本人审阅。
- 学生贡献：提出“两阶段分目录、三份公共文件、全部放在 Lab4 下”的仓库要求，并要求按 agent/workflow 执行；仓库重组的执行者是 agent，不记为学生手工操作；对文档结论的确认仍需学生本人完成。

## 待学生本人填写

以下内容 agent 不能代填，保持空白：

- 对 D11–D18 各条取舍是否认同、是否要改。
- 是否亲自复核过 `library.py` 的版本与统计逻辑。
- 对“共享即授权”“恢复即新增版本”“统计范围按所有者/被共享者区分”三条是否有不同解释。
- 本阶段实际投入的时间与遇到的问题（如与 AI 记录不同）。

## 记录模板（沿用一阶段）

```text
AI记录 ID／时间时区／实际使用者：
工具／可核验模型版本（不知道则写未知）：
任务与需求、阶段：
原始提示词或脱敏原文（较长时链接本项目内文本）：
生成的代码/文档位置与版本差异：
是否采纳／改了哪些内容／为什么：
验证方式与实际结果（含失败）：
AI 错误与修正：
未验证项：
学生贡献（仅本人可确认）：
```

## AI-105 浏览器核验尝试与其失败

- 日期：2026-10-22，Asia/Shanghai。触发：父 agent 为补齐 EXP-103 的未验证项而尝试浏览器验证。
- agent 产物：无功能改动；新增 results/stage2/browser/library-anonymous.png（Chrome 无头截图）与 docs/EXPERIMENT_LOG.md 的 EXP-107。
- 是否采纳与修改：不采纳 agent-browser 的执行结果，因为其输出为命令用法文本、流程未落库；改以截图作为“页面可渲染、脚本已执行”的有限证据。
- 实际发现的 AI 错误：a) agent-browser 在 Windows 管道下 fill/click 失效且 screenshot/errors 挂起，agent 连续两次等到超时；b) agent 一开始把“未登录时显示登录面板”当作脚本成功的间接证据是对的，但随后在数据库里看到的两条同标题题目重复记录属同一批 HTTP 运行产物，未误记为浏览器产物（已按 created_at 核对）。
- 未验证内容及影响：登录后交互全部未验证；题目库页面仍只有 HTTP 与自动化测试证据。
- 学生贡献：无（本次为验证尝试，未产生交付内容）。

## AI-106 第二轮修复：题库 pin、报告载体、README、统一检查

- 日期：2026-10-22，Asia/Shanghai。触发：用户要求“按顺序完成修复”，随后指出我把“上下文容量”当成事实陈述。
- agent 产物：`library.py` 的 `import_into_survey` 支持 `bank_id`；`models.py` 与 `main.py` 同步；
  `tests/test_library.py` 新增 `test_import_from_bank_uses_the_pinned_version`；`Lab4-2/scripts/build_report_pdf.py`
  与 `build_report_docx.py`（自一阶段复制并改路径/封面）；`Lab4/README.md` 开头改为两阶段；新增
  `Lab4/scripts/check_all.ps1`。
- 是否采纳与修改：全部采纳用户“按顺序修复”的要求。文档补充以“补充”小节追加，未改写既有结论。
- 实际发现的 AI 错误：a) 上一轮把“上下文容量用完”当成客观事实讲，而我没有真实占用读数，这是不该说的判断，
  已在回复中更正；b) 自建的报告校验脚本里曾有一条恒真断言（`... or True`），已改为解压 `word/footer*.xml`
  检查 PAGE 域，避免用假通过掩盖真实状态；c) 追加测试时两次因缩进/位置写错导致收集失败，已修正并保留过程记录。
- 未验证内容及影响：题目库页面的登录后交互仍无浏览器证据；`check_all.ps1` 只在本机 conda 环境验证，
  未在其他 shell 或 CI 环境验证。
- 学生贡献：本轮为按用户指令执行的修复，未涉及学生本人贡献的表述。

## AI-107 浏览器验证、归档与分享链接

- 日期：2026-10-22，Asia/Shanghai。触发：用户要求“剩下 3 项按照最佳方式解决，不要影响一阶段，不要影响效果”。
- agent 产物：
  - `scripts/browser_e2e.mjs`（CDP 驱动真实 Chrome 的验证脚本，无第三方依赖）与 `results/stage2/browser/` 证据；
  - `question_share_links` 集合、归档与分享链接的 6 个路由、5 个服务方法、2 个测试；
  - `Lab4/scripts/check_private_data.py`、`Lab4/.gitignore`、`Lab4/scripts/check_all.ps1` 的隐私扫描步骤。
- 是否采纳与修改：采纳用户三项要求。第三项（重写历史）按“最佳方式”改为**不重写 + 当前树扫描**，理由写入 DECISIONS D21；
  该选择在上一轮已向用户说明风险，本轮据此落地。
- 实际发现的 AI 错误：a) 自建隐私扫描首版误报 5 处（忽略文件里的模式串、UUID 中的 11 位数字片段），已收紧规则；
  b) `check_all.ps1` 每次被编辑都会丢 BOM 导致 PowerShell 5.1 解析失败，最终改为纯 ASCII 脚本；
  c) 分享链接预览接口初版写了一个无意义的 `shared_with_me` 字段（对 `grantee_id: None` 查询），已删除。
- 未验证内容及影响：浏览器验证只覆盖主流程，恢复/共享/题库/加入问卷的点击未纳入；分享链接没有过期时间与访问次数限制；
  归档没有级联清理题库条目（题库仍可显示已归档题目）。
- 学生贡献：无新增（本轮为按用户指令执行的修复）；三份公共文件仍由学生确认口径。

## AI-108 四项未覆盖项的处理

- 日期：2026-10-22，Asia/Shanghai。触发：用户对照需求变更文件追问“四项为什么不能解决”。
- agent 产物：`browser_e2e.mjs` 扩展到 12 步 7 图；分享链接 `expires_at/max_uses/uses` 与 410 语义；题库 `archived` 标记与拒绝入库；统计 `limit` 参数；对应 4 个测试与文档更新。
- 是否采纳与修改：全部采纳。核对后确认这四项都**不在需求变更的八项之内**，属于工程加固；需求八项本身已由自动化测试与 HTTP 全链路覆盖。
- 实际发现的 AI 错误：a) 上一轮把“未覆盖项”说成“不能解决”，实际是当时按需求边界主动收手，表述不准确；b) 分享链接初版没有时效字段，属于设计时漏想，本轮补齐；c) 归档初版没有考虑题库条目，导致题库会显示已归档题目而不自知。
- 未验证内容及影响：分享链接的界面入口尚未提供（只有 API 与测试）；统计上限仍是无分页的截断而非游标分页；浏览器未在移动端或非 Chrome 浏览器验证。
- 学生贡献：无新增（按用户指令执行的加固）。
