# 实验与工作日志

本日志记录实际动作。计划和预期不等于已执行；每次运行的原始结果放 `results/`。当前没有应用代码版本、数据库拓扑或业务测试结果，不补造这些信息。

## EXP-000 S0 规划初始化

- 日期：2026-10-15，Asia/Shanghai；本条在首轮资料阅读与主文档初建后补录，不伪装成事前登记。首次建立流程属于 S0 bootstrap，后续任务必须先登记。
- 触发：用户要求阅读一阶段 Word，设计 workflow，参考指定 AGENTS 设计实验行为规范，并用 README 说明项目，后续严格执行。
- 目标与范围：R01–R15 的规划与追踪；只创建本大作业治理文档和只读检查器，不实施问卷应用，不修改 Word、参考规范及 Lab 内容。
- 已执行：读取参考规范、完整提取 Word 正文/列表/评分表并计算 SHA-256；枚举现有目录文件名；读取相关技能；并行审阅需求与规范迁移；查阅 MongoDB 官方原子性、事务和部分索引说明。
- 文档工具：Codex bundled Python，OOXML 使用 zipfile/lxml 读取；未安装任何依赖。读取源文件未产生新的 Word。此工具环境只用于本次文档工作，不是已验证的应用环境。
- 来源检查实际值：Word SHA-256 为 `88AF590B01A4265C31B5DA1F2D44F0BB833F4D8FA8C0852478963420B9D685EC`；参考规范摘要见 [REQUIREMENTS.md](REQUIREMENTS.md)。源文件含 1 张评分表，无嵌入媒体文件及修订插删文字；页码和版式未验证。bundled 依赖无 LibreOffice，未借用用户桌面软件渲染。
- 命令记录：PowerShell `Get-Content`、`rg --files`、`Get-FileHash -Algorithm SHA256`；bundled Python 标准 ZIP/XML 读取及 lxml 的列表/表格提取。输出已在本次会话核对，原始完整终端输出没有另存；后续结构检查输出将保存到 `results/planning/`，不声称前序输出均已落盘。
- 设计判断：将登录+匿名、重复填写、跳转确定性、路径、时间、统计口径等显式列为 proposed 决策；当前不做环境安装或业务实验。
- 下一步验证计划（先登记后执行）：审阅全部新文件；运行只读流程检查器并保存输出；在临时副本注入跳阶段/缺证据/坏链接/源文件变化等错误，验证检查器实际拦截，保留真实结果；复查 Word 与参考规范摘要未变。
- 当前业务结果：全部 TC 为 NOT_RUN；S1–S8 未开始。结构检查及最终审查的实际结论见 [规划审查](../results/planning/review.md)。

收尾实际记录：

- 首轮与内容修订后流程检查均退出 0，ERROR=0、WARN=0，输出已保存到 `results/planning/`。
- 临时副本验证共 12 场景全部符合预期：2 个合法状态通过、10 个错误场景被拒绝；预期/实际退出码和完整输出保存在 `checker-validation.json`。先验证临时目录位于指定系统临时目录且具有本任务前缀，再由同一 Python 流程清理；未删除或覆盖工作区内容。
- Word、父目录参考 AGENTS 的摘要与首次读取一致，实际对比保存在 `source-integrity.json`。
- 内容复审修正了门禁对尚未实现 API 的提前依赖和二阶段用例混入第一阶段的问题；详情在 AI-000。修订后结构检查仍通过，没有弱化检查器判断逻辑。
- S0 门禁审查已完成；状态收尾为 S0 passed、当前待执行 S1，S1–S8 pending。最终再运行只读检查并保存 `structure-check-final.txt`；应用与业务用例仍未运行。

## EXP-001 第一阶段范围收敛

