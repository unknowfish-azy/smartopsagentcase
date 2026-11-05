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
        }
    }
}

// 用户层与管理员层共用的分包策略。
// zrender 是 echarts 的渲染底座，单独拆出可让两包并行加载、独立缓存，
// 避免单个 vendor 包过大。
export function manualChunks(id) {
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
