import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

// 通用门户 HTML 回退：每个平级门户（enterprise/audit/command/open）由独立 Vite 服务提供，
// 入口是 <portal>.html。Vite 内建 SPA 回退固定指向 index.html，因此这里为每个门户补一个
// 只作用于本服务的回退：所有非资源请求都返回并转换 <portal>.html。
//
// /api、/ws 必须让给 server.proxy，否则登录、会话与终端隧道会被回退吞掉。
const RESERVED_PREFIXES = ['/api', '/ws', '/@', '/node_modules/', '/src/']

export { RESERVED_PREFIXES }

export function portalHtmlFallback(portalId, environment = process.env) {
    const entryName = `${portalId}.html`
    return {
        name: `smartops-${portalId}-html-fallback`,
        apply: 'serve',
        configureServer(server) {
            const entry = resolve(environment[`SMARTOPS_${portalId.toUpperCase()}_ROOT`] || process.cwd(), entryName)
            server.middlewares.use(async (request, response, next) => {
                const method = request.method || 'GET'
                if (method !== 'GET' && method !== 'HEAD') return next()
                const url = request.originalUrl || request.url || '/'
                if (RESERVED_PREFIXES.some(prefix => url.startsWith(prefix))) return next()
                const path = url.split('?')[0]
                if (/\.[a-zA-Z0-9]+$/.test(path)) return next()
                try {
                    const html = await readFile(entry, 'utf8')
                    const transformed = await server.transformIndexHtml(url, html)
                    response.statusCode = 200
                    response.setHeader('Content-Type', 'text/html; charset=utf-8')
                    response.setHeader('Cache-Control', 'no-store')
                    response.end(transformed)
                } catch (failure) {
                    // 明确失败，不放行到 Vite 内建回退，避免静默返回用户层 index.html。
                    response.statusCode = 500
                    response.setHeader('Content-Type', 'text/plain; charset=utf-8')
                    response.end(`${portalId} 入口渲染失败：${failure.message}\n入口文件：${entry}\n`)
                }
            })
        }
    }
}
