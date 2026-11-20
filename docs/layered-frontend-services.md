# 六级平级门户前端服务

本文件记录「用户层 / 管理层 / 企业管理层 / 审计合规层 / 决策指挥层 / 开放生态层」
六个平级入口由同一前端代码库构建为六个独立前端服务的现状、理由与维护约束。

## 1. 现状

| 门户 | 角色 | 默认地址 | 启动命令 | 配置文件 | 入口 → 主入口 | 构建产物 | 公开 | 高敏 | 空闲 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 用户层 user | operator | `http://127.0.0.1:5173/` | `npm run dev` | `vite.config.js` | `index.html` → `src/main.js` | `dist/` | ✅ | ❌ | 30min |
| 管理层 admin | admin | `http://127.0.0.1:5174/` | `npm run dev:admin` | `vite.config.admin.mjs` | `admin.html` → `src/admin-main.js` | `dist-admin/` | ❌ | ✅ | 10min |
| 企业管理层 enterprise | enterprise | `http://127.0.0.1:5175/` | `npm run dev:enterprise` | `vite.config.enterprise.mjs` | `enterprise.html` → `src/enterprise-main.js` | `dist-enterprise/` | ❌ | ❌ | 15min |
| 审计合规层 audit | auditor | `http://127.0.0.1:5176/` | `npm run dev:audit` | `vite.config.audit.mjs` | `audit.html` → `src/audit-main.js` | `dist-audit/` | ❌ | ✅ | 10min |
| 决策指挥层 command | commander | `http://127.0.0.1:5177/` | `npm run dev:command` | `vite.config.command.mjs` | `command.html` → `src/command-main.js` | `dist-command/` | ❌ | ✅ | 10min |
| 开放生态层 open | partner | `http://127.0.0.1:5178/` | `npm run dev:open` | `vite.config.open.mjs` | `open.html` → `src/open-main.js` | `dist-open/` | ❌ | ❌ | 30min |

端口均可被环境变量覆盖：前端 `VITE_SMARTOPS_<ID>_PORT`、后端 `SMARTOPS_<ID>_PORT`。
六个服务：

- 共用同一后端（默认 `http://127.0.0.1:8080`），因此共用同一套服务端会话与 CSRF；
- 各自拥有独立路由表（`src/router/<id>.js`）与独立构建产物（`dist-<id>/`）；
- 四个新增门户共用一套骨架布局 `src/layouts/PortalScaffoldLayout.vue` 与着陆页
  `src/views/portal/PortalLandingView.vue`，按当前门户渲染标签、定位与能力，避免重复样板。

## 2. 单一事实来源：门户注册中心

所有「入口层面」的合法取值、角色映射、权限、空闲时长、限流、公开标记与高敏标记，
收敛在前后端同构的注册中心里，**不再散点硬编码**：

- 后端：`backend/src/main/java/com/smartops/security/PortalCatalog.java`（`@Component`）
- 前端：`frontend/src/security/portalCatalog.js`（`PORTAL_REGISTRY`）

`UserAccountService` / `AuthController` / `HumanVerificationService` 以及前端的
`portalSwitch.js` / `portalPolicy.js` / `accessModel.js` / `LoginView.vue` / 各 Layout
全部改读注册中心。两侧的一致性由 `frontend/test/portal-catalog.test.mjs` 跨端校验
（解析后端 Java 源码，断言 id / role / idle / public / sensitive / authority 完全对齐）。

### 2.1 新增一个平级门户只需要两步

1. 在前后端注册中心各加一条 `PortalSpec` / registry 条目；
2. 复用 `PortalScaffoldLayout` + `PortalLandingView` 生成一套入口脚手架
   （`vite.config.<id>.mjs` / `<id>.html` / `src/<id>-main.js` / `src/router/<id>.js`），
   并在 `package.json` 与 `scripts/windows/start-dev.ps1`、`stop-all-local.ps1` 登记端口。

鉴权链路（登录角色校验、空闲时长、MFA 触发、限流）自动跟随注册中心，无需再改 N 处。

## 3. 入口选择仍然不是授权

