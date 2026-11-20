// 审计合规层专用前端服务（127.0.0.1:5176）。平级门户之一，独立端口与构建产物。
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { backendOrigin, devProxy, manualChunks } from './vite.shared.mjs'
import { portalHtmlFallback } from './vite.portal-fallback.mjs'

export default defineConfig({
    // 每个门户独立依赖缓存：多门户并行 dev 时避免争抢 node_modules/.vite/deps（EPERM）。
    cacheDir: 'node_modules/.vite/audit',
    plugins: [
        vue(),
        Components({ resolvers: [ElementPlusResolver()] }),
        portalHtmlFallback('audit')
    ],
    build: {
        outDir: 'dist-audit',
        rollupOptions: {
            input: { audit: resolve(import.meta.dirname, 'audit.html') },
            output: { manualChunks }
        }
    },
    server: {
        host: '127.0.0.1',
        strictPort: true,
        port: Number(process.env.SMARTOPS_AUDIT_PORT || 5176),
        proxy: devProxy(backendOrigin())
    }
})
