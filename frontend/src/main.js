import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@guochenwang/lggc/dist/lggc.min.css'

import App from './App.vue'
import router from './router'

import './assets/styles/variables.css'
import './assets/styles/global.css'
import { initializeTheme } from './theme.js'

initializeTheme()
const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
