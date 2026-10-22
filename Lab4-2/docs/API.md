# 第二阶段 API 契约

新增接口全部挂在 `/api` 下，UTF-8 JSON，认证方式与一阶段相同（HttpOnly、SameSite=Strict 会话 Cookie；除注册/登录外都需要会话）。一阶段的问卷、填写、统计接口未改动，契约见一阶段文档 `Lab4-1/docs/API.md`（阶段目录之间不互相链接）；本文只写第二阶段新增的 22 条路由与 1 个页面入口，并说明它们与既有接口的交互点。

错误格式沿用一阶段：`{"error":{"code":"…","message":"…","question_id":"可选题号"}}`，不回显密码、Cookie、连接串或堆栈；未捕获的数据库错误统一 503。字段错误的 422 只返回字段名列表，不回显输入值（`main.py:51-55`）。

**示例来源标注**：标“实际响应”的代码块摘自 [http-e2e.json](../results/stage2/http-e2e.json) 的对应步骤（作者运行 34 步全 PASS，`generated_at` 2026-10-22T10:11:44Z；节选时删除了重复字段，未改动取值）；标“按代码构造”的代码块由 [main.py](../survey_app/main.py)、[library.py](../survey_app/library.py)、[models.py](../survey_app/models.py) 的返回结构推出，**没有**对应的真实请求记录，不能当作运行证据。

## 1. 新增端点总表

### 1.1 题目实体与版本

| 方法 | 路径 | 权限 | 请求 | 成功响应 | 可能错误 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/questions` | 登录用户 | `QuestionInput` | 201，题目详情 | 401、422 |
| GET | `/api/questions?type=&q=` | 登录用户 | 查询参数可选 | 200，题目摘要数组（本人 `active`，最多 200 条） | 401 |
| GET | `/api/questions/shared` | 登录用户 | 无 | 200，共享给我的题目摘要数组（最多 200 条，含 `owner_name`） | 401 |
| GET | `/api/questions/{question_id}` | 所有者或被共享者 | 无 | 200，题目详情（含 `current`、`versions`、`banks`、`shares`） | 401、404 |
| GET | `/api/questions/{question_id}/versions` | 所有者或被共享者 | 无 | 200，版本摘要数组 | 401、404 |
| POST | `/api/questions/{question_id}/versions` | **仅所有者** | `QuestionInput` | 201，题目详情（`current_version` +1） | 401、404、409、422 |
| POST | `/api/questions/{question_id}/versions/{version}/restore` | **仅所有者** | 无 | 201，题目详情（新增一版，`restored_from`=来源版本） | 401、404、409、422 |
| POST | `/api/questions/{question_id}/fork?version=` | 所有者或被共享者 | `QuestionInput`，`version` 可选 | 201，**新**题目详情（`origin=forked`） | 401、404、422 |

### 1.2 共享、使用情况、统计

| 方法 | 路径 | 权限 | 请求 | 成功响应 | 可能错误 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/questions/{question_id}/shares` | 所有者或被共享者 | 无 | 200，共享名单数组（非所有者得到空数组） | 401、404 |
| POST | `/api/questions/{question_id}/shares` | **仅所有者** | `ShareInput` | 201，题目详情（`shares` 增加一条） | 401、404、409、422 |
| DELETE | `/api/questions/{question_id}/shares/{grantee_id}` | **仅所有者** | 无 | 200，题目详情 | 401、404 |
| GET | `/api/questions/{question_id}/usage` | 所有者或被共享者 | 无 | 200，使用情况（`usages`、`usage_count`） | 401、404 |
| GET | `/api/questions/{question_id}/statistics` | 所有者或被共享者（范围不同） | 无 | 200，跨问卷统计（`scope`、`aggregate`、`by_question_version`、`surveys`） | 401、404 |

### 1.3 题库及其条目