- 日期：2026-10-15，Asia/Shanghai；实际修改前登记。
- 用户澄清原文：“目前只要求完成1阶段任务”。本次据此修订规划范围，不自动启动问卷应用实现。
- 阶段：S0 规划维护；S1–S7 仍未开始。先前 S0–S8 的记录保留为历史，新版以第一阶段 S0–S7 为准。
- 拟改动：AGENTS、WORKFLOW、README、需求/决策/测试计划、状态和只读检查器；追加本条及 AI-001、范围复核证据。删除当前计划中的第二阶段执行步骤、用例和验收交付，仅保留来源背景及第一阶段成果留存。
- 检查器修改理由：原检查器强制包含第二阶段，用户当前范围只含第一阶段，须将固定阶段由 S0–S8 调整为 S0–S7、当前需求由 R01–R15 调整为 R01–R14；第一阶段原有门禁、证据、权限/并发/统计测试不减少，不为绕过失败而放宽判断。
- 验证计划：核对 26 组第一阶段用例仍完整；正常检查退出 0；临时副本附加 S8 必须被拒绝；顺序/证据错误仍被拒绝；模拟完成 S7 后 current_stage=complete 应可通过结构检查。保存本次输出，保留以前的真实结果及其旧范围说明。
- 经验检查：no-delta。本次澄清属于本项目范围事实，记录在项目文档，不写入全局技能或额外自改规则。
- 验证中实际失败：首轮临时夹具只复制 Markdown，遗漏历史审查所链接的 txt/json 证据，因此两个应通过场景被缺链接检查拒绝。原输出保存在 `scope-checker-validation-incomplete-fixture.json`；修正夹具为复制本项目规划证据文件，不改检查器判断逻辑，随后复测。
- 实际结果：第一阶段 26 组用例保留，修正夹具后的 5 个场景全部符合预期；正常状态及一期完成可通过，额外二期、跳步和缺证据被拒绝。S0 复核通过，S1–S7 pending，业务未运行。收尾结构输出保存到 `scope-check-final.txt`。

## EXP-002 打包为 Lab4

- 日期：2026-10-15，Asia/Shanghai；复制及修改前登记。
- 用户要求原文：“打包为文件夹Lab4”。本次仅整理当前第一阶段规划交付，不执行应用开发或业务实验。
- 计划：新建 Lab4，复制本项目主文档、状态、源 Word、docs/scripts/results；原目录材料保留，不复制 Lab1–Lab3。为独立搬运附带用户最初参考规范的副本，放在 references 中且不作为活动 AGENTS 执行；修正包内参考路径与运行目录说明。
- 验证：在 Lab4 内运行同一流程检查器，核对源 Word 和参考规范摘要；生成包内相对路径与 SHA-256 清单并逐文件复核。不安装依赖、不压缩为用户未要求的格式。
- 实际结果见 Lab4 内的打包复核记录；第一阶段业务实现状态保持未开始。

## EXP-004 对照 Word 检查第一阶段完成情况

- 日期：2026-10-15，Asia/Shanghai；核查执行前登记。
- 用户要求原文：“对照文件，检查完成情况”，依据 Lab4 根目录《大作业一第一阶段.docx》。
- 范围：完整读取作业需求，枚举 Lab4（含嵌套旧包）的文件，核对实际应用代码、Schema、配置、设计文档、测试执行证据、报告和 AI 日志；区分规划完成、未实现、未执行与不可确认。只做核查，不编写应用或修改完成状态。
- 验证计划：检查脚本与实际文件种类、需求和测试计划措辞、各阶段状态；运行只读流程检查器并保存输出。该检查器结果不替代课程功能验收。发现目录嵌套等问题只记录，不删除或整理。
- 证据位置：本次只读核查事实及命令输出保存在 `results/audit/`。实际结论完成后追加。

实际核查结果：

- 已重新读取 Word 全文及评分表，仅按第一阶段要求核对。源 Word SHA-256 与原记录一致；本次检查前有 51 个文件，含外层 22 个及嵌套旧包 29 个，不把重复包计为新增成果。
- 两个 Python 文件均为 `check_workflow.py` 的副本；未发现问卷后端、前端、可执行 MongoDB Schema 或应用环境/配置。账号、问卷、校验/跳转、提交与统计均只有计划，未发现业务实现。
- 26 组业务用例明确为 NOT_RUN，无实际输入输出、业务执行结果或真实 MongoDB 验收证据。现有检查器验证记录只证明流程工具行为。
- 系统说明为规划层面；完整数据库/API/关键逻辑实现文档、测试报告和第一阶段完成报告尚缺。AI 日志已有规划/范围修订记录，但不是完整应用开发过程及最终报告说明。
- `progress.json` 仅 S0 passed，S1–S7 pending；现有流程检查实际退出 0，ERROR=0、WARN=0，未把结构检查通过当成课程作业完成。
- 结论：第一阶段尚未完成，当前是准备性规划成果。核查事实见 `results/audit/completion-evidence.json`，本次命令输出见 `results/audit/workflow-check.txt`。未启动应用、连接数据库、执行业务测试或更改阶段状态，未估算课程得分/完成百分比。

