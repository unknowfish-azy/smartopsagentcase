// 开放生态层专用前端服务（127.0.0.1:5178）。平级门户之一，独立端口与构建产物。
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { backendOrigin, devProxy, manualChunks } from './vite.shared.mjs'
import { portalHtmlFallback } from './vite.portal-fallback.mjs'

export default defineConfig({
    // 每个门户独立依赖缓存：多门户并行 dev 时避免争抢 node_modules/.vite/deps（EPERM）。
    cacheDir: 'node_modules/.vite/open',
    plugins: [
        vue(),
        Components({ resolvers: [ElementPlusResolver()] }),
        portalHtmlFallback('open')
    ],
    build: {
        outDir: 'dist-open',
        rollupOptions: {
            input: { open: resolve(import.meta.dirname, 'open.html') },
            output: { manualChunks }
        }
    },
    server: {
        host: '127.0.0.1',
        strictPort: true,
        port: Number(process.env.SMARTOPS_OPEN_PORT || 5178),
        proxy: devProxy(backendOrigin())
    }
})