| 方法 | 路径 | 权限 | 请求 | 成功响应 | 可能错误 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/banks` | 登录用户 | `BankInput` | 201，题库详情（`items` 为空数组） | 401、409、422 |
| GET | `/api/banks` | 登录用户 | 无 | 200，本人题库数组（含条目计数） | 401 |
| GET | `/api/banks/{bank_id}` | **仅所有者** | 无 | 200，题库详情（`items` 含 `outdated`、`preview`） | 401、404 |
| PATCH | `/api/banks/{bank_id}` | **仅所有者** | `BankPatch` | 200，题库详情 | 401、404、409、422 |
| POST | `/api/banks/{bank_id}/items` | **仅所有者**（题目需可访问） | `BankItemInput` | 201，题库详情 | 401、404、409、422 |
| PATCH | `/api/banks/{bank_id}/items/{question_id}` | **仅所有者**（题目需可访问） | `BankVersionInput` 或空请求体 | 200，题库详情（`question_version` 指向新钉版本） | 401、404、422 |
| DELETE | `/api/banks/{bank_id}/items/{question_id}` | **仅所有者** | 无 | 200，题库详情 | 401、404 |

### 1.4 问卷侧集成与页面

| 方法 | 路径 | 权限 | 请求 | 成功响应 | 可能错误 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/surveys/{survey_id}/questions/import` | 问卷所有者；题目需可访问 | `ImportQuestionInput` | 201，**问卷**载荷（草稿，`revision` +1） | 401、404、409、422 |
| POST | `/api/surveys/{survey_id}/questions/{question_id}/revision` | 问卷所有者；模式有额外权限 | `RevisionInput` | 200，**问卷**载荷（草稿，`revision` +1） | 401、403、404、409、422 |
| GET | `/library` | 无需登录（页面本身） | 无 | 200，`library.html` | — |

`GET /library` 只返回静态页面；页面里的每个数据请求仍要登录，未登录时脚本显示“登录后管理题目库”面板并发起跳转链接。静态资源为 `/static/library.js`、`/static/library.css`（另有复用的 `/static/app.css`）。

## 2. 请求与响应示例

### 2.1 创建题目

请求：

```json
{"type":"single","title":"你的年龄段","required":true,
 "options":[{"id":"a","label":"18-25"},{"id":"b","label":"26-35"}],
 "validation":{},"note":"初版"}
```

响应 201（实际响应，http-e2e 第 5 步，节选）：

```json
{"id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","owner_id":"8885ba6f-ccfc-49c8-a021-fb9be6c32b3c",
 "type":"single","title":"你的年龄段","current_version":1,"status":"active","origin":"created",
 "owned":true,"shared_with_me":false,"share_count":0,"bank_count":0,
 "current":{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","version":1,"type":"single",
   "title":"你的年龄段","required":true,
   "options":[{"id":"a","label":"18-25"},{"id":"b","label":"26-35"}],
   "validation":{},"note":"初版","derived_from":null,"supersedes":null,"restored_from":null,
   "created_at":"2026-10-22T10:11:44.109000+00:00"},
 "versions":[{"version":1,"note":"初版","created_at":"2026-10-22T10:11:44.109000+00:00",
   "derived_from":null,"restored_from":null,"supersedes":null}],
 "banks":[],"shares":[]}
```

服务端生成的字段（`id`、`owner_id`、`current_version`、`status`、`origin`、时间）不接受客户端输入；请求里多带 `owner_id` 会被 422 拒绝（`tests/test_library.py::test_question_creation_listing_and_validation` 断言）。`POST /api/questions` 的唯一键冲突分支（409 `exists`）在 HTTP 层不可达，因为题目 ID 由服务端生成，该分支只防御内部调用。

### 2.2 我的题目列表与共享列表

响应 200（按代码构造，无对应 HTTP 记录）：

```json
[{"id":"4902a2f4-…","owner_id":"8885ba6f-…","type":"single","title":"你的年龄段",
  "current_version":3,"status":"active","origin":"created",
  "created_at":"2026-10-22T10:11:44.108000+00:00","updated_at":"2026-10-22T10:11:44.175000+00:00",
  "owned":true,"shared_with_me":false,"share_count":1,"bank_count":0}]
```

`GET /api/questions/shared` 的每条额外含 `owner_name`（实际响应，http-e2e 第 9 步，节选）：

```json
[{"id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","owner_id":"8885ba6f-ccfc-49c8-a021-fb9be6c32b3c",
  "type":"single","title":"你的年龄段","current_version":3,"status":"active","origin":"created",
  "owned":false,"shared_with_me":true,"share_count":1,"bank_count":0,
  "owner_name":"u_owner_bbe2874859"}]
```

`q` 只匹配标题（`re.escape` + 不区分大小写），`type` 精确匹配题型；两者都只作用于本人列表，共享列表没有过滤参数。

