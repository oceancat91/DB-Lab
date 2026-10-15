# 第一阶段 API 契约

基路径 `/api`，UTF-8 JSON。除 register/login 外需要有效会话；管理和结果接口还须当前用户拥有该问卷。管理越权统一 404，不能仅隐藏浏览器按钮。`/survey/{share_code}` 是分享页面，进入填写仍须登录。以下是 S2 冻结契约，功能验收在后续门禁记录。

## 身份与错误

- `POST /api/auth/register`：`{username,password}`；用户名 trim/casefold 后唯一，3–32 字符；密码 8–128 字符。201 返回 `{id,username,created_at}`，不自动登录。重复用户名 409。
- `POST /api/auth/login`：同样输入；200 返回当前用户，并设置 HttpOnly、SameSite=strict 会话 cookie。密码错误 401。
- `GET /api/auth/me`：200 当前用户，未认证 401。
- `POST /api/auth/logout`：204，撤销 MongoDB 会话并清除 cookie。

错误格式 `{"error":{"code":"validation","message":"可理解的错误","question_id":"可选题号"}}`；不回显密码、cookie、连接串或堆栈。401 未认证，404 不存在/无管理权限，409 用户名/编辑版本/状态/重复填写/幂等冲突，410 已关闭或截止，422 输入/配置/路径非法，503 数据库不可用。已实现路由的权限拒绝才是验收证据，未实现路由 404 不是。

浏览器采用同源 JSON 请求；不开放 CORS。非安全请求的 Origin 与当前主机不符时拒绝；会话过期由应用检查，不能依赖 TTL 立即清理。密码保存 scrypt 哈希及独立盐，原密码不入库。

## 问卷管理

- `POST /api/surveys`：创建草稿，输入 title、description（默认空）、allow_anonymous（默认 true）、allow_repeat（默认 false）、closes_at（ISO 8601 带时区或 null）。201 返回问卷。
- `GET /api/surveys`：当前用户列表，返回数组。
- `GET /api/surveys/{id}`：本人详情，包含草稿 questions/rules 或发布快照、revision、share_url。
- `PUT /api/surveys/{id}`：仅草稿，完整替换元数据、questions、rules；必须带读到的 revision，成功递增。不接受 owner_id、状态或服务器计数等额外字段。
- `POST /api/surveys/{id}/publish`：输入 `{revision}`，在事务内读取并检查同一 revision 的全部题目/规则，再条件写入和冻结，200 返回 published、version=1 和 share_url。版本冲突 409，空卷、坏规则、不是草稿时拒绝。
- `PATCH /api/surveys/{id}/deadline`：`{closes_at}`，仅本人；允许调整截止，不改变题目/匿名/重复策略。
- `POST /api/surveys/{id}/close`：仅本人已发布问卷；状态变为 closed，第一阶段不重开。

草稿样例：

```json
{
  "title": "学习体验", "description": "课程练习",
  "allow_anonymous": true, "allow_repeat": false, "closes_at": null,
  "revision": 0,
  "questions": [
    {"id":"q1","type":"single","title":"是否参加","required":true,
     "options":[{"id":"yes","label":"参加"},{"id":"no","label":"未参加"}],"validation":{}},
    {"id":"q2","type":"number","title":"体验评分","required":true,
     "validation":{"min_value":0,"max_value":10,"integer_only":true}},
    {"id":"q3","type":"text","title":"建议","required":false,"validation":{"max_length":200}}
  ],
  "rules":[{"source":"q1","op":"eq","value":"no","target":"q3","priority":10}]
}
```

type 为 single/multi/text/number。选择题选项为 `{id,label}`；validation 支持多选 min_choices/max_choices/exact_choices，文本 min_length/max_length，数字 min_value/max_value/integer_only。单个问卷最多 100 题，单题最多 50 选项，文本回答最多 10000 码点。规则为 source/op/value/target/priority；条件算子与确定性规则见 LOGIC。

## 填写与提交

- `GET /api/fill/{code}`：已登录读取当前有效发布卷，返回标题/说明、匿名/重复提示、version、questions/rules；不包含拥有者或私有填写者数据。草稿 409，关闭/到期 410，未知分享码 404。
- `POST /api/fill/{code}/next`：`{version,answers}`，answers 是已回答可达题 ID 到值的映射。缺键表示尚未访问并停在该题；键存在且为 null 表示主动跳过可选题，必答题 null 仍报错。服务端校验已答部分及路径，返回 `{path,next_question_id,complete,answers}`；不保存草稿。S4 实现。
- `POST /api/fill/{code}/submit`：`{version,request_id,answers}`，request_id 1–128 个安全字符，整个填写过程一次生成，重试复用。服务端从首题计算完整路径，拒绝缺必答、非法/陌生/路径外题，成功事务保存一份答卷。

submit 200 返回 `{id,submitted_at,replayed}`；第一次 replayed=false，相同内容重复请求 replayed=true；主动再填使用新 ID 且仅 allow_repeat=true 可成功。相同 ID 不同内容 409；禁重复再次填写 409。已成功回执的相同请求在问卷关闭后仍可重放。

## 统计与答卷

- `GET /api/surveys/{id}/statistics`：本人整卷统计。
- `GET /api/surveys/{id}/statistics/{question_id}`：本人单题，与整卷对应题保持一致。
- `GET /api/surveys/{id}/responses`：本人答卷明细，包含答卷 ID、时间、path、answers；匿名时不披露账户身份，非匿名时才包含 username。不返回数据库原文档或私有判重字段。

统计包含 survey_id、version、submissions、respondents、questions。单题含 id/type/title、answered_submissions、answered_people；选择题 options 含 id/label/count/people；填空题 values 保留原文，数字另含 mean。无数字回答 mean=null。任何已有答卷均无需手动“生成统计”操作。
