import {
    defineConfig
} from 'vite'

import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { backendOrigin, devProxy, manualChunks } from './vite.shared.mjs'

export default defineConfig({
    plugins: [
        vue(),
        Components({
            resolvers: [ElementPlusResolver()]
        })
    ],

    build: {
        rollupOptions: {
            output: {
                manualChunks
            }
        }
    },

    server: {
        host: true,
        port: 5173,
        strictPort: true,
        // 开发期对所有响应加 no-store 头，强制浏览器每次重新拉取，
        // 避免 CSS/JS 改动后浏览器仍用磁盘缓存导致页面不更新。
        headers: {
            'Cache-Control': 'no-store, no-cache, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        },
        // 用户层入口端口保持 5173；代理与管理员层共用 vite.shared.mjs，避免两端口语义分裂。
        proxy: devProxy(backendOrigin())
    }
})
