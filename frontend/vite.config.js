import {
    defineConfig
} from 'vite'

import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

function manualChunks(id) {
    if (!id.includes('node_modules')) {
        return undefined
    }

    const normalizedId = id.replaceAll('\\', '/')
    if (normalizedId.includes('/three/')) {
        return 'vendor-three'
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
        // 用户层入口，端口与代理语义保持不变。
        // 管理员层入口在 vite.config.admin.mjs（默认 5174），两者指向同一后端。
        proxy: {
            '/ws': {
                target: 'http://127.0.0.1:8080',
                ws: true
            },
            '/api': {
                target: 'http://127.0.0.1:8080',
                changeOrigin: true
            }
        }
    }
})
