# 填写页面前端改版证据（EXP-013）

2026-10-16 Asia/Shanghai。范围、设计判断与事前计划见实验日志的 EXP-013 条目（[EXPERIMENT_LOG.md](../../docs/EXPERIMENT_LOG.md)）；关联需求 R03、R09、R11 的展示层，未改动任何服务端语义。

## 1 改动文件与摘要

| 文件 | SHA-256（本次改版后） | 说明 |
| --- | --- | --- |
| `survey_app/static/app.css` | `049F606F8A355654830BFF4F37D28EC4248CB87B02688A15FCFCCE7BBAAAAE17` | 重写为分节可读样式：设计令牌、纸墨配色、宋体标题、填写页答题路径轨；选择器集合由 250 增至 271 |
| `survey_app/static/app.js` | `85FF0B197D9F662D8E5951FF07099DF81B21D1E5419BA3C1DEB645F2EE9F6062` | 只改填写页渲染层：路径轨、进度行与必答标记、提示文案、核对编号、回执编号样式类、加载/失败态 |
| `docs/EXPERIMENT_LOG.md` | 见 Git 工作树 | 追加 EXP-013 事前登记与实际结果 |

`survey_app/templates/index.html` 与全部 Python 文件未改动；`git status` 只显示上述三个文件被修改。

## 2 命令与实际结果

| 检查 | 命令 | 实际结果 |
| --- | --- | --- |
| 流程结构 | `python scripts/check_workflow.py` | ERROR=0，WARN=0，退出码 0（`workflow-check.txt`） |
| 全量回归 | `python -m pytest tests --evidence results/local-run.json -q` | 245 passed，1 warning（既有 Starlette/httpx 弃用提示），退出码 0 |
| 选择器覆盖（本地工具，非交付物） | `python .runtime/ui-refresh/check_selectors.py` | 旧 250 → 新 271；丢失 10 个，逐条说明见第 4 节，退出码 1（表示存在差异，需人工判定） |
| 测试库隔离 | `python .runtime/ui-refresh/db_check.py` | 库 `lab4_ui_check_4f2a91c7b3d5`；`business_database_untouched=true`（`fixture-check.json`） |
| 清理与泄漏核对 | `python .runtime/ui-refresh/db_check.py --drop lab4_ui_check_4f2a91c7b3d5` | 业务库 `lab4_survey` 中同题名问卷 0 份、`ui_check_` 账号 0 个；仅删除该隔离库，业务库仍在（`cleanup-check.json`） |

## 3 真实浏览器验证

隔离实例：conda 环境 `lab4-survey` 的 uvicorn 监听 127.0.0.1:8005，`MONGODB_DATABASE` 环境变量覆盖为 `lab4_ui_check_4f2a91c7b3d5`。夹具由 `.runtime/ui-refresh/seed.py` 通过真实 API 建立：1 个合成创建者、1 个合成填写者、1 份已发布问卷（5 题覆盖单选/多选/数字/文本，多选 1–3 项、数字 0–120 整数、文本 ≤200 字），2 条真实跳转规则（q1 选“手机”跳到 q4；q3 大于 20 跳到 q5）。业务库 `lab4_survey` 未写入、未清空。

截图均为 1440×900（移动端 390×844），`before/` 为改版前、`after/` 为改版后。

| 状态 | 改版前 | 改版后 | 实测结论 |
| --- | --- | --- | --- |
| 登录页 | `before/01-login.png` | `after/01-login.png` | 标题换宋体，配色随令牌同步；表单与按钮行为不变 |
| 单选第 1 题 | `before/02-question-single.png` | `after/02-question-single.png` | 题目成为页面最大字号；路径轨出现“01 当前 + 按回答继续” |
| 多选第 2 题 | `before/03-question-multi.png` | `after/03-question-multi.png` | 提示改为“请选择 1–3 项”；选项行选中态用主色而非原绿色调 |
| 数字第 3 题 | `before/04-question-number.png` | `after/04-question-number.png` | 提示改为“填写 0–120 之间的整数”；路径轨连接线可见 |
| 文本第 5 题 | `before/05-question-text-history.png` | `after/05-question-text-rail.png` | 原“返回修改已答题”按钮行改为左侧路径轨 01–05，当前题高亮 |
| 核对页 | `before/06-review.png` | `after/06-review.png` | 逐题编号改为问卷题号，与路径轨一致 |
| 提交回执 | `before/07-receipt.png` | `after/07-receipt.png` | 回执编号与左侧朱砂标记构成唯一强调点 |
| 移动端 | `before/08-mobile-question.png` | `after/08-mobile-question.png` | 路径轨折为横向编号条，题号与题干同屏 |
| 工作台 | `before/09-workspace.png`、`before/10-workspace-full.png` | `after/09-workspace.png`、`after/10-workspace-full.png` | 侧栏、编辑区、状态标签随令牌同步，布局未改 |
| 分支跳题 | 无对应状态 | `after/11-branch-gap.png` | 第 1 题选“手机”后服务端跳到第 4 题，路径轨显示 01→04，跳过的 02、03 以编号断档体现 |
| 回改已答题 | 无对应状态 | `after/12-edit-return.png` | 点路径轨 02 回到第 2 题：路径截断为 01+02，原选中的 2 个选项保留 |
| 键盘焦点 | 无对应状态 | `after/13-keyboard-focus.png` | Tab 后焦点落在下一选项，选项行 outline 为 2px `rgb(29,107,94)` |

同一会话内 `agent-browser console` 与 `agent-browser errors` 均为空，无脚本错误。夹具库最终为 4 份答卷（改版前后各两次完整提交，用于对比截图），版本均为 1。

## 4 选择器差异逐条说明

改版后仍保留原有 id 与 `data-testid` 契约，因此旧定位方式继续有效。样式表选择器差异共 10 项丢失、31 项新增（`selector-check.txt`）：

- `.fill-history`、`.fill-history.button`、`.fill-history>.muted`：原为“返回修改已答题”按钮行的样式。该节点改为路径轨后仍保留 `fill-history` 类作为兼容钩子，但样式由 `.fill-path*` 承担。
- `.fill-question>.muted`：提示行改用 `.fill-hint.muted` 承担间距。
- `.preview-list`、`.preview-question`、`.preview-question.muted`、`.preview-question:last-child`、`.preview-question h3`、`.preview-question ul`：全仓库检索确认无任何 JS/HTML 产生这些类，属改版前遗留的死规则，本次不再保留。

## 5 未验证与已知范围

- `prefers-reduced-motion`：仅核对规则存在且填写页动效为 140ms 位移淡入，未在真实“减少动态效果”系统设置下截图。
- 移动端只实测 390×844 一档；平板宽度、横屏与其他机型未验证。
- 仅实测本机 Chrome；Safari、Firefox 未验证。
- 宋体标题在无 `SimSun`／`Songti SC` 的环境会回退到系统衬线体，未在其他操作系统实测。
- 交付包处置：`dist/Lab4-stage1.zip` 已按改版后的工作树重建，摘要记录在新的 `results/S7/manifest.json` 与 `dist/Lab4-stage1.zip.sha256`；S7 时点的包、清单与打包检查逐字节快照保存在 `dist/Lab4-stage1-s7-baseline.zip` 与 [S7 快照说明](../S7/archive/README.md)，21 个业务文件的基线复核见 [基线复核](code-baseline-check.json)，重建后的解包复核见 `package-verify.json`（该文件在打包之后生成，不在压缩包清单内）。重建过程见实验日志 EXP-013 续。
