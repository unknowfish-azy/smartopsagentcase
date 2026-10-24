# 专业管理基础：已确认范围

用户确认双入口登录、独立管理台、账户生命周期、会话撤销、审计和最后管理员保护。保留真实服务端身份验证，不恢复前端自授管理员。

## 产品行为

- 登录入口 `user` / `admin`，默认 user；普通账号选择 admin 返回 403，管理员选 user 得到普通权限。
- `SessionUser` 返回 `{id,username,role,portal,mustChangePassword,authVersion}`；role 为账户角色，portal 为当前会话入口。浏览器不可决定权限。
- 管理入口为 `/admin`（总览）、`/admin/users`、`/admin/sessions`、`/admin/audit`、`/admin/readiness`；独立布局，弱化背景动效。用户原有页面保持。
- 用户安全页 `/account/security` 支持自己改密；必须改密时只允许进入该页及退出，不允许业务接口。
- 管理员新增账号与重置密码后均须首次改密；改密成功撤销全部旧会话并要求重新登录。
- 禁用、角色修改、密码重置均使目标账户旧会话失效，包括终端。不能禁用/降权最后一个启用管理员。
- 密码不回显、不返回、不写日志；列表永远不包含密码哈希、JSESSIONID 或 CSRF。
- 审计仅元数据：登录成败、账号创建/状态/角色/密码变更、会话撤销、退出。没有审计删除接口。
- 本批不增加资产细粒度授权、外部监控联调、MFA、收费模型调用或远程执行。

## API 契约

所有响应沿用 `{code,message,data}`（服务原有未包装模型接口除外）。变更请求沿用 CSRF。

- `POST /api/auth/login`: `{username,password,portal:'user'|'admin'}`；返回 SessionUser，缺 portal 默认 user。成功后仍重新 GET session 获取新 CSRF。
- `GET /api/auth/session`: `{user:SessionUser|null,csrfToken}`。
- `POST /api/auth/password`: `{currentPassword,newPassword}`；成功 `{reauthenticate:true}`；旧会话全部失效。
- `GET /api/admin/overview`: `{usersTotal,usersEnabled,adminsEnabled,activeSessions,recentFailures,pendingPasswordChanges}`，真实数据库/活动会话统计。
- `GET /api/admin/users?q=&page=1&pageSize=20&enabled=&role=`: `{items:[{id,username,role,enabled,mustChangePassword,createdAt}],total,page,pageSize}`；q 为账号子串。
- `POST /api/admin/users`: `{username,password,role}`；返回创建账户（不含密码），必须改密。
- `PUT /api/admin/users/{id}`: `{role,enabled}`；返回账户。不能修改 username；禁用/角色修改撤销旧会话。
- `POST /api/admin/users/{id}/reset-password`: `{password}`；成功 `{reauthenticate:true}`，目标账户必须改密。
- `GET /api/admin/sessions`: `{items:[{id,userId,username,portal,createdAt,lastSeenAt,current}]}`；id 为管理用随机 ID，绝不是会话 Cookie。
- `DELETE /api/admin/sessions/{id}`: 撤销对应会话，成功空 data。
- `GET /api/auth/sessions` / `DELETE /api/auth/sessions/{id}`: 仅本人会话（强制改密阶段禁止）。
- `GET /api/admin/audit?action=&outcome=&q=&page=1&pageSize=20`: `{items:[{id,actorId,actorUsername,action,targetId,outcome,createdAt}],total,page,pageSize}`；q 为账号子串，不返回请求正文。
- 现有 `GET /api/admin/readiness` 保持不变。

## 存储与安全

不更改已应用迁移的校验和。新增 account_security 表维护密码变更要求和 auth_version，新增 security_audit_event 表；通过左连接兼容已有账号。当前单节点 HttpSession 注册表维护可撤销会话；持久化版本校验用于拦截撤销竞态和角色旧快照，WS 每帧也校验。

锁住启用管理员集合后再变更账户，避免两管理员同时降权造成零管理员；事务中写审计，事务提交后撤销会话。数据库先备份再迁移，保留现有账号和业务数据。