### 2.3 追加版本与恢复

`POST /api/questions/{id}/versions` 请求体同 `QuestionInput`；响应 201 的 `current_version` 变为 2，`versions` 出现两条，其中 v2 的 `derived_from={"question_id":"…","version":1}`、`supersedes=1`（按代码构造；形状与下方恢复响应一致）。

`POST /api/questions/{id}/versions/1/restore` 响应 201（实际响应，http-e2e 第 7 步，节选）：

```json
{"id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","current_version":3,
 "current":{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","version":3,
   "title":"你的年龄段","note":"恢复自 v1",
   "derived_from":{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","version":1},
   "supersedes":2,"restored_from":1,
   "created_at":"2026-10-22T10:11:44.175000+00:00"},
 "versions":[{"version":1,"note":"初版","restored_from":null,"supersedes":null},
   {"version":2,"note":"增加第三段","restored_from":null,"supersedes":1},
   {"version":3,"note":"恢复自 v1","restored_from":1,"supersedes":2}]}
```

恢复不删除 v2，也不把 `current_version` 指回 1；v3 是内容等于 v1 的新版本。

### 2.4 共享与另存

`POST /api/questions/{id}/shares` 请求 `{"username":"u_mate_bbe2874859"}`，响应 201 为题目详情，`shares` 出现（实际响应，http-e2e 第 8 步，节选）：

```json
{"share_count":1,
 "shares":[{"user_id":"08c2d726-5107-40b8-8544-b1d0b1e58061","username":"u_mate_bbe2874859"}]}
```

`POST /api/questions/{id}/fork` 请求体同 `QuestionInput`，响应 201 是新题目（实际响应，http-e2e 第 33 步，节选）：

```json
{"id":"7cca0a8c-0088-426d-9789-8e33efaeeddb","owner_id":"08c2d726-5107-40b8-8544-b1d0b1e58061",
 "title":"同事改写的题","current_version":1,"origin":"forked",
 "current":{"version":1,"title":"同事改写的题",
   "derived_from":{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","version":3},
   "supersedes":null,"restored_from":null}}
```

注意 `derived_from.version` 是 3，因为另存时源题目的当前版本已经是 3（恢复之后）；`GET /api/questions/{new_id}/versions` 返回同样的血缘（第 34 步）。

### 2.5 导入草稿问卷

请求：

```json
{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","version":1}
```

响应 201（实际响应，http-e2e 第 12 步，节选）：

```json
{"id":"e328cd5d-df08-4060-a799-5bafb3b6ffaa","title":"问卷一","status":"draft",
 "revision":1,"version":null,"share_url":"/survey/8dSdnDZXXQqHPMSd",
 "questions":[{"id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","type":"single","title":"你的年龄段",
   "required":true,"options":[{"id":"a","label":"18-25"},{"id":"b","label":"26-35"}],
   "validation":{},"question_version":1}],
 "rules":[]}
```

返回的是**问卷**载荷，不是题目载荷；`revision` 已递增，后续发布要带这个 revision。同名题目重复导入返回 409 `exists`；已发布问卷返回 409 `immutable`；题目超过 100 道返回 422。

### 2.6 修订的三种模式

`POST /api/surveys/{survey_id}/questions/{question_id}/revision` 请求：

```json
{"mode":"new_version","question":{"type":"single","title":"新版本","required":true,
 "options":[{"id":"a","label":"甲"},{"id":"b","label":"乙"}],"validation":{},"note":""}}
```

响应 200 为问卷载荷。三种模式的差别（依据 `library.py:488-528` 与 `tests/test_library.py::test_revision_modes_change_only_what_they_should`）：

| 模式 | 对题目库 | 对当前问卷 | 规则引用 |
| --- | --- | --- | --- |
| `draft_only` | 不动 | 用新内容替换该题，**去掉** `question_version`（变成本地题） | 保留（题号未变） |
| `new_version` | 追加一个版本，`current_version` +1 | 指向新版本，带 `question_version` | 保留 |
| `fork` | 新建一个题目（`origin=forked`） | 换成新题目的 v1，`id` 改变 | 把引用旧题号的 `source`/`target` 改写为新题号 |