拆分只影响「前端静态服务从哪个端口提供」，**不改变授权模型**：

- `src/security/portalPolicy.js` 的 `sessionRouteDecision(user, route, portalId)` 仍是路由裁决者；
  `user` / `admin` 走原两参逻辑保持不动，新增门户走泛化分支（第三参 `portalId`），零回归。
- 服务端按 `portal` 与账号角色分别校验：每个门户只接受注册中心规约的对应角色登录
  （`portal/role` 不匹配 → 403，未知 portal → 400）。矩阵由
  `backend/.../PortalAccessIntegrationTest` 覆盖。
- 高敏门户（管理层 / 审计合规层 / 决策指挥层）强制 MFA、更严登录限流（5 次 / 900s）与更强密码策略；
  普通门户为 10 次 / 300s。
- 会话空闲时长按门户规约：管理层/审计/指挥 10 分钟，企业管理 15 分钟，用户/开放 30 分钟。

### 3.1 管理层隐蔽：受限入口不在公开登录页暴露

安全要求：管理层及其余受限门户不得被普通用户从公开登录页知晓，降低被扫描与撞库的风险。

- 用户层登录页只渲染 `PUBLIC_PORTALS`（当前仅 `user`）；当公开门户 ≤ 1 时连切换器都不显示。
- `?portal=admin` 等受限深链由 `redirectIfForeignPortal()` 跨源 `window.location.assign`
  整页跳转到该门户的专属服务地址，不在用户层渲染其登录表单。
- 管理面在用户层已**物理剥离**：`src/router/index.js` 不注册任何 `/admin` 路由与管理视图，
  侧栏不再有「管理控制台」分组，账户菜单不再有「管理入口」按钮，语音词典不再收录管理台；
  仅管理员可见的 `/architecture` 迁至管理端 `/admin/architecture`。用户层构建产物因此不含
  任何 `Admin*` 分包（`test/access-navigation.test.mjs`、`test/admin-foundation.test.mjs`、
  `test/build-optimization.test.mjs` 守卫）。
- 语音高危拦截表 `HAZARD_ROUTES` 也不再收录管理端路径，避免路径名字符串进入用户层产物；
  用户层既无管理路由/视图，也无对应的高危路径配置。
- 管理端落地路由由 `portalHome(portalId)` 按会话门户运行时推导（`user → /`，其余 `→ /<id>`），
  `portalPolicy` 与账户安全页不再写死 `/admin`；用户层源码与构建产物均不含 `/admin` 字面量
  （`test/admin-service-contract.test.mjs` 守卫）。
- 每个门户的 vite 配置拥有独立 `cacheDir`（`node_modules/.vite/<portal>`），支持六门户并行 `dev`，
  避免争抢共享依赖缓存导致 `EPERM: rmdir node_modules/.vite/deps`。
- 该隐蔽策略由 `frontend/test/login-portal.test.mjs` 守卫（只广告公开门户、受限深链跨源跳转）。

### 3.2 职责分离（SoD）：审计与管理互斥

审计合规层与系统管理两权分离：把仍持有有效 `platform_admin_profile`（`revoked_at IS NULL`）
的账号改任为 `auditor` 时，后端抛 409；撤销其管理员档案后才允许改任。由
`UserAccountService.update` 校验，`PortalAccessIntegrationTest` 覆盖。

### 3.3 切换入口 = 跨源跳转

登录页的入口切换不是改一个变量，而是跳到**另一种源上的独立服务**：

| 位置 | 行为 |
| --- | --- |
| 登录页入口切换 | `src/security/portalSwitch.js` 算目标地址；跨源用 `location.assign()` 整页跳转 |
| 受限深链 | `redirectIfForeignPortal()` 跨源整页跳转，不渲染对端表单 |
| 管理台「返回用户层」 | 先登出，再整页跳到用户层登录页 |

**必须整页跳转**：在 5173 上用 SPA 路由「渲染」其它门户，等于又回到多入口共用一个前端实例，
端口与构建产物会重新纠缠。