## EXP-005 S1 实施授权与环境基线

- 日期：2026-10-15，Asia/Shanghai；实际工作前登记。
- 用户原始要求：“根据这几份文件，完成实验”。本次明确授权完成第一阶段实现、测试与交付，覆盖 S1–S7，仍不执行第二阶段。
- 当前前置：S0 已通过。先修正目录入口/参考路径与旧“仅规划”范围说明，再审阅并采纳业务语义，核实 conda 和 MongoDB，建立隔离的应用/测试环境及版本记录。
- 数据隔离：使用本项目独立 MongoDB 实例/端口和新数据库，不访问、清理或迁移 Lab1–Lab3 数据；运行时数据和环境不进入提交包。
- 计划产物：已采纳决策、environment.yml、.env.example、docs/ENVIRONMENT.md、真实环境连通证据及 S1 门禁记录。S1 未通过前不开始应用实现。
- 验证：conda 环境与依赖可导入、MongoDB 版本/副本集拓扑及隔离数据库连通；记录实际命令和输出，不把已有规划检查当环境验证。

## EXP-006 S2 数据库与接口契约

- 日期：2026-10-15，Asia/Shanghai；S1 真实环境与语义门禁已通过，证据为 results/S1。
- S1 实测摘要：conda 新环境安装成功、MongoDB 6.0.29 独立 27084 端口副本集 primary、事务探针 PASS；流程检查 0 ERROR/0 WARN，本项目独立 Git 已建立（87bd45a）。
- 本步目标：冻结集合/索引/校验、API、发布状态、跳转及提交并发协议，创建可执行 Schema 初始化并在新测试库验证非法文档和唯一约束。不得提前将后续业务功能标记完成。
- 拟改动：survey_app/config.py、db.py、scripts/init_db.py、Schema 探针及 docs/DATABASE.md、API.md、LOGIC.md；根目录入口与参考来源按已发现事实修正，不改变门禁。
- 验证：隔离真实 MongoDB 新库的 Schema/索引测试；字段/图/权限/匿名/统计契约审阅；保存 S2 证据后才能进入 S3。

## EXP-007 S3 账号与问卷管理

- 日期：2026-10-15，Asia/Shanghai；前置 S2 已通过（43/43 Schema 检查 PASS，设计审阅缺口已修正，提交 d7349be）。
- 本步范围：安全注册/登录/会话、本人管理、草稿/题型配置、同 revision 发布冻结、截止/关闭、认证填写入口及简单管理页面；只实现 S3 已解锁部分。
- 拟改动：应用模型/配置校验/认证/服务/API模块，templates/static 页面，pytest 真实 MongoDB 管理测试及证据工具。内部 agent 分别负责 UI 与独立管理测试，主 agent 负责业务集成。
- 验证：TC-A01、A02管理/填写入口、A03已实现管理接口、Q01–Q03，用真实 UUID 测试库与数据库读回；浏览器填写/最终提交和统计留到后续步骤，未实现路由404不可当权限成功。
- 日志管理修正：results 下原始 .log 是证据，应纳入版本记录；运行时日志由 .runtime 整体忽略，不再全局忽略 *.log。

## 后续每次工作先复制本模板

```text
实验 ID／日期时间与时区／执行者：
阶段与前置门禁证据：
需求 ID／决策 ID／用例及子用例 ID：
目标与拟改动文件（事前）：
代码版本或本次文件摘要：
操作系统／依赖版本／MongoDB版本与拓扑（脱敏）：
测试库精确名称与隔离、清理范围：
输入、随机种子及配置：
运行命令（脱敏）与预期（事前）：
实际动作、输出、退出码（事后）：
结论 PASS/FAIL/NOT_RUN/BLOCKED（事后）：
实测证据路径／设计判断／未验证范围：
失败原因、修复及复测（保留原记录）：
WARN逐条说明／阶段状态更新：
关联AI使用记录：
```

