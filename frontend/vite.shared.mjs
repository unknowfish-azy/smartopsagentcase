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
            changeOrigin: true
        }
    }
}
