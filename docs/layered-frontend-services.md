# 用户层与管理员层：双前端服务

本文件记录「用户层 / 管理员层」由同一前端服务拆成两个独立前端服务的现状、理由与维护约束。

## 1. 现状

| 入口 | 地址 | 启动命令 | 配置文件 | 入口文件 |
| --- | --- | --- | --- | --- |
| 用户层 | `http://127.0.0.1:5173/` | `npm run dev` | `frontend/vite.config.js` | `frontend/index.html` → `src/main.js` |
| 管理员层 | `http://127.0.0.1:5174/` | `npm run dev:admin` | `frontend/vite.config.admin.mjs` | `frontend/admin.html` → `src/admin-main.js` |

两个服务：

- 共用同一后端（默认 `http://127.0.0.1:8080`），因此共用同一套服务端会话与 CSRF；
- 各自拥有独立路由表（`src/router/index.js` 与 `src/router/admin.js`）；
- 各自拥有独立构建产物（`frontend/dist/` 与 `frontend/dist-admin/`）。

## 2. 为什么拆开

原先两个入口共用一个 SPA 实例，仅靠 `?portal=admin` 区分，代价是：

1. 两个入口抢同一个端口，管理层无法独立启动或独立暴露；
2. 两个入口的地址、书签互相覆盖；
3. 管理员层不存在独立的构建产物，无法只部署管理层。

拆分后，**用户层的端口（5173）、外观、导航与交互一律未改**；`5173/login?portal=admin` 仍可用，作为兼容入口保留。

## 3. 入口选择仍然不是授权

拆分只影响「前端静态服务从哪个端口提供」，**不改变授权模型**：

- `src/security/portalPolicy.js` 的 `sessionRouteDecision` 仍是唯一的路由裁决者；
- 管理员层路由表在首次导航时把 `?portal=admin` 补进登录页——这只是默认选中的入口，不是授予角色；
- 服务端仍按 `portal` 与账号角色分别校验（用户层入口不接受管理员账号，管理员层入口不接受普通账号）；
- 管理员层与用户层的会话空闲时长仍分别是 10 分钟与 30 分钟。

### 3.1 切换入口 = 跨源跳转

登录页的「用户层 / 管理员层」不是切换一个变量，而是跳到**另一种源上的独立服务**：

| 位置 | 行为 |
| --- | --- |
| 登录页入口切换 | `src/security/portalSwitch.js` 算出目标地址；跨源用 `location.assign()` 整页跳转 |
| 管理员台「返回用户层」 | 先登出，再整页跳到用户层登录页 |
| 登录页提示 | 显示"将打开 `127.0.0.1:5174/login`（独立服务，需在该入口重新登录）" |

**必须整页跳转**：在 5173 上用 SPA 路由"渲染"管理员层，等于又回到两个入口共用一个前端实例，端口与构建产物会重新纠缠。

**跨端口需要重新登录是预期的**：会话 Cookie 按源（host:port）隔离，5173 的 `JSESSIONID` 不会自动带到 5174。后端是同一个，但浏览器不共享该 Cookie。

端口不写死：`portalSwitch.js` 优先读 `VITE_SMARTOPS_ADMIN_PORT` / `VITE_SMARTOPS_USER_PORT`，其次按 hostname 推导；`currentPortal()` 以服务自己声明的 `window.__SMARTOPS_PORTAL_SURFACE__` 为准，端口只作为兜底。

## 4. 维护约束

1. **两套代理必须指向同一后端**，否则会话会分裂。管理员层通过 `vite.shared.mjs` 读取 `SMARTOPS_BACKEND_ORIGIN`。
2. **管理员层的 SPA 回退只回退 `admin.html`**，且必须放过 `/api`、`/ws`、`/@`、`/src/`、`/node_modules/` 与静态资源，否则登录与会话请求会拿到 HTML。见 `vite.admin-fallback.mjs` 与 `frontend/test/admin-service-fallback.test.mjs`。
3. **用户层 `vite.config.js` 中的内联 `/ws` 代理声明不能删**：`frontend/test/session-security.test.mjs` 用它守卫「终端开发流量与已认证同源」这一安全不变量。
4. 管理员层样式仍以 `.admin-surface` 为作用域，`--admin-*` 令牌不定义在 `:root`，因此不会渗透到用户层。

## 5. 回归测试

| 测试 | 覆盖 |
| --- | --- |
| `test/admin-service-contract.test.mjs` | 端口固定、独立入口、用户层 5173 与 `/ws` 不变量、管理员层路由不含用户层路由、客户端不自行授权 |
| `test/admin-service-fallback.test.mjs` | 回退只服务管理员入口，且不吞 `/api`、`/ws` 与静态资源 |
| `test/admin-portal-surface.browser.mjs` | 管理员层服务四类路径都停在管理员门户，无控制台错误 |
| `test/user-portal-default.browser.mjs` | 用户层仍默认落在「用户层」 |
| `test/user-layer-isolation.browser.mjs` | 用户层页面上不存在 `.admin-surface`，`--admin-*` 未泄漏到 `:root` |
| `test/admin-console-visual.browser.mjs` | 真实登录后逐页截图与几何/令牌核验（深浅色、375px） |

## 6. 启动脚本

- 只启动管理员层：`powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-admin-frontend.ps1`
- 两个前端一起启动：`.\scripts\windows\start-dev.ps1`（同时拉起 5173 与 5174）
- 停止：`.\scripts\windows\stop-all-local.ps1`（已把 5174 纳入端口检查）