S3 首次实测：results/S3/admin-tests.json，23/23 PASS；Starlette 对 httpx TestClient 的弃用提示保留，当前兼容正常，后续另有真实 HTTP/浏览器复核。只读审阅发现 malformed Origin 导致500、先全读再限长、日期可被数字时间戳强制转换，现登记修复与独立新增回归；原始通过证据保留，修复后重新运行。S3 页面已完成静态语法检查，尚未以浏览器验收。

S3 收尾：35/35 回归 PASS，精确测试库清理 PASS；结果及门禁见 results/S3。原23项结果保留。

## EXP-008 S4 校验与跳转

2026-10-15 Asia/Shanghai。前置S3门禁通过；事前登记。范围R04–R08、TC-V01–V05、J01–J05a：统一运行期校验、路径求值、/next接口和逐题页面。验证边界、优先级、空答/必答、路径伪造、回改清理，并回归管理接口。主agent负责集成，子agent分别实现求值器、独立测试及页面。S5提交仍未解锁。
D06补充解释：必答题必须存在非空合法答案；拒绝必答多选exact/max=0、文本max=0、整数上下界间无整数。可选题允许空答，结构冲突仍拒绝。新增规则在测试前登记，不倒改预期。
S4浏览器首次进入失败：测试服务器在questions模块更新前启动，未开启热重载，/next导入旧进程中不存在的evaluate_path导致500。已核对自己的PID/启动参数后重启此测试进程，保留原运行日志；继续重新加载页面验证。

S4收尾：190/190 PASS（155项S4+35项管理回归），浏览器四题校验和回改跳转通过；证据results/S4，未提交答卷。

## EXP-009 S5 提交、并发与统计

2026-10-15 Asia/Shanghai，前置S4真实门禁通过；事前登记R09–R11及TC-R01–R05/S01–S03、A02/A03/J05b提交集成。计划新增事务提交、结果白名单与统计/页面；服务器规范答案后gate条件写入与答卷插入同一事务，关闭同文档竞争。真实新UUID测试库检验10人并发、同账户/同请求/允许重复、先关闭/先受理、截止前/等于/之后；以MongoDB读回对账，手算三答卷统计并验证匿名和所有权。禁止mock替代事务证明。原失败证据保留，S5通过后方进入S6。
S5文档命令核对发现check_schema旧脚本不解析参数；尝试--help意外执行一次真实43项（全部PASS，原证据由脚本自动归档）。现登记仅增加argparse输出路径/帮助支持，不改变测试断言；新运行移存results/S5/schema-unplanned-rerun.json，恢复S2固定证据为原归档，修复后核对--help无数据库操作及指定输出重跑。

S5审阅诊断：每个数字先除以n再fsum仍会在3/7个最大有限double时溢出；纯Python已确认，见mean-diagnostic.json。统计模块保留通常精度路径，溢出时按最大绝对值缩放并限制归一化均值后还原；新增真实API大数回归，未预先声称通过。该修复不改变D08统计定义。

S5收尾：提交专项46/46、全量245/245及Schema CLI43/43 PASS；浏览器真实回执、匿名明细及均值8与MongoDB读回一致，控制台无error。见results/S5/gates.md。Starlette弃用提示已解释。S5 gate均通过后进入S6。

## EXP-010 S6 集成与干净复现

2026-10-15 Asia/Shanghai，事前登记。前置S5真实门禁通过。计划按README在新conda环境和干净源码副本、独立MongoDB数据目录/端口27085及UUID库完成配置、初始化、启动、真实HTTP和全量回归；重启应用验证持久化。根agent完成浏览器E01关闭环节及页面复核，汇总26组实际结果。TC-S02按已采纳一次发布version1范围检验当前版本筛选和跨问卷同题号隔离，不虚构可公开生成第二发布版本；原计划措辞保留并作明确修订。不改任何原验收断言或既有失败记录。

### EXP-010-REPRO 干净环境具体验证计划（事前）