`new_version` 与 `fork` 需要该题在题目库中（否则 409 `not_stored`）；`new_version` 还要求当前用户是所有者（否则 403）。

### 2.7 使用情况

`GET /api/questions/{id}/usage` 响应 200（实际响应，http-e2e 第 26 步，节选）：

```json
{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","title":"你的年龄段","current_version":3,
 "usage_count":3,
 "usages":[
  {"survey_id":"e328cd5d-…","title":"问卷一","status":"published","version":1,
   "question_version":1,"owner_is_self":true,"editable":false},
  {"survey_id":"b467e646-…","title":"问卷二","status":"published","version":1,
   "question_version":2,"owner_is_self":true,"editable":false},
  {"survey_id":"7ec18beb-…","title":"同事问卷","status":"published","version":1,
   "question_version":1,"owner_is_self":false,"editable":false}]}
```

草稿问卷的行会给出 `version:null`、`editable:true`、`question_version` 取草稿里该题的值（可能是 null，表示本地修改）。接口没有分页，返回全部命中行。

### 2.8 跨问卷统计

`GET /api/questions/{id}/statistics` 响应 200（实际响应，http-e2e 第 27 步，节选）：

```json
{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","title":"你的年龄段","current_version":3,
 "scope":"all surveys","total_answered":3,"survey_count":3,
 "aggregate":{"answered":3,"by_type":{"single":{"answered":3,
   "options":[{"id":"a","label":"18-25","count":2},{"id":"b","label":"26-35","count":1}]}}},
 "by_question_version":{
   "1":{"answered":2,"by_type":{"single":{"answered":2,"options":[{"id":"a","label":"18-25","count":2}]}}},
   "2":{"answered":1,"by_type":{"single":{"answered":1,"options":[{"id":"b","label":"26-35","count":1}]}}}},
 "surveys":[
   {"survey_id":"7ec18beb-…","title":"同事问卷","owner_is_self":false,"survey_version":1,
    "question_version":1,"answered":1},
   {"survey_id":"e328cd5d-…","title":"问卷一","owner_is_self":true,"survey_version":1,
    "question_version":1,"answered":1},
   {"survey_id":"b467e646-…","title":"问卷二","owner_is_self":true,"survey_version":1,
    "question_version":2,"answered":1}]}
```

被共享者调用同一接口（实际响应，http-e2e 第 28 步，节选）：

```json
{"scope":"own surveys only","survey_count":1,"total_answered":1,
 "surveys":[{"survey_id":"7ec18beb-…","title":"同事问卷","owner_is_self":true,
   "survey_version":1,"question_version":1,"answered":1}]}
```

文本题的 `values`、数字题的 `mean`/`count` 结构见一阶段统计口径；跨问卷统计沿用同一套字段，只是多了 `scope`、`by_question_version` 与 `surveys`。

### 2.9 题库

`POST /api/banks` 请求 `{"name":"常用题 bbe2874859","description":""}`，响应 201（实际响应，http-e2e 第 29 步）：

```json
{"id":"2cd5d183-14fb-4c48-b7e3-2554afc0b1de","name":"常用题 bbe2874859","description":"",
 "items":[],"created_at":"2026-10-22T10:11:44.612000+00:00"}
```

`POST /api/banks/{bank_id}/items` 请求 `{"question_id":"…","version":1}`；随后题目升到 v3，题库详情显示钉住版本与最新版本不一致（实际响应，http-e2e 第 30 步）：

```json
{"items":[{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","question_version":1,
  "title":"你的年龄段","type":"single","current_version":3,"outdated":true,"preview":"你的年龄段"}]}
```

`PATCH /api/banks/{bank_id}/items/{question_id}` 空请求体即“更新到当前版本”（实际响应，http-e2e 第 31 步）：

```json
{"items":[{"question_id":"4902a2f4-4c8c-45b6-9b31-a9370d485139","question_version":3,
  "title":"你的年龄段","type":"single","current_version":3,"outdated":false,"preview":"你的年龄段"}]}
```

该路由的请求体是**可选**的 `BankVersionInput`（只有 `version`，题号来自路径）。早期版本要求请求体带 `question_id`，空体请求因此得到 422（`body.question_id`）；修复方式是新增 `BankVersionInput`（`models.py:117-119`）并把路由参数改为可空，见 [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) EXP-105。