**跨端口需要重新登录是预期的**：会话 Cookie 按源（host:port）隔离，5173 的 `JSESSIONID`
不会自动带到 5174+。后端是同一个，但浏览器不共享该 Cookie。

端口不写死：`portalSwitch.js` 优先读 `VITE_SMARTOPS_<ID>_PORT`，其次按 hostname 推导；
`currentPortal()` 以服务自声明的 `window.__SMARTOPS_PORTAL_SURFACE__` 为准，端口仅作兜底，
未知端口退化为 `user`。

## 4. 维护约束

1. **所有门户的代理必须指向同一后端**，否则会话会分裂。各门户通过 `vite.shared.mjs`
   读取 `SMARTOPS_BACKEND_ORIGIN`。
2. **每个门户的 SPA 回退只回退自己的 `<id>.html`**，且必须放过 `/api`、`/ws`、`/@`、`/src/`、
   `/node_modules/` 与静态资源，否则登录与会话请求会拿到 HTML。新增门户复用
   `vite.portal-fallback.mjs` 的 `portalHtmlFallback(portalId)`，与 `vite.admin-fallback.mjs` 同构；
   由 `test/admin-service-fallback.test.mjs` 等守卫。
3. **用户层 `vite.config.js` 中的内联 `/ws` 代理声明不能删**：`test/session-security.test.mjs`
   用它守卫「终端开发流量与已认证同源」这一安全不变量。
4. **样式按门户隔离**：管理层以 `.admin-surface` 为作用域，新增门户以各自 surface 类作用域，
   门户令牌不定义在 `:root`，因此不会渗透到用户层或其它门户。
5. **`ARCHITECTURE_LAYERS` 仍为 7 层**（技术分层），六门户是其上方的「接入面」，在
   `ArchitectureMapView.vue` 中从 `PORTAL_REGISTRY` 单独渲染，不与技术分层耦合；
   `test/access-model.test.mjs` 断言 `ARCHITECTURE_LAYERS.length === 7` 不可破坏。
6. 后端 `app_user.role` 为单值字段，MVP 一人一门户；未来一人多门户需引入
   `user_portal_entitlement` 关联表，注册中心已预留判定点。

## 5. 回归测试

| 测试 | 覆盖 |
| --- | --- |
| `test/portal-catalog.test.mjs` | 注册中心完整性（6 门户、端口唯一、仅 user 公开、sensitive = admin/audit/command）、与后端 Java 同构 |
| `test/portal-switch.test.mjs` | 切换目标地址、surface 优先 / 端口兜底、未知门户 fail-closed |
| `test/login-portal.test.mjs` | 登录页只广告公开门户、受限深链跨源跳转、人机验证按敏感度选 action |
| `test/admin-service-contract.test.mjs` | 端口固定、独立入口、用户层 5173 与 `/ws` 不变量、管理员路由不含用户路由、客户端不自行授权 |
| `test/admin-service-fallback.test.mjs` | 回退只服务对应入口，且不吞 `/api`、`/ws` 与静态资源 |
| `backend PortalCatalogTest` | 注册中心纯单元不变量（角色/授权/空闲/公开/高敏/限流） |
| `backend PortalAccessIntegrationTest` | 六门户登录允许/拒绝矩阵、未知 portal 400、审计/管理 SoD 409 |
| `backend AdminFoundationIntegrationTest` | 入口选择不授予管理权限、最后一个管理员不可降权等既有治理不变量 |
| `test/*.browser.mjs` | 管理员/用户层服务表面、隔离与视觉核验（需运行服务器） |

## 6. 启动脚本

- 六个门户一起启动：`.\scripts\windows\start-dev.ps1`（拉起 5173–5178，并打印各门户地址）
- 单独启动某门户：`npm run dev:<id>`（`id ∈ {admin, enterprise, audit, command, open}`），用户层为 `npm run dev`
- 单独构建：`npm run build:<id>`，预览：`npm run preview:<id>`
- 停止：`.\scripts\windows\stop-all-local.ps1`（端口检查已覆盖 5173–5178，进程回收按路径匹配自动覆盖新门户）