日期：2026-10-15，Asia/Shanghai。执行者：Codex复现子agent；需求TC-E02/R01/R12/R13。从提交e7255c3332b3492691eff27a0a5ce7e395127422通过git archive导出到.runtime/reproduction/project；新建conda环境lab4-survey-repro-be6b0d，严格从归档environment.yml安装，不使用pip。副本独立MongoDB端口27085、副本集lab4repro、应用端口8005，均只绑定127.0.0.1。先验证归档摘要与副本流程，再配置随机秘密、不输出.env；完成副本Mongo初始化、Schema43项、全量245项测试、真实HTTP四类问卷发布/填写/提交/统计。仅在核验PID命令行指向副本后停止自己的应用，重新启动读取旧会话/答卷和统计以验证持久化。新UUID测试库仅按测试夹具精确清理；不触碰27084/8004或旧Lab。实际命令、版本、退出码、源码摘要、原始失败/警告及结果保存到副本并复制脱敏证据至主results/acceptance；不改根进度/README/报告，不提交Git。
S6复现安装首轮包装器故障（实际失败保留）：Windows PowerShell将conda原生stderr输出视为RemoteException，尚无新环境python。现改为隐藏Start-Process单独收集stdout/stderr、WaitForExit按真实退出码判断；仍从原environment.yml创建同一新环境，不更改SSL，不使用pip。原始conda-install-attempt1.txt及conda-result-attempt1.json保留。
S6复现安装第二轮实际失败：conda报告EnvironmentFileNotFound，但PowerShell核验归档environment.yml存在。改为将工作目录设为干净项目，传相对environment.yml，避免绝对Unicode路径经原生参数转义；同时以Start-Process -Wait -PassThru收集真实退出码。第二轮日志已另存，不改依赖定义。
S6复现包装器根因已定位：PowerShell7生成UTF-8无BOM计划文件，Windows PowerShell5默认按ANSI读取，中文项目路径因此损坏，第三轮报DirectoryNotFoundException。现显式按UTF-8读取计划，并从PSScriptRoot构建项目路径；前三轮真实失败日志保留。依赖内容与校验规则未变。

S6文档审阅修正：README的init_mongo命令增加--output results/local-environment.json，避免普通复现覆盖历史S1环境证据；参数原已支持，复现也采用显式输出文件。统计区域加载时可能改变滚动位置、手工畸形百分号分享URL缺少友好提示作为非阻塞已知限制记录于final-code-review.md；正常生成的分享链接与完整链路均已实际通过，不冒称全部浏览器/异常输入均验证。
S6 TC-E02收尾实测：新conda环境lab4-survey-repro-be6b0d安装退出0；归档105个文件运行前后摘要不变；新环境模块来源已核对。独立27085/lab4repro上Schema43/43、全量245/245、真实HTTP23步及不同PID应用重启后会话/答卷/统计/幂等回执持久化全部PASS。原清理包装器exit1与GBK解码stderr保留；仅UTF-8输出修正后补救核验PID17332命令和精确dbPath，PyMongo优雅关闭并确认PID退出。最终事实results/acceptance/reproduction-final.json，原失败reproduction.json，补救reproduction-cleanup-repair.json，说明reproduction.md。未重跑或覆盖245测试原证据；复现数据保留，主27084/8004未动。证据秘密/连接串扫描0匹配。

S6收尾：26/26组PASS；新conda、干净归档副本、独立MongoDB与HTTP进程，245/245、Schema43/43及23HTTP流程步骤、重启持久化均通过。清理包装器原exit1保留；单独补救后自有进程退出，最终reproduction-final.json PASS。仅同主机隔离复现，不称新OS。见results/acceptance/gates.md及TEST_REPORT。

## EXP-011 S7 第一阶段交付与基线

2026-10-15 Asia/Shanghai，前置S6已通过；事前登记。范围R01/R12/R13/R14、DOC01/DOC02。计划新增SYSTEM、REPORT_STAGE1、BASELINE_STAGE1和合成统计夹具，补备份恢复方法并在新UUID合成测试库演示；保留受验业务代码e7255c3及文件摘要。根agent核对README/需求状态、四类交付物、文件清单及打包排除.env/.runtime/.git/缓存/旧嵌套results/Lab4；实际解压校验哈希和秘密不入包。S7门禁全部满足后才标complete。

### EXP-011 续作：2026-10-16 Asia/Shanghai

