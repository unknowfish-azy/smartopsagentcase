import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

// Vite 的 dev server 内建 SPA 回退固定指向 index.html。管理员层服务的对等入口是
// admin.html，因此这里补一个只作用于本服务的回退：所有非资源请求都返回并转换
// admin.html。它不改变 Vite 的资源处理链路，也不影响用户层 5173 服务。
//
// 注意：/api 与 /ws 必须让给 server.proxy，否则登录、会话与终端隧道会被
// 这个回退吞掉，前端只会拿到一份 HTML 而不是后端响应。
const RESERVED_PREFIXES = ['/api', '/ws', '/@', '/node_modules/', '/src/']

// 供回归测试断言：这些前缀必须交给 server.proxy / Vite 自身处理。
export { RESERVED_PREFIXES }

export function adminHtmlFallback(environment = process.env) {
    return {
        name: 'smartops-admin-html-fallback',
        apply: 'serve',
        configureServer(server) {
            const entry = resolve(environment.SMARTOPS_ADMIN_ROOT || process.cwd(), 'admin.html')
            server.middlewares.use(async (request, response, next) => {
                const method = request.method || 'GET'
                if (method !== 'GET' && method !== 'HEAD') {
                    return next()
                }
                const url = request.originalUrl || request.url || '/'
                if (RESERVED_PREFIXES.some(prefix => url.startsWith(prefix))) {
                    return next()
                }
                const path = url.split('?')[0]
                if (/\.[a-zA-Z0-9]+$/.test(path)) {
                    return next()
                }
                try {
                    const html = await readFile(entry, 'utf8')
                    const transformed = await server.transformIndexHtml(url, html)
                    response.statusCode = 200
                    response.setHeader('Content-Type', 'text/html; charset=utf-8')
                    response.setHeader('Cache-Control', 'no-store')
                    response.end(transformed)
                } catch (failure) {
                    // 明确失败，不放行到 Vite 内建回退：否则管理员层会静默返回
                    // 用户层 index.html，把一个配置错误伪装成"页面能打开"。
                    response.statusCode = 500
                    response.setHeader('Content-Type', 'text/plain; charset=utf-8')
                    response.end(`管理员层入口渲染失败：${failure.message}\n入口文件：${entry}\n`)
                }
            })
        }
    }
}
