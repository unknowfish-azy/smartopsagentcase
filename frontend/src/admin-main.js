// 管理员层应用入口（127.0.0.1:5174）。
//
// 与用户层入口 src/main.js 保持一致的初始化顺序（样式、主题、Pinia、路由），
// 只把路由换成管理员层专用路由表，并在首次导航时把门户锁定为 admin，
// 这样管理员层服务上打开根路径就直接落在管理员层登录页。
//
// 用户层入口 src/main.js 与 5173 端口一律不变。

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@guochenwang/lggc/dist/lggc.min.css'

import App from './App.vue'
import router from './router/admin.js'

import './assets/styles/variables.css'
import './assets/styles/global.css'
import { initializeTheme } from './theme.js'

// 管理员层服务只提供管理员层入口，标记后由路由守卫把 ?portal=admin 补到登录页。
window.__SMARTOPS_PORTAL_SURFACE__ = 'admin'
document.title = '智维Agent · 管理员层'

initializeTheme()
const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