用户提示“继续”。中断前报告与SYSTEM已实际落盘，但恢复演示和交付包未完成；恢复时不把旧计划当成功。完整重读规范/状态/决策与测试计划，当前S7 active。首个流程检查因README已引用但BASELINE尚未落盘报1ERROR（results/S7/workflow-resume.txt）；先补真实基线说明并消除该结构错误，再运行恢复演示。根继续核验四类材料、21业务基线摘要、ZIP清单/秘密排除和真实解压结构检查，保留所有失败历史；除新增交付工具外业务代码不变。

S7收尾实测：2026-10-16，backup-restore.json首轮PASS exit0；静止合成源snapshot五集合BSON恢复，文档/Schema/index相等，3份2人均值15、三原回执重放无写入，双精确UUID库清理PASS，sessions空不覆盖。报告与Word四类/九项审阅通过。归档预检156文件真实解压、清单SHA/字节全部匹配、当前文档链接0错、解压后workflow0，业务21文件未变；见unpacked-preflight.json。S7全部门禁据实通过并将current_stage设为complete；最后状态元数据变更后用同一工具重建和复核最终ZIP，最终摘要随包单独保存。原结构1ERROR与其修复0ERROR输出均保留，无未解释WARN。

## EXP-012 本地站点连接恢复（2026-10-16 Asia/Shanghai，事前）

用户报告http://127.0.0.1:8004/ ERR_CONNECTION_REFUSED。已完整重读规范/工作流/状态与运行文档，结构检查0ERROR/0WARN；S0-S7已完成，不新增阶段。只读核查MongoDB27084运行且dbPath确属本项目、lab4rs可写；8004无应用监听。原隐藏后台启动命令被工具策略拒绝执行，未产生进程或计划文件。现改用受管理终端启动现有conda环境的uvicorn，便于查看日志/停止；验证/health、首页及当前浏览器。禁止清库/改密钥，不更改受验业务代码；运行证据在.runtime，日志改变后刷新交付摘要。

EXP-012实际结果：现有conda Python在受管理终端session80096启动uvicorn，PID20744；127.0.0.1:8004监听，/health真实HTTP200，status=ok/database=connected。没有改业务代码、清库、改密钥或重新安装依赖。浏览器URL安全策略拒绝获取当前错误页（协议检查未通过），未尝试替代浏览器/DOM旁路；因此本次不宣称页面视觉复测通过，用户需手动刷新。README补充进程需持续运行及连接拒绝/健康检查说明。日志和说明更新后重新打包、核验文件摘要；既有业务验收仍适用。self-improving判断no-delta：这是本项目进程运行状态及启动说明问题，不修改全局技能/规则。

## EXP-013 填写页面前端改版（2026-10-16 Asia/Shanghai，事前）

用户当前明确指示优先于本项目约定：要求读取 Lab4 并调用前端设计技能优化问卷页面。已向用户确认范围为“填写页面为主、整体视觉系统同步”，视觉方向由 agent 按问卷题材确定。本项是 S7 结束后用户新增的界面改进，不新增阶段、不新增需求编号、不改动受验业务语义（服务端、Schema、API、校验、跳转、提交、统计逻辑全部不变），只改表现层。

范围与文件：R03/R09/R11 的展示层。改动文件限于 `survey_app/static/app.css` 与 `survey_app/static/app.js`；`survey_app/templates/index.html` 与全部 Python 代码不改。保留既有 id 与 data-testid 契约（fill-view、fill-title、fill-save-note、fill-question、fill-answer-form、fill-answer、fill-option-*、fill-clear、fill-next、fill-back、fill-hint、fill-error、fill-question-heading、fill-edit-*、fill-review*、fill-submit*、fill-receipt*），既有定位方式仍有效。

设计判断（先方案后实现）：配色为纸与墨，页面底 #F4F5F2、卡面 #FFFFFF、正文 #1B2422、次要文字 #56615E、发丝线 #E1E5E1、主色松墨绿 #1D6B5E、选中底 #E8F0ED，朱砂红 #B23A2E 只用于“必答”与回执编号；标题/题干用宋体系（Songti SC／SimSun 等），界面与正文用 Segoe UI + 微软雅黑栈，数字走 Latin 字体与 tabular-nums，中文不使用负字距。布局为单列纸面（≤760px），答题区在桌面分两栏：左侧 132px 答题路径轨（真实路径的序号、可点回改、当前题标记、末端按回答继续），右侧为当前题；移动端路径轨折为横向编号条。原则：一屏一题、结构即信息（序号只标记真实路径）、纸与线（发丝线分隔而非圆角卡片堆叠与阴影）、一处用力（朱砂红只出现两处）、中文排版（题干行高 1.7、行宽 ≤34 汉字）。

