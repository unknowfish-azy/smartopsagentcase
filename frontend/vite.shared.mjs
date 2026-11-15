// 用户层与管理员层共用的开发服务器代理配置。
// 两个入口必须指向同一后端，否则会话与 CSRF 会分裂。

export function backendOrigin(environment = process.env) {
    const configured = environment.SMARTOPS_BACKEND_ORIGIN || environment.VITE_BACKEND_ORIGIN
    return configured && configured.trim() ? configured.trim().replace(/\/+$/, '') : 'http://127.0.0.1:8080'
}

export function devProxy(target) {
    return {
        '/ws': {
            target,
            ws: true
        },
        '/api': {
            target,
            changeOrigin: true
        },
        '/ai': {
            target: 'http://127.0.0.1:8001',
            changeOrigin: true,
            // 去掉 /ai 前缀：ai-service 的路由是 /api/chat/stream
            rewrite: path => path.replace(/^\/ai/, '')
        },
        // 知识服务（Python FastAPI，端口 8002）的空间场只读端点
        '/ks': {
            target: 'http://127.0.0.1:8002',
            changeOrigin: true,
            // /ks/api/knowledge/evidence-refs → /api/knowledge/evidence-refs
            rewrite: path => path.replace(/^\/ks/, '')
        }
    }
}

// 用户层与管理员层共用的分包策略。
// zrender 是 echarts 的渲染底座，单独拆出可让两包并行加载、独立缓存，
// 避免单个 vendor 包过大。
export function manualChunks(id) {
    // commonjsHelpers 是被多个 CommonJS 包（@xterm、dayjs 等）共享的辅助模块。
    // 必须固定到独立的公共小 chunk：否则 Rollup 会把它绑进 vendor-terminal，
    // 导致 base（element-plus/dayjs，被登录等所有视图共享）静态依赖 71KB 的 @xterm，
    // 登录首屏被迫下载整个终端包（Lighthouse unused-javascript 约 300ms）。
    if (id.includes('commonjsHelpers')) {
        return 'vendor-helpers'
    }
    if (!id.includes('node_modules')) {
        return undefined
    }

    const normalizedId = id.replaceAll('\\', '/')
    if (normalizedId.includes('/three/')) {
        return 'vendor-three'
    }
    if (normalizedId.includes('/zrender/')) {
        return 'vendor-zrender'
    }
    if (normalizedId.includes('/echarts/')) {
        return 'vendor-echarts'
    }
    if (normalizedId.includes('/@xterm/')) {
        return 'vendor-terminal'
    }
    if (normalizedId.includes('/vue/') || normalizedId.includes('/vue-router/') || normalizedId.includes('/pinia/')) {
        return 'vendor-vue'
    }
    if (normalizedId.includes('/axios/') || normalizedId.includes('/yaml/')) {
        return 'vendor-utils'
    }

    return undefined
}
