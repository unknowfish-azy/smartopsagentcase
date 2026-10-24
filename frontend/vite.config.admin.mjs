// 管理员层专用前端服务。
//
// 为什么单独起服务：用户层与管理员层原本共用 5173 与同一个 SPA 实例，
// 入口靠 ?portal=admin 区分。管理员层迁到独立端口后，两个入口各自的
// 地址、书签与书签栏不再互相占用，也不再与用户层抢同一个端口。
//
// 用户层仍然由 vite.config.js 提供，端口 5173 与视觉理念一律不变。

import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { backendOrigin, devProxy } from './vite.shared.mjs'
import { adminHtmlFallback } from './vite.admin-fallback.mjs'

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
        }),
        adminHtmlFallback()
    ],

    build: {
        outDir: 'dist-admin',
        rollupOptions: {
            input: {
                admin: resolve(import.meta.dirname, 'admin.html')
            },
            output: {
                manualChunks
            }
        }
    },

    server: {
        host: '127.0.0.1',
        strictPort: true,
        port: Number(process.env.SMARTOPS_ADMIN_PORT || 5174),
        proxy: devProxy(backendOrigin())
    }
})
