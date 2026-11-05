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
        host: '127.0.0.1',
        port: 5173,
        // 用户层入口端口保持 5173；代理与管理员层共用 vite.shared.mjs，避免两端口语义分裂。
        proxy: devProxy(backendOrigin())
    }
})