`GET /api/banks/{bank_id}` 在非所有者处返回 404（实际响应，http-e2e 第 32 步，`{"error":{"code":"not_found","message":"题库不存在或无权访问"}}`）。

### 2.10 页面入口

`GET /library` 返回 [library.html](../survey_app/templates/library.html)。2026-10-22 文档整理时对运行中的实例（`127.0.0.1:8012`）做过只读 GET 核验：`/library` 200（4,880 字节 HTML）、`/static/library.js` 200（23,051 字节）、`/static/library.css` 200（3,644 字节）、`/static/app.css` 200（32,802 字节）、`/health` 200。这是页面加载层面的核验，**没有**执行登录后的交互浏览器会话。

## 3. 权限矩阵

“所有者”= 题目/题库/问卷的 `owner_id` 等于当前用户；“被共享者”= `question_shares` 中有对应记录；“其他登录用户”= 无授权。

| 操作 | 所有者 | 被共享者 | 其他登录用户 | 未登录 |
| --- | --- | --- | --- | --- |
| 查看题目详情 / 版本列表 | 200 | 200 | 404 | 401 |
| 我的题目列表 | 含该题（`owned=true`） | 不含 | 不含 | 401 |
| 共享给我的列表 | 不含 | 含该题（`owned=false`，含 `owner_name`） | 不含 | 401 |
| 新建版本 / 恢复 | 201 | 404 | 404 | 401 |
| 另存（fork） | 201 | 201 | 404 | 401 |
| 查看共享名单 | 200（含记录） | 200（空数组） | 404 | 401 |
| 共享 / 取消共享 | 201 / 200 | 404 | 404 | 401 |
| 使用情况 | 200 | 200（**含他人问卷行**） | 404 | 401 |
| 跨问卷统计 | 200（`all surveys`） | 200（`own surveys only`） | 404 | 401 |
| 新建/列出题库、看题库详情、改名、增删条目 | 201/200/200/200 | 404 | 404 | 401 |
| 导入题目到问卷 | 201（草稿） | 201（草稿，题目需被共享给本人） | 404（题目不可访问） | 401 |
| 修正问卷内题目 | 200 | 200（`draft_only`/`fork`），403（`new_version`） | 404 | 401 |

两处值得注意的差异：

1. **同一资源的不同入口用不同状态码**：对非所有者的“新建版本”，`POST /api/questions/{id}/versions` 返回 404（`_accessible(owner_only=True)`），而在问卷修订接口里对同一情形返回 403（题目已通过问卷上下文暴露存在性）。客户端不能把 404 与 403 当成同一含义。
2. **使用情况不按统计范围过滤**：被共享者能看到所有者问卷的标题、状态与题目版本；统计接口只聚合被共享者自己的问卷。这是实现与 [DECISIONS.md](DECISIONS.md) D17 之间的已知偏差，记录在 [REPORT_STAGE2.md](REPORT_STAGE2.md) 第 10 节，未修复。

## 4. 状态码语义

| 状态码 | 本阶段的触发场景 | 备注 |
| --- | --- | --- |
| 401 | 未登录或会话失效 | 由 `session_user` 统一抛出，与一阶段一致 |
| 403 | ①跨站写请求（Origin 校验中间件）；②问卷修订模式 `new_version` 但题目不属于当前用户 | 第二类只出现在修订接口；其余越权用 404，避免泄露存在性 |
| 404 | 题目/题库/版本/密共享对象不存在；无权访问或无权操作；要共享的用户名不存在；取消共享时该用户未被共享；问卷里没有这道题；题库里没有这道题 | 统一响应 `not_found`；“无权”与“不存在”故意不可区分 |
| 409 `exists` | 同名题库、题目已在题库、已共享给该用户、该题已在问卷中 | 唯一键冲突的应用层映射 |
| 409 `revision` | 追加题目版本时乐观锁冲突（“题目已被他人修改”）、问卷 revision 过期 | 需要重新读取后重试 |
| 409 `immutable` | 对已发布/已关闭问卷导入或修订题目 | 与一阶段“发布后冻结”同义 |
| 409 `not_stored` | 修订模式选 `new_version`/`fork`，但该题不是题目库中的题目（例如已 `draft_only` 改过） | 提示改用 `draft_only`/`fork` |
| 422 `validation` | 题目内容不合法（复用一阶段配置校验）、共享给自己、问卷已满 100 题、`mode` 非三种取值 | 题目内容错误尽量带 `question_id`；字段形状错误由 FastAPI 返回字段名列表 |
| 422 `too_large` | 请求体超过 1 MiB | 中间件在读取时累计判断 |
| 503 `database` | 数据库不可用 | 不回显驱动异常细节 |

