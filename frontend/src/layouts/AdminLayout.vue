<template>
  <div class="admin-surface admin-layout" :class="{ 'is-collapsed': collapsed }">
    <a class="admin-skip" href="#admin-content">跳转到内容</a>

    <aside class="admin-sidebar">
      <div class="admin-sidebar__brand">
        <span class="admin-brand-mark">智</span>
        <span v-show="!collapsed" class="admin-brand-name">智维Agent</span>
        <small v-show="!collapsed">ADMIN</small>
      </div>
      <nav aria-label="管理导航" class="admin-sidebar__nav">
        <section v-for="group in navigation" :key="group.label" class="admin-navigation-group">
          <h2 v-show="!collapsed">{{ group.label }}</h2>
          <RouterLink v-for="item in group.items" :key="item.path" :to="item.path" class="admin-nav-item" :class="{ 'is-current': route.path === item.path }" :title="collapsed ? item.label : undefined" :aria-current="route.path === item.path ? 'page' : undefined">
            <component :is="navigationIcons[group.label]" class="admin-nav-symbol" aria-hidden="true" />
            <span v-show="!collapsed" class="admin-nav-label">{{ item.label }}</span>
          </RouterLink>
        </section>
      </nav>
    </aside>

    <div class="admin-main">
      <header class="admin-header">
        <div class="admin-header__left">
          <button type="button" class="admin-header-btn" :aria-label="collapsed ? '展开侧栏' : '折叠侧栏'" @click="collapsed = !collapsed"><svg v-if="collapsed" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg><svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>
          <nav class="admin-breadcrumb" aria-label="面包屑">
            <template v-if="crumb"><span>{{ crumb.group }}</span><span class="admin-breadcrumb-sep">/</span><span class="admin-breadcrumb-current">{{ crumb.item }}</span></template>
            <template v-else><span>管理总览</span></template>
          </nav>
        </div>
        <div class="admin-header__toolbar">
          <CommandPalette :entries="discoveryEntries" />
          <button type="button" class="admin-header-btn" :title="isDarkTheme ? '切到浅色' : '切到深色'" :aria-label="isDarkTheme ? '切到浅色' : '切到深色'" @click="toggleDark"><svg v-if="isDarkTheme" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12.5A8 8 0 1 1 11.5 4 6.5 6.5 0 0 0 20 12.5Z"/></svg></button>
          <button type="button" class="admin-header-btn" :title="fullscreen ? '退出全屏' : '全屏'" :aria-label="fullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen"><svg v-if="fullscreen" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8h5V3M21 8h-5V3M3 16h5v5M21 16h-5v5"/></svg><svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/></svg></button>
          <button type="button" class="admin-header-btn" title="刷新" aria-label="刷新" @click="refresh"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4"/></svg></button>
          <div class="admin-user" ref="userMenuRoot">
            <button type="button" class="admin-user-trigger" :aria-expanded="userMenuOpen" aria-haspopup="menu" aria-label="账户菜单" @click="userMenuOpen = !userMenuOpen">
              <span class="admin-user-avatar">{{ avatarChar }}</span>
              <span class="admin-user-name">{{ currentSession?.username }}</span>
              <span class="admin-badge admin-user-badge">管理层</span>
              <span class="admin-user-caret" aria-hidden="true">▾</span>
            </button>
            <div v-show="userMenuOpen" class="admin-user-menu">
              <RouterLink to="/account/security" @click="userMenuOpen = false">账户安全</RouterLink>
              <button type="button" :disabled="leaving" @click="leave('user')">返回用户层（重新登录）</button>
              <button type="button" :disabled="leaving" @click="leave('admin')">退出登录</button>
            </div>
          </div>
        </div>
      </header>

      <AdminTabs />

      <div class="admin-workspace">
        <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
        <main id="admin-content" class="admin-content" tabindex="-1"><RouterView /></main>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Grid, User, Setting, Lock, Connection } from '@element-plus/icons-vue'
import CommandPalette from '../components/navigation/CommandPalette.vue'
import AdminTabs from '../components/admin/AdminTabs.vue'
import { adminNavigation, adminBreadcrumb } from '../adminNav.js'
import { currentSession, logoutSession } from '../security/session.js'
import { resolvePortalSwitch } from '../security/portalSwitch.js'
import { themeMode, isDarkTheme, setThemeMode } from '../theme.js'
import '../assets/styles/admin.css'
const router = useRouter()
const route = useRoute()
const navigation = adminNavigation
const navigationIcons = { '管理工作台': Grid, '身份与空间': User, '系统管理': Setting, '安全与审计': Lock, '服务与部署': Connection }
const discoveryEntries = adminNavigation.flatMap(group => group.items.map(item => ({ to: item.path, title: item.label, label: item.path, group: group.label })))
const collapsed = ref(false)
const fullscreen = ref(false)
const leaving = ref(false)
const error = ref('')
const userMenuOpen = ref(false)
const userMenuRoot = ref(null)

const crumb = computed(() => adminBreadcrumb(route.path))
const avatarChar = computed(() => (currentSession.value?.username || 'A').charAt(0).toUpperCase())

// 用户菜单：点击开关。曾用纯 :hover 实现，芯片与菜单之间有 8px 死区，
// 鼠标移向菜单时中途触发 mouseleave → 菜单闪烁消失、点不中退出登录。
// 现在打开状态由 userMenuOpen 单一数据源驱动，鼠标怎么移动都不会闪掉。
function onDocumentPointerdown(event) {
  if (!userMenuOpen.value) return
  if (userMenuRoot.value && !userMenuRoot.value.contains(event.target)) userMenuOpen.value = false
}
function onDocumentKeydown(event) {
  if (event.key !== 'Escape' || !userMenuOpen.value) return
  userMenuOpen.value = false
  userMenuRoot.value?.querySelector('.admin-user-trigger')?.focus()
}
watch(() => route.fullPath, () => { userMenuOpen.value = false })
onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerdown, true)
  document.addEventListener('keydown', onDocumentKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerdown, true)
  document.removeEventListener('keydown', onDocumentKeydown)
})

function toggleDark() { setThemeMode(isDarkTheme.value ? 'light' : 'dark') }
async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen()
    fullscreen.value = Boolean(document.fullscreenElement)
  } catch { /* 全屏不可用时静默忽略 */ }
}
function refresh() { router.go(0) }
async function leave(portal) {
  if (leaving.value) return
  leaving.value = true
  userMenuOpen.value = false
  error.value = ''
  try {
    await logoutSession()
    const decision = resolvePortalSwitch(portal)
    if (decision?.crossOrigin) { window.location.assign(decision.url); return }
    await router.replace({ path: '/login', query: { portal } })
  } catch (failure) { error.value = failure.message || '退出失败，请重试' }
  finally { leaving.value = false }
}
</script>

<style scoped>
.admin-sidebar { border-top:2px solid var(--admin-primary, var(--smart-primary-strong)); }
.admin-nav-symbol { width:18px; height:18px; flex-shrink:0; }
.admin-nav-item { min-height:44px; position:relative; transition:background 160ms, color 160ms; }
.admin-nav-item.is-current { box-shadow:inset 2px 0 currentColor; }
.admin-navigation-group h2 { display:flex; align-items:center; gap:10px; letter-spacing:.12em; }
.admin-navigation-group h2::after { content:''; height:1px; flex:1; background:var(--admin-border); }
.admin-sidebar__brand { border-bottom:1px solid var(--admin-border); margin-bottom:14px; }
@media(prefers-reduced-motion:reduce) { .admin-nav-item { transition:none; } }
</style>
