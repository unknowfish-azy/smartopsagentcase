// 企业管理层应用入口（127.0.0.1:5175）。平级门户之一：
// 独立前端服务、独立路由表，与用户层/管理层共用同一后端与会话，登录时按 portal 鉴权。
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@guochenwang/lggc/dist/lggc.min.css'
import App from './App.vue'
import router from './router/enterprise.js'
import './assets/styles/variables.css'
import './assets/styles/global.css'
import { initializeTheme } from './theme.js'

window.__SMARTOPS_PORTAL_SURFACE__ = 'enterprise'
document.title = '智维Agent · 企业管理层'
initializeTheme()
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
