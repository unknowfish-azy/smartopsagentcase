<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Sunny, Moon } from '@element-plus/icons-vue'
import { currentSession, logoutSession } from '../security/session.js'
import { resolvePortalSwitch } from '../security/portalSwitch.js'
import { portalSpec } from '../security/portalCatalog.js'
import { isDarkTheme, setThemeMode } from '../theme.js'

const props = defineProps({ portal: { type: String, required: true } })
const router = useRouter()
const spec = computed(() => portalSpec(props.portal))
const user = computed(() => currentSession.value)

onMounted(() => {
  // 若本服务被错误地以其它门户会话进入，强制回登录；正常由路由守卫拦截，这里兜底。
  if (user.value && user.value.portal !== props.portal) {
    const decision = resolvePortalSwitch(props.portal, { query: { reason: 'denied' } })
    if (decision?.crossOrigin) window.location.assign(decision.url)
    else router.replace({ path: '/login', query: { portal: props.portal, reason: 'denied' } })
  }
})

function leave() {
  const decision = resolvePortalSwitch('user')
  if (decision?.crossOrigin) window.location.assign(decision.url)
  else router.push({ path: '/' })
}
async function logout() {
  await logoutSession()
  const decision = resolvePortalSwitch(props.portal)
  router.push(decision?.crossOrigin ? { path: '/' } : { path: '/login', query: { portal: props.portal } })
}
function toggleTheme() { setThemeMode(isDarkTheme.value ? 'light' : 'dark') }
</script>

<template>
  <div class="portal-scaffold" :class="`portal-scaffold--${portal}`">
    <aside class="portal-scaffold__sidebar">
      <div class="portal-scaffold__brand">
        <div class="portal-scaffold__logo" aria-hidden="true">智</div>
        <div>
          <div class="portal-scaffold__brand-name">SmartOpsAgent</div>
          <div class="portal-scaffold__badge">{{ spec?.label }}</div>
        </div>
      </div>
      <nav class="portal-scaffold__nav" aria-label="门户导航">
        <router-link :to="`/${portal}`" class="portal-scaffold__nav-item is-active">门户首页</router-link>
        <span class="portal-scaffold__nav-item is-placeholder" title="规划中">
          <span class="portal-scaffold__dot" /> 规划中模块
          <em>建设中</em>
        </span>
      </nav>
      <p class="portal-scaffold__purpose">{{ spec?.purpose }}</p>
    </aside>

    <div class="portal-scaffold__main">
      <header class="portal-scaffold__topbar">
        <button class="portal-scaffold__back" type="button" @click="leave">
          <ArrowLeft /><span>返回用户层</span>
        </button>
        <div class="portal-scaffold__spacer" />
        <button class="portal-scaffold__icon" type="button" :aria-label="isDarkTheme ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          <Sunny v-if="isDarkTheme" /><Moon v-else />
        </button>
        <div class="portal-scaffold__user">
          <span class="portal-scaffold__user-name">{{ user?.username || '未登录' }}</span>
          <button type="button" class="portal-scaffold__logout" @click="logout">退出登录</button>
        </div>
      </header>
      <main class="portal-scaffold__content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.portal-scaffold { display: flex; min-height: 100vh; background: var(--smart-bg, #0b1020); color: var(--smart-text, #e6e9f2); }
.portal-scaffold__sidebar { width: 248px; flex: 0 0 248px; padding: 24px 18px; background: rgba(255,255,255,0.03); border-right: 1px solid rgba(255,255,255,0.08); display: flex; flex-direction: column; gap: 18px; }
.portal-scaffold__brand { display: flex; align-items: center; gap: 12px; }
.portal-scaffold__logo { width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center; background: linear-gradient(135deg, #4f8cff, #7c5cff); color: #fff; font-weight: 700; font-size: 18px; }
.portal-scaffold__brand-name { font-size: 15px; font-weight: 600; letter-spacing: 0.5px; }
.portal-scaffold__badge { font-size: 12px; color: var(--smart-muted, #9aa3b8); margin-top: 2px; }
.portal-scaffold__nav { display: flex; flex-direction: column; gap: 6px; }
.portal-scaffold__nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; color: var(--smart-muted, #9aa3b8); text-decoration: none; font-size: 14px; }
.portal-scaffold__nav-item.is-active { background: rgba(79,140,255,0.15); color: #cfe0ff; }
.portal-scaffold__nav-item.is-placeholder { opacity: 0.55; cursor: default; }
.portal-scaffold__nav-item em { margin-left: auto; font-style: normal; font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(255,255,255,0.08); }
.portal-scaffold__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--smart-muted, #9aa3b8); }
.portal-scaffold__purpose { margin-top: auto; font-size: 12px; line-height: 1.7; color: var(--smart-muted, #7e869c); }
.portal-scaffold__main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.portal-scaffold__topbar { height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 20px; border-bottom: 1px solid rgba(255,255,255,0.08); }
.portal-scaffold__back { display: inline-flex; align-items: center; gap: 6px; background: transparent; color: var(--smart-muted, #9aa3b8); border: 1px solid rgba(255,255,255,0.12); padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; }
.portal-scaffold__back:hover { color: #fff; border-color: rgba(255,255,255,0.3); }
.portal-scaffold__spacer { flex: 1; }
.portal-scaffold__icon { background: transparent; border: none; color: var(--smart-muted, #9aa3b8); cursor: pointer; padding: 6px; }
.portal-scaffold__icon:hover { color: #fff; }
.portal-scaffold__user { display: flex; align-items: center; gap: 12px; }
.portal-scaffold__user-name { font-size: 13px; color: var(--smart-text, #e6e9f2); }
.portal-scaffold__logout { background: transparent; color: #ff9a9a; border: 1px solid rgba(255,154,154,0.4); padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.portal-scaffold__logout:hover { background: rgba(255,154,154,0.12); }
.portal-scaffold__content { flex: 1; overflow: auto; padding: 24px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
