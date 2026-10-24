# 体检整改执行计划

## 执行状态（2026-10-02）

- 第一批关键业务与安全边界：已完成本机实施及验证。
- 第二批可见性与可用性：已完成主导航占位、连接中心主题、管理入口及对应回归。
- 验证：前端 229 项、后端 100 项、所选浏览器回归 19 项通过；真实会话、Cookie 重放拒绝、终端退出、数据库迁移重复执行另行实测。
- 未执行真实收费模型、远程写操作、外部监控/仓库集成及生产验收。
- 交付、启动与限制详见 `docs/reports/2026-10-02-remediation-results.md`。

依据：用户确认 `docs/reports/2026-10-01-functional-audit.md` 的整改顺序。

## 第一批：恢复关键业务并建立安全边界

1. 数据库：使用匹配版本 mysqldump 完整备份 smartops，成功且非空后才执行增量建表；保留现有行。增加迁移版本记录和关键表就绪检查。不执行 DROP 或重置。
2. 身份：新增 app_user、BCrypt 密码、服务器 HttpSession 登录和 CSRF；首次管理员通过服务端环境引导，无默认公开密码。取消登录角色选择和 localStorage 鉴权。所有业务 API 需要登录，管理接口需要管理员。
3. 身份隔离：兼容现有控制器参数，安全过滤器将 X-User-Id 固定为已认证用户 ID，WebSocket 从认证 Principal 取身份。内部模型接口继续使用内部 Token，不向浏览器暴露凭据。
4. 聊天：新增 `/api/chat/connections/{id}/invoke` 用户接口，复用已存在的 ModelConnectionService；未登录、跨用户、缺 CSRF 必须被拒绝。
5. 错误：业务状态和 HTTP 状态一致；前端显示服务器提供的安全错误信息，401 引导重新登录。

## 第二批：可见性与可用性

1. 主导航展开时统一让出内容宽度，连接中心浅色配色使用主题变量。
2. 管理台提供真实账户入口和接入检查；不具备实现的能力明确禁用，不保留空按钮。
3. 更新因接口/导航变化而过期的测试；模型、远程操作使用隔离替身，不调用真实服务。

## 文件职责

- `backend/src/main/java/com/smartops/security/`：会话身份、用户存储、登录限流和可信身份透传。
- `backend/src/main/java/com/smartops/controller/AuthController.java`：会话查询、登录、账户管理。
- `backend/src/main/java/com/smartops/controller/UserChatController.java`：用户模型调用边界。
- `backend/src/main/java/com/smartops/config/SecurityConfig.java`：用户认证、CSRF、管理路由、内部接口规则。
- `backend/src/main/resources/db/`：只增量建表的版本脚本。
- `frontend/src/security/session.js`：服务器会话与 CSRF 状态；旧存储仅保留为展示/工作区兼容缓存。
- `frontend/src/router/index.js`、`views/auth/LoginView.vue`、`layouts/MainLayout.vue`：登录、退出、访问守卫、占位布局。

## 先写失败测试

- `UserAuthenticationIntegrationTest`：匿名访问 401、缺 CSRF 403、错误密码 401、正确登录保持会话、登录角色不可伪造、X-User-Id 不可信、用户调用无需内部 Token、退出后失效、普通用户管理接口 403。
- 前端浏览器：伪造本地登录标记不能进入受保护页；真实登录后聊天和历史管理工作；登出后不可复用。
- 布局浏览器：知识库/连接中心/插件中心标题在导航右侧；浅色工作区文本使用深色。

## 验证命令

```powershell
cd backend
mvn.cmd -o -s .mvn/smartops-settings.xml -Dtest=UserAuthenticationIntegrationTest test
mvn.cmd -o -s .mvn/smartops-settings.xml test
cd ../frontend
npm.cmd test
npm.cmd run build
```

只在看到对应失败和根因后实现，再运行定向和全量测试。数据库备份与服务重启保存日志。未经用户要求不创建分支、不提交、不重置已有更改。

## 后续条件

真实远程采集、Prometheus/Loki/Harbor 接入、真实模型验收需要用户提供目标和凭据；不得生成成功状态或执行收费请求替代验收。流式回复、导出和大规模性能重构属于后续增强，不与本批安全修复混在一起交付。
