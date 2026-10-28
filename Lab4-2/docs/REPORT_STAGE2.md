# MongoDB 在线问卷系统第二阶段项目完成报告

本报告对应《大作业一：需求变更》的八项变更，覆盖目标、数据模型、版本与冻结语义、共享与权限、题库、使用情况与跨问卷统计、页面流程、测试结果、问题与解决办法、限制与 AI 使用说明。第二阶段的账号、问卷、校验跳转、提交与统计沿用第一阶段，不重复描述。

本报告由本人定稿，初稿借助 AI 编程助手起草；AI 的具体参与范围、犯过的错误与本人的改动见第 11 节，逐条记录见 [AI_USAGE.md](AI_USAGE.md)。

## 关键结果

| 维度 | 实际结果 | 证据 |
| --- | --- | --- |
| 需求覆盖 | 八项变更全部实现，需求 R15–R22 | [REQUIREMENTS.md](REQUIREMENTS.md) |
| 自动化测试 | 268 项通过（一阶段 245 + 二阶段 23），0 失败 | [pytest.json](../results/stage2/pytest.json) |
| Schema 与索引 | 61 项检查通过，清理通过 | [schema-check.json](../results/stage2/schema-check.json) |
| HTTP 全链路 | 34 步全部通过 | [http-e2e.json](../results/stage2/http-e2e.json) |
| 真实浏览器 | 12 步全部通过、7 张截图、0 脚本异常 | [browser/report.json](../results/stage2/browser/report.json) |

## 1. 项目目标与范围

在一阶段的问卷系统上增加“可复用题目库”：题目独立于问卷存在、可多版本、可共享、可归档、可组题库，并能查看单题跨问卷统计。范围仅需求变更的八项，不改一阶段的填写与统计行为。

八项变更逐条对照：

| 变更 | 实现 | 证据 |
| --- | --- | --- |
| 一 保存常用题目并在新问卷中复用 | `/library` 建题入库；建草稿问卷时从“我的题目 / 共享给我的”选择加入 | R15，`test_import_from_bank_uses_the_pinned_version` |
| 二 把题目共享给别人使用 | 按用户名共享写入 `question_shares`，被共享者可 import/fork，原题仍可继续使用 | R16，`test_sharing_allows_reuse_but_not_modification` |
| 三 修改题目不影响已发布问卷 | 发布后冻结快照；编辑生成新版本，旧问卷引用旧版本 | R17，`test_published_question_snapshot_survives_new_versions` |
| 四 修改历史与恢复 | 版本只追加并记录 `derived_from`/`restored_from`，恢复生成新版本 | R18，`test_versions_are_append_only_and_restorable` |
| 五 同一题目不同版本共存 | 每份问卷各自钉住 `question_version`，`usage` 按版本分组 | R19，`test_two_surveys_can_pin_different_versions_and_usage_lists_both` |
| 六 查看题目被哪些问卷使用 | `usage` 报表列出问卷与版本；修改时可选“只改草稿 / 生成新版本 / fork 成新题” | R20，`test_revision_modes_change_only_what_they_should` |
| 七 建立题目库 | `question_banks` + 条目钉版，可手动更新到当前版本 | R21，`test_bank_items_pin_versions_and_can_be_updated` |
| 八 跨问卷的单题统计 | 单选占比、数字均值、文本样本，支持 `limit` 与 `truncated` | R22，`test_cross_survey_statistics_aggregate_one_question` |

## 2. 数据模型

| 集合 | 作用 | 要点 |
| --- | --- | --- |
| `questions` | 题目实体 | `current_version`、`origin`、`status`（active/archived） |
| `question_versions` | 不可变版本 | 题型、题干、必答、选项、校验、`derived_from`、`supersedes`、`restored_from` |
| `question_shares` | 共享授权 | `(question_id, grantee_id)` 唯一，被共享者只能 fork |
| `question_banks` / `question_bank_items` | 题库 | 条目钉住版本，可“更新版本” |
| `question_share_links` | 分享链接 | 只存 `sha256(token)`，可设过期与领取次数 |

版本号只在题目内自增；问卷保存题目快照（含 `question_version`），发布后内容冻结。使用情况不建关联表，由 `ix_surveys_draft_question` 与 `ix_survey_versions_question` 两个多键索引反查。

## 3. 版本与冻结语义

1. 已发布问卷的题目不可改；编辑生成新版本，旧问卷仍引用旧版本。
2. 版本只追加：恢复历史版本会生成新版本并记录 `restored_from`。
3. 不同问卷可分别钉住同一题的不同版本，`usage` 按版本分组，能看出谁还在用旧版。

## 4. 共享与权限