几个容易误判的点：

- 共享给**不存在的用户名**返回 404，不是 422（对方不存在，不在服务端“校验”范畴）；共享给**自己**才返回 422。
- 重复共享、重复加入题库、题库重名都是 409 而不是幂等成功；客户端要刷新后重试。
- `PATCH /api/banks/{bank_id}` 使用 `exclude_none=True`，只更新提供的字段；空请求体是合法的 200（返回当前详情），不会把名称或说明清空。

## 5. 与一阶段接口的交互

- `PUT /api/surveys/{survey_id}`（一阶段接口）在第二阶段多了一步：保存前对题目数组调用 `normalize_question_refs`（`service.py:81-85`），把不可信或与版本内容不符的 `question_version` 删除。客户端不需要主动调用任何新接口就能继续用旧接口保存问卷。
- 发布（`POST /api/surveys/{id}/publish`）不需要改动：`question_version` 是题目对象里的普通整数字段，发布快照原样保留它，因此发布后仍能按版本统计。
- 填写与提交接口完全不感知题目库：回答按题目 ID 存入 `responses.answers`，跨问卷统计靠这个 ID 关联。

## 6. 未验证与边界

- 未做分页/限流：`GET /api/questions` 与 `/api/questions/shared` 固定 `limit(200)`，`/usage` 与 `/statistics` 没有条数上限，响应方向不受 1 MiB 限制（与一阶段统计接口相同的边界）。
- 未对并发 `POST /versions`、`POST /share` 做专门的并发夹具；一致性依赖唯一索引，未用真实并发请求验证（一阶段的并发夹具不覆盖新接口）。
- 示例中“按代码构造”的响应没有对应的真实 HTTP 记录；只有标注“实际响应”的代码块可追溯到 [http-e2e.json](../results/stage2/http-e2e.json)。
- 页面交互（点击、表单、弹窗）没有浏览器会话证据；只验证了 `/library` 与静态资源返回 200。

## 补充（2026-10-22）：从题库加入时按钉住版本

`POST /api/surveys/{survey_id}/questions/import` 的请求体新增可选 `bank_id`。版本选择顺序为：
显式 `version` → 该题库条目钉住的 `question_version` → 题目当前版本。`bank_id` 必须属于当前用户，
且该题必须在该题库中，否则返回 404；成功时响应仍是更新后的问卷草稿。

## 补充（2026-10-22 第二轮）：归档与分享链接

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| PATCH | `/api/questions/{id}` | 所有者 | 请求体 `{"status": "active"\|"archived"}`；归档会同时吊销该题所有分享链接 |
| POST | `/api/questions/{id}/share-links` | 所有者 | 生成一次性分享令牌，返回 `{id, token, path}`；已归档题目返回 409 |
| GET | `/api/questions/{id}/share-links` | 所有者 | 列出链接（只返回 id、创建时间、是否吊销），不返回令牌 |
| DELETE | `/api/questions/{id}/share-links/{link_id}` | 所有者 | 吊销链接 |
| GET | `/api/share-links/{token}` | 任意登录用户 | 预览题目（标题、题型、当前版本、所有者名） |
| POST | `/api/share-links/{token}/claim` | 任意登录用户 | 领取共享授权，重复领取幂等；令牌失效或题目归档返回 404/409 |

令牌只以 SHA-256 摘要存库，明文只在创建响应里出现一次；归档题目不能再被分享或加入问卷，但已加入的草稿与已发布快照不受影响。

### 补充（2026-10-22 第四轮）：链接时效与统计上限

- `POST /api/questions/{id}/share-links` 请求体可选 `{"expires_in_seconds": 3600, "max_uses": 3}`；响应新增 `expires_at`、`max_uses`、`uses`。过期或次数用完时，预览与领取都返回 410。
- `GET /api/questions/{id}/statistics` 新增查询参数 `limit`（默认 200，最大 500）；响应的 `survey_limit` 反映实际取值，`truncated=true` 表示被截断。
