// 管理员层独立服务（5174）的回退逻辑回归测试。
//
// 背景：管理员层用 admin.html 作为入口，需要对 SPA 路由做回退；
// 但这个回退**不能**吞掉 /api 与 /ws，否则管理员层的登录、会话与
// 终端隧道都会拿到一份 HTML 而不是后端响应。
//
// 这里只验证路由判定，不启动 Vite。

import assert from 'node:assert/strict'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { adminHtmlFallback, RESERVED_PREFIXES } from '../vite.admin-fallback.mjs'

const frontendRoot = fileURLToPath(new URL('..', import.meta.url))

// 构造一个最小 server 替身，捕获插件注册的中间件。
function mount() {
    const handlers = []
    const server = {
        middlewares: { use: handler => handlers.push(handler) },
        transformIndexHtml: async (_url, html) => html
    }
    adminHtmlFallback({ SMARTOPS_ADMIN_ROOT: frontendRoot }).configureServer(server)
    return handlers[0]
}

function call(handler, url, method = 'GET') {
    return new Promise(resolve => {
        const request = { url, originalUrl: url, method }
        const response = {
            statusCode: 0,
            headers: {},
            body: undefined,
            setHeader(name, value) { this.headers[name.toLowerCase()] = value },
            end(body) { this.body = body; resolve({ served: true, response: this }) }
        }
        const finished = handler(request, response, () => resolve({ served: false, response }))
        if (finished?.catch) finished.catch(() => resolve({ served: false, response }))
    })
}

test('administrator service proxies API and websocket paths instead of serving HTML', async () => {
    const handler = mount()
    for (const url of ['/api/auth/session', '/api/auth/human-verification?action=login', '/ws/operations/terminal']) {
        const outcome = await call(handler, url)
        assert.equal(outcome.served, false, `${url} must fall through to the proxy`)
    }
})

test('administrator service keeps Vite internal and static asset paths out of the fallback', async () => {
    const handler = mount()
    for (const url of ['/@vite/client', '/src/admin-main.js', '/node_modules/.vite/deps/vue.js', '/favicon.svg']) {
        const outcome = await call(handler, url)
        assert.equal(outcome.served, false, `${url} must not be answered by the HTML fallback`)
    }
})

test('administrator service serves the administrator entry for portal routes', async () => {
    const handler = mount()
    for (const url of ['/', '/login', '/admin', '/admin/users', '/account/security']) {
        const outcome = await call(handler, url)
        assert.equal(outcome.served, true, `${url} must be answered by the HTML fallback`)
        assert.match(outcome.response.body, /admin-main\.js/, `${url} must serve the administrator entry`)
    }
})

test('administrator fallback never answers non-GET requests', async () => {
    const handler = mount()
    for (const method of ['POST', 'PUT', 'DELETE']) {
        const outcome = await call(handler, '/api/auth/login', method)
        assert.equal(outcome.served, false, `${method} must not be answered by the HTML fallback`)
    }
})

test('reserved prefixes cover every path family owned by the proxy or Vite', async () => {
    assert.deepEqual(RESERVED_PREFIXES, ['/api', '/ws', '/@', '/node_modules/', '/src/'])
})