所有者可建版本、恢复、共享、归档、管理题库；被共享者可以 import 与 fork，但不能改原题。`usage` 与跨问卷统计对非所有者只展示其本人问卷，另有 `other_surveys` 计数。分享链接面向任意登录用户：预览返回标题与所有者名；领取写入 `question_shares` 且幂等，重复领取不消耗次数；过期或次数用尽返回 410，吊销或归档返回 404。

## 5. 题库与统计

导入优先级为“显式版本 → 题库钉版 → 当前版本”。归档题目不能新加入问卷或题库，已加入的草稿与已发布快照不受影响。跨问卷统计支持单选占比、数字均值与文本样本，可用 `?limit=N`（默认 200、上限 500）限制扫描范围，被截断时返回 `truncated=true`。

## 6. 页面流程

`/library` 一页完成：左侧新建题目与题库，右侧“我的题目 / 共享给我的”、搜索、详情面板（版本历史、被哪些问卷使用、共享、修改题目、加入问卷、跨问卷统计）。详情里的“恢复此版本”“加入问卷”直接调用 API，失败时提示，不静默失败。

## 7. 测试结果

| 层级 | 内容 | 结果 |
| --- | --- | --- |
| 单元与集成 | 版本链、共享权限、归档、链接时效、题库钉版、统计口径、迁移 | 268 项通过 |
| Schema | 集合校验器与索引 | 61 项通过 |
| HTTP | 登录到统计的 34 步 | 全通过 |
| 浏览器 | 注册、建题、详情、恢复、共享、题库更新、加入问卷 | 12 步全通过 |

浏览器验证由 `scripts/browser_e2e.mjs` 通过 Chrome DevTools Protocol 驱动真实 Chrome 完成，截图与逐步结果存于 `results/stage2/browser/`。

## 8. 遇到的问题与解决办法

| 问题 | 处理 |
| --- | --- |
| 题库条目 PATCH 空体返回 422 | 新增可选的 `BankVersionInput` |
| 迁移遇到非 UUID 的旧题号 `q1` | 跳过并报告 `skipped_non_uuid` |
| 迁移用例按绝对计数断言，共享库上失败 | 改为相对基线增量 |
| 并发新建版本可能产生多余版本号 | 先认领 `current_version`，失败返回 409 |
| 共享者能看到他人问卷标题 | `usage` 对非所有者只返回本人问卷 + 计数 |
| 页面只有 HTTP 200 证据 | 补真实浏览器 12 步验证与截图 |

## 9. 限制与未验证

- 统计是“有上限的截断”，不是游标分页；超出上限只能调大 `limit`。
- 分享链接只有 API 与测试，页面暂无创建入口；过期由应用层比较，未用 TTL 索引。
- 迁移只在合成数据上验证，未在真实的一阶段库上执行。
- 部署仍是本机回环 HTTP 与无认证 MongoDB，未覆盖公网、TLS、移动端与其他浏览器。

## 10. 结论

八项变更均已落地并有可定位证据；已知限制集中在规模、部署与界面覆盖，不影响需求判定。后续优先补统计分页与真实库迁移演练。

## 11. AI 使用说明

本次使用的工具是 Codex 桌面应用中的 AI 编程助手，底层模型版本未单独核验，按 [AI_USAGE.md](AI_USAGE.md) 记为未知。

AI 帮了什么：按需求变更实现题目库（版本链、共享、归档、分享链接）、题库与跨问卷统计、迁移脚本、测试与文档初稿；仓库按两阶段重组（`a3ed940` 迁入 `Lab4-1/`，`c34d04d` 加入 `Lab4-2/`，三份公共文件留在 `Lab4/` 根）。

AI 做错了什么：

| 错误 | 发现方式 | 处理 |
| --- | --- | --- |
| 题库条目 PATCH 要求请求体带 `question_id` | 端到端脚本第 31 步 | 新增 `BankVersionInput` |
| 三处测试断言错误（字段名、非 UUID `_id`、过期 revision） | pytest 失败 | 修正测试 |
| 迁移用例绝对计数在共享库失败 | 两次 pytest | 改为相对基线 |
| 早期文档把“HTTP 200”当成页面可用 | 复核 | 收窄为“页面可达、交互未验证” |
| 计数“261/16”照抄 | 对照 `pytest.json` | 改为 268/23 并说明口径 |

以上错误在 [AI_USAGE.md](AI_USAGE.md) 的 AI-101 起各条中记录，失败证据保留未删。以下由 AI 完成，不记入我的贡献：题目库的数据模型与版本链、共享与归档权限、题库钉版、跨问卷统计口径、迁移与端到端脚本。我的工作：提出二阶段任务与仓库组织要求，逐项验收并确认取舍；对 D11–D18 的取舍与代码理解仍需我当面确认，AI 没有代填。项目解释（共享、恢复、统计范围、题库钉版）是项目决定，不是教师规定。
