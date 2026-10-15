# 基于 MongoDB 的在线问卷系统第一阶段

本文件所在的 Lab4 即项目根目录，所有命令在本目录执行。`results/Lab4/` 是历史包，不能作为当前项目入口，也不纳入本阶段交付。

本项目依据《大作业一第一阶段》设计一个简化在线问卷系统：注册用户创建并发布问卷，通过链接收集填写结果，系统执行可配置校验与跳转，并生成统计。重点是 MongoDB 数据建模、后端逻辑、可复现测试与真实 AI 使用记录。

**当前范围仅为第一阶段，按 S0–S7 推进，完成第一阶段交付即结束。** 第二阶段开发、数据迁移、回归任务及报告不列入当前计划。

**当前正在按阶段实施：S0、S1 已完成，S2 设计与 Schema 验证进行中。** 环境和真实 MongoDB 事务能力已验证，业务功能仍待后续实现与验收。实际状态与证据见 [progress.json](progress.json)，执行要求见 [WORKFLOW.md](WORKFLOW.md) 和 [AGENTS.md](AGENTS.md)。

## 计划实现的功能

- 账号注册、登录，创建者只能管理自己的问卷和查看统计。
- 问卷标题、说明、匿名开关、重复填写策略、发布、截止时间、关闭及分享链接。
- 单选、多选、文本填空、数字填空，以及必答、选择数量、长度、范围与整数校验。
- 从单选、多选和数字答案驱动的可配置跳转；服务端重新验证完整填写路径。
- 多人同时填写、成功提交保存、匿名身份隐藏、允许时多次填写与重试幂等。
- 整卷/单题统计：选项人数或次数、有效回答数、填空内容和数字平均值。

Word 同时提出“填写者先登录”与“匿名填写”。S1 已采纳“登录后对问卷创建者匿名”，并单独处理判重身份；这是项目解释，不是教师后续确认。规则优先级、统计人数口径、截止边界等见 [docs/DECISIONS.md](docs/DECISIONS.md)。

## 技术与数据设计方向

数据库必须使用 MongoDB，所有持久业务数据进入 MongoDB；禁止关系数据库和现成问卷系统框架。已采纳 Python、FastAPI、PyMongo 及简单页面，Python 环境用 conda；版本与实际环境命令见 [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)。

拟按职责分离账号、问卷、不可变发布版本和答卷。题目配置嵌入发布版本，每次成功提交形成独立答卷，保留版本和路径，避免把不断增长的所有回答塞进一个问卷文档。具体 Schema、索引、并发一致性与取舍在 S2 完成。S7 留存本阶段可复现的代码、Schema、数据样例和验收基线。

## 从哪里开始

1. 完整阅读 [AGENTS.md](AGENTS.md) 与 [WORKFLOW.md](WORKFLOW.md)，确认 [progress.json](progress.json) 中当前待执行阶段。
2. 阅读 [需求清单](docs/REQUIREMENTS.md)、[决策清单](docs/DECISIONS.md) 和 [测试计划](docs/TEST_PLAN.md)。
3. 先在 [实验日志](docs/EXPERIMENT_LOG.md) 登记本次范围和验收方式，再执行阶段任务；使用 AI 后同步更新 [AI 使用日志](docs/AI_USAGE.md)。
4. 保存真实证据，逐条完成阶段门禁，更新状态并运行流程检查。未通过则修复或记录阻塞，不能越级。

## 现在可以运行的检查

在项目根目录，用 Python 3.10 或更高版本运行：

```powershell
python scripts/check_workflow.py
```

检查器只用 Python 标准库，核对文档链接、需求/用例映射、源 Word 摘要、阶段顺序、门禁与证据字段。退出码 0 表示流程结构检查无 ERROR，1 表示存在 ERROR。它不会安装依赖、启动应用或连接数据库，也不能证明问卷功能通过。

目前没有可执行的应用启动命令。S1 完成后补齐实际验证的环境创建和 MongoDB 配置；S6 补齐 Schema 初始化、启动、页面入口及测试命令。禁止把尚不存在的命令写成已经可用。

## 文档与目录

- [WORKFLOW.md](WORKFLOW.md)：第一阶段 S0–S7 的步骤、产物和验收门禁。
- [AGENTS.md](AGENTS.md)：每次工作必须遵守的行为规范。
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)：Word 章节、需求编号、实现阶段、测试映射与提交清单。
- [docs/DECISIONS.md](docs/DECISIONS.md)：原文未定义语义的暂定方案及采纳方式。
- [docs/TEST_PLAN.md](docs/TEST_PLAN.md)：测试步骤、输入和预期；业务用例当前均未执行。
- [docs/EXPERIMENT_LOG.md](docs/EXPERIMENT_LOG.md)、[docs/AI_USAGE.md](docs/AI_USAGE.md)：真实工作记录及后续模板。
- [progress.json](progress.json)、[scripts/check_workflow.py](scripts/check_workflow.py)：阶段记录和只读结构检查。
- [results/planning/scope-review.md](results/planning/scope-review.md)：当前第一阶段范围的规划复核结果；首次规划审查作为历史留存。
- [大作业一第一阶段.docx](大作业一第一阶段.docx)：原始作业说明。

现有 `Lab1/`、`Lab2/`、`Lab3/` 是独立实验材料，本次未改动。未来实现目录、环境文件、数据库设计、API 文档、测试报告和第一阶段完成报告只在相应步骤实际产出后加入文档导航。

## 交付标准

第一阶段须交付可运行代码（含 Schema 与配置）、系统/数据库/API/关键逻辑文档、有步骤/输入/输出/结果的 26 组测试用例，以及完整第一阶段报告。报告说明 AI 帮助、AI 错误、实际修改和本人设计，并留存本阶段代码、数据和验收基线。26 组用例是项目验收计划，不是教师规定的用例数量。

本次尚未产生上述应用交付物或课程实测成绩。当前可交付范围是 workflow、行为规范、项目说明及配套计划与流程检查工具。