课程合规说明：Word 只写“界面可简单”，未指定风格；本次不增加任何功能、不改变填写与提交流程，故不改变 R01–R14 的验收口径，也不需要重跑业务门禁。但待交付包 `dist/Lab4-stage1.zip` 及其清单摘要会与改后的静态文件不一致；本次先完成改版与验证并如实记录，是否重新打包由用户决定，不静默改写 S7 已通过证据。

验证计划：1) `scripts/check_workflow.py` 结构检查；2) 全量 pytest（自动新建并仅清理 UUID 测试库）；3) 新 UUID 库 + 独立端口 8005 的真实浏览器验证填写、回改、核对、提交回执，截图存 `results/ui-refresh/`；4) 选择器覆盖比对，确认改版未丢失既有 CSS 选择器；5) 只停止本次新建的进程并按精确库名清理。禁止清空既有数据库、禁止改密钥、禁止用静态预览冒充真实浏览器验证。

EXP-013实际结果：只改了 `survey_app/static/app.css`、`survey_app/static/app.js` 与本文档，`index.html` 和 Python 代码未动（`git status` 仅此三项）。新 app.css 摘要 049F606F8A355654830BFF4F37D28EC4248CB87B02688A15FCFCCE7BBAAAAE17，新 app.js 摘要 85FF0B197D9F662D8E5951FF07099DF81B21D1E5419BA3C1DEB645F2EE9F6062。结构检查 ERROR=0/WARN=0（results/ui-refresh/workflow-check.txt）；全量回归 `python -m pytest tests --evidence results/local-run.json -q` 得 245 passed、1 warning（既有 Starlette/httpx 弃用提示）、退出码 0。选择器覆盖比对（本地工具 .runtime/ui-refresh/check_selectors.py）显示旧 250 项、新 271 项，丢失 10 项：3 项 .fill-history* 与 1 项 .fill-question>.muted 属有意替换为 .fill-path*／.fill-hint，6 项 .preview-* 经全仓库检索确认无 JS/HTML 产生属遗留死规则；据此还发现并补回统计页仍在用的 .question-type 和 .fill-review 基础间距。真实浏览器验证在隔离实例进行：同一 conda 环境另起 uvicorn 监听 127.0.0.1:8005，MONGODB_DATABASE 覆盖为 lab4_ui_check_4f2a91c7b3d5，seed.py 经真实 API 建 1 份已发布问卷（5 题覆盖四类题型，2 条真实跳转规则）及两个合成账号；改版前后各截 1440×900（移动 390×844）同名截图，见 [改版证据](../results/ui-refresh/review.md)。实测通过：正向填写四类题、按 q1=手机 跳至 q4 且路径轨编号由 01 断档到 04、点路径轨 q2 回改后路径截断为 01+02 且原选项保留 2 项、核对页编号为问卷题号、提交回执显示新回执编号、Tab 后选项行 outline 为 2px rgb(29,107,94)、console 与页面错误均为空；夹具库记录 4 份答卷（全程版本 1），业务库 lab4_survey 未写入。未验证项：仅本机 Chrome 与 390×844 一档移动宽度，prefers-reduced-motion 只核对规则存在，未重跑或改写 S0–S7 任何原验收证据。偏差提示：dist/Lab4-stage1.zip 内静态文件摘要已与改后工作树不一致，本次未重新打包，是否重打由用户决定。验证结束后停止本次 8005 进程并按精确库名清理该隔离库。

### EXP-013 续：交付包重建与 S7 产物快照（2026-10-16 Asia/Shanghai）

