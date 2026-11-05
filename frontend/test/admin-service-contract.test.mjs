// 管理员层独立服务的配置契约回归测试。
//
// 锁定的不变量：
//   1. 管理员层入口固定在 5174，且 strictPort，不与用户层共享端口；
//   2. 管理员层有独立 HTML 入口与独立路由表；
//   3. 用户层入口仍然是 5173 且仍声明 /ws 与 /api 代理（安全不变量）；
//   4. 管理员层路由表不注册任何用户层路由（物理隔离两个门户）。

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = name => readFile(new URL(`../${name}`, import.meta.url), 'utf8')

test('administrator service is pinned to its own port with strictPort', async () => {
    const config = await read('vite.config.admin.mjs')
    assert.match(config, /port:\s*Number\(process\.env\.SMARTOPS_ADMIN_PORT\s*\|\|\s*5174\)/)
    assert.match(config, /strictPort:\s*true/)
    assert.match(config, /host:\s*'127\.0\.0\.1'/)
})

test('administrator service has its own html entry and application entry', async () => {
    const config = await read('vite.config.admin.mjs')
    assert.match(config, /admin\.html/)
    const html = await read('admin.html')
    assert.match(html, /\/src\/admin-main\.js/)
    assert.match(html, /智维Agent · 管理员层/)
    const entry = await read('src/admin-main.js')
    assert.match(entry, /from '\.\/router\/admin\.js'/)
})

test('user layer keeps its own port and the same-origin proxy invariant', async () => {
    const config = await read('vite.config.js')
    const shared = await read('vite.shared.mjs')
    assert.match(config, /port:\s*5173/)
    // 与 test/session-security.test.mjs 相同的安全不变量：同源代理 + 凭据。
    assert.match(config, /proxy:\s*devProxy\(backendOrigin\(\)\)/)
    assert.match(shared, /['"]\/ws['"]\s*:\s*\{\s*target,\s*ws:\s*true\s*\}/)
})

test('administrator router registers no user-layer routes', async () => {
    const router = await read('src/router/admin.js')
    for (const forbidden of ['ChatView', 'DashboardView', 'MainLayout', 'ServerListView', 'KnowledgeView', 'view:actions']) {
        assert.doesNotMatch(router, new RegExp(forbidden), `${forbidden} must not be registered on the administrator surface`)
    }
    assert.match(router, /AdminLayout\.vue/)
})

test('administrator router never grants the portal from the client side', async () => {
    const router = await read('src/router/admin.js')
    // 入口选择不是授权：必须继续走服务端会话判定。
    assert.match(router, /sessionRouteDecision/)
    assert.match(router, /await loadSession\(/)
    assert.doesNotMatch(router, /localStorage\.getItem\('smartops_preview_auth'\)/)
})