用户确认“按最佳解决方法办”。处理原则是不改写 S7 已通过的原始证据，只为改后状态新增可追溯记录。先逐字节快照 S7 时点产物：`results/S7/manifest.json`（27732 字节，a2b7fbf242e894ccedc68482f98f3b67045afffd6e54a682f646da3984290950）与 `results/S7/package-check.json`（634 字节，ab66f80278fe405c27be88dd4a28329de1e4e5f6ce72a7086f9fda21d81dcd6d）复制为 `results/S7/archive/manifest-s7-baseline.json` 与 `package-check-s7-baseline.json`；S7 时点交付包 `dist/Lab4-stage1.zip`（636693 字节，1dd92dcb5dac605183db384c7b91c529fc3acd219727ced0b43771ca8989ba5f）复制为 `dist/Lab4-stage1-s7-baseline.zip` 并生成配套 `.sha256`；快照与复制的摘要一致性、来源和用途记录在 results/ui-refresh/repackaging.json，说明见 [S7 快照说明](../results/S7/archive/README.md)。

基线范围实测：以 results/S7/code-baseline.json 的 21 个业务文件逐项重算工作树摘要与 LF 归一化摘要，19 项与 S7 基线一致、2 项改变、0 项缺失；改变的只有 survey_app/static/app.css 与 survey_app/static/app.js，即 EXP-013 的界面改版，服务端、Schema、校验、跳转、提交、统计与全部测试文件未变。逐项结果见 [基线复核](../results/ui-refresh/code-baseline-check.json)。据此判定 S7 门禁 G7.1–G7.3 的实质结论不受影响：改版后全量 245 项测试再次通过，并新增真实浏览器验证；本次不重跑业务门禁、不改任何原验收断言、不删除原失败记录。

随后以当前工作树重建交付包：`python scripts/package_stage1.py`，脚本自身完成 ZIP CRC、清单逐文件字节与 SHA-256、条目唯一与路径安全、本机会话密钥不出现等检查后才写出 PASS 证明；重建后的 dist/Lab4-stage1.zip 及 .zip.sha256、results/S7/manifest.json、results/S7/package-check.json 均为改后状态的当前记录，S7 时点值以上述快照为准。README 打包一节同步说明“每次重建都会得到新摘要”以及快照位置，避免把基线包当成当前包提交。

重建后另做一次独立解包复核（本地工具 .runtime/ui-refresh/verify_package.py，只读压缩包并解包到 .runtime）：压缩包摘要与 dist/Lab4-stage1.zip.sha256 一致；清单 193 行逐字节与 SHA-256 全部匹配、0 行不符；无 .env/.runtime/dist/results/Lab4/缓存等禁用条目（.env.example 属必需占位文件，按原脚本规则仅排除名为 .env 的文件）；解包副本内 `python scripts/check_workflow.py` 退出码 0；三份 S7 快照摘要与复制时记录一致。复核结果落在 results/ui-refresh/package-verify.json，该文件在打包之后生成，因此不在本次压缩包的清单内，属构建后本地复核记录，包内完整性仍以包内 manifest 与 package-check 为准。

### EXP-013 续 2：仓库发布（2026-10-16 Asia/Shanghai）

用户要求把代码推送到 GitHub 仓库并更新 README。远端 https://github.com/oceancat91/DB-Lab.git 原本只有 GitHub 初始提交的 README.md，正文是“# DB-Lab”与“数据库项目仓库”。本次把 README 改写为仓库门面文档：新增仓库地址与克隆步骤、当前状态与最近改动、界面改版小节（含两张改版后真实截图）、克隆后 dist 与 .env 不入库的说明，并调整打包一节改为“本地按需生成”。本地分支由 master 改名为 main，fetch 远端后以 --allow-unrelated-histories 合并其初始提交，README 的 add/add 冲突保留本项目版本，未使用强制推送，远端历史未被改写。

实测结果：提交 1eca93c（改版、证据与 README）与合并提交 c28f3fe 推送成功，远端 main=c28f3fe，共 196 个文件；远端不含 .env、.runtime、dist、results/Lab4；推送前核对了 .gitignore 覆盖范围，并用 git log -S 确认会话密钥从未进入任何提交。发布后按新文档重新打包并复核（清单 193 行全部匹配、包内 workflow 检查退出码 0）。未核验项：GitHub 仓库可见性未在设置中确认，仓库若为公开则课程原始 Word 与完整报告一并公开，是否保留由用户决定。本项不属于 S0–S7 阶段范围，不改变任何阶段状态与原有验收结论。
