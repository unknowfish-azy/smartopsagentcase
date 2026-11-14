<template>
  <StellarOceanProvider :state="whaleState">
    <div class="app-layout" :data-visual-mode="visualMode" :class="{ 'app-layout--tools': isToolsPage, 'app-layout--liquid': !isToolsPage, 'app-layout--sidebar-collapsed': appStore.sidebarCollapsed, 'app-layout--chat': route.path === '/chat', 'app-layout--lightweight': isLightweightVisualMode, 'app-layout--team': isTeamSpace, 'app-layout--admin-entry': currentRole === 'admin' }">
      <MilkyWay v-if="showEnhancedHomeVisuals" class="home-galaxy" :particle-size="0.45" :rotation-speed="0.3" :viewport-coverage="0.78" :center-x="0.36" mouse-influence />
      <CanvasAmbientField v-else-if="route.name === 'Dashboard'" />
      <MeteorShower v-if="showEnhancedHomeVisuals" />
      <ParticleWhale v-if="showEnhancedHomeVisuals && !personaPetActive" :placement="whalePlacement" :state="whaleState" />
      <CanvasParticleWhale v-if="!showEnhancedHomeVisuals && !isConnectionWorkspace && !personaPetActive" :placement="whalePlacement" :state="whaleState" />
      <LivingJellyfish v-if="!isConnectionWorkspace && visualMode === 'balanced'" class="app-jellyfish" :class="`app-jellyfish--${whalePlacement}`" :state="jellyfishState" ecosystem="protected" />
      <OpsSpiderPet v-if="!isTeamSpace && !isKnowledgeSpace" :state="opsSpiderState" :agent-state="whaleState" :compact="route.name === 'Connections'" @navigate="openOpsSpiderAction" />
      <PersonaPet v-if="personaPetStore.enabled && route.name !== 'AgentPersona'" />
      <button v-if="opsSpider.hidden && !isTeamSpace && !isKnowledgeSpace" class="spider-restore-control" type="button" aria-label="重新显示桌宠" title="重新显示桌宠" @click="opsSpider.show()">AI</button>
      <SmartInquiryDrawer v-if="!isTeamSpace" />

      <button class="sidebar-expand-control" type="button" aria-label="展开主菜单" title="展开主菜单" :aria-expanded="!appStore.sidebarCollapsed" @click="expandSidebar">
        <span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>
      </button>
      <button v-if="!appStore.sidebarCollapsed" class="sidebar-collapse-control" type="button" aria-label="收起主菜单" @click="collapseSidebar"><span aria-hidden="true">&lt;&lt;&lt;</span> 收起</button>

      <aside ref="navigationPanel" class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed, 'sidebar--expanded': !appStore.sidebarCollapsed, 'sidebar--mobile-open': appStore.mobileNavigationOpen, lggc: !isToolsPage }">
        <RouterLink class="wordmark" :to="isTeamSpace ? '/teams' : '/'"><span>SMARTOPS AGENT</span><small>{{ isTeamSpace ? '团队空间 · 成员与协作' : '个人空间 · 我的工作台' }}</small></RouterLink>
        <CommandPalette :entries="discoveryEntries" />
        <PersonalSystemNavigation
          v-if="!isTeamSpace"
          :groups="navigationGroups"
          :expanded-group-ids="appStore.expandedPersonalSystemGroups"
          :current-route-name="route.name?.toString()"
          :mobile="isNarrowViewport"
          :mobile-open="!isNarrowViewport || appStore.mobileNavigationOpen"
          :collapsed="appStore.sidebarCollapsed && !isToolsPage && !isNarrowViewport"
          :health-badges="navHealthBadges"
          @toggle-group="togglePersonalSystemGroup"
          @navigate="closeMobileNavigation"
          @close-mobile="closeMobileNavigation"
        />
        <nav v-if="isTeamSpace" class="section-nav" aria-label="团队空间导航"><p class="nav-label nav-label--system"><b>TEAM SPACE</b><small>团队协作</small></p><RouterLink to="/teams" @click="closeMobileNavigation"><span class="nav-copy"><b>WORKSPACES</b><small>我的团队与邀请</small></span></RouterLink><RouterLink v-if="route.params.teamId" :to="`/teams/${route.params.teamId}/workspace`" @click="closeMobileNavigation"><span class="nav-copy"><b>TEAM TOOLS</b><small>Agent · 工具 · 会话</small></span></RouterLink><p class="team-scope-note">团队资源与个人资源独立。</p></nav>
        <nav v-else class="section-nav" aria-label="System tools navigation">
          <p class="nav-label nav-label--system"><b>SYSTEM TOOLS</b><small>系统工具</small></p>
          <RouterLink v-for="item in systemNav" :key="item.to" :to="item.to" :aria-label="`${item.cn} / ${item.label}`" :title="`${item.cn} / ${item.label}`"><component :is="item.icon" class="nav-icon" aria-hidden="true" /><span class="nav-copy"><b>{{ item.label }}</b><small>{{ item.cn }}</small></span></RouterLink>
        </nav>
        <div class="system-status"><div><span>SESSION / 登录会话</span><strong>{{ currentSession?.username || '未登录' }}</strong></div><div><span>AGENT / 智能体</span><strong>{{ whaleState.toUpperCase() }}</strong></div><time>{{ currentTime }}</time><button class="persona-pet-toggle" type="button" :aria-pressed="personaPetStore.enabled" :title="personaPetStore.enabled ? '关闭数字人桌宠' : '开启数字人桌宠'" @click="personaPetStore.toggle()">{{ personaPetStore.enabled ? '桌宠·开' : '桌宠·关' }}</button></div>
      </aside>

      <div class="main-area">
        <header class="topbar" :class="{ lggc: !isToolsPage }">
          <button class="menu-button" type="button" aria-label="切换导航" :aria-expanded="appStore.mobileNavigationOpen" @click="toggleNavigation">目录</button>
          <p class="route-context">{{ routeContext }}</p>
          <div class="account-menu" ref="accountMenuRoot">
            <button type="button" class="account-menu-trigger" :aria-expanded="accountMenuOpen" aria-haspopup="menu" aria-label="个人账户菜单" @click="accountMenuOpen = !accountMenuOpen">
              <span class="account-menu-avatar" aria-hidden="true">{{ avatarChar }}</span>
              <span class="account-menu-name">个人账户</span>
              <span class="account-menu-caret" aria-hidden="true">▾</span>
            </button>
            <div v-show="accountMenuOpen" class="account-menu-dropdown">
              <div class="account-menu-header"><strong>{{ currentSession?.username || '未登录' }}</strong><small>{{ ROLE_LABELS[currentRole] }}</small></div>
              <RouterLink to="/account/security" @click="accountMenuOpen = false">账户安全</RouterLink>
              <button v-if="currentRole !== 'admin'" type="button" :disabled="leaving" @click="enterAdmin">管理入口（重新登录）</button>
              <button type="button" :disabled="leaving" @click="logout">退出登录</button>
            </div>
          </div>
          <div v-if="!isTeamSpace" class="tools-menu"><button type="button" class="tools-trigger" @click="toggleToolsMenu">TOOLS / 工具</button><div v-if="toolsOpen" class="tools-dropdown"><section v-for="group in toolGroups" :key="group.label"><strong>{{ group.label }}</strong><RouterLink v-for="tool in group.items" :key="tool.id" :to="`/tools/${tool.id}`" @click="toolsOpen = false">{{ tool.label }}</RouterLink></section></div></div>
          <div class="topbar-right">
            <div v-if="!isTeamSpace" class="ops-statusbar" aria-label="全局运行状态">
              <span class="ops-statusbar__item" title="当前运维空间">
                <span class="u-overline">ENV</span><b>{{ currentWorkspace.name }}</b>
              </span>
              <span class="ops-statusbar__sep" aria-hidden="true"></span>
              <RouterLink class="ops-statusbar__item" to="/sentinel/alerts" :title="inspectorOffline ? '告警数据不可用（未登录或后端未接入）' : '待处理 / 待审批 / 处置中告警'">
                <span class="u-overline">ALERTS</span><b :class="alertTone">{{ activeAlerts ?? '—' }}</b>
              </RouterLink>
              <span class="ops-statusbar__sep" aria-hidden="true"></span>
              <RouterLink class="ops-statusbar__item ops-statusbar__item--optional" to="/health" :title="inspectorOffline ? '健康数据不可用（未登录或后端未接入）' : '健康分（来自 Inspector 巡检摘要）'">
                <span class="u-overline">HEALTH</span><b :class="healthTone">{{ healthScore ?? '—' }}</b><template v-if="healthScore !== null">/100</template>
              </RouterLink>
              <span class="ops-statusbar__sep" aria-hidden="true"></span>
              <span class="ops-statusbar__item ops-statusbar__item--optional" title="当前智能体状态">
                <span class="u-overline">AGENT</span><b>{{ whaleState.toUpperCase() }}</b>
              </span>
            </div>
            <CompanionStatus /><label class="theme-control"><span class="theme-control__label">THEME</span><select aria-label="选择主题模式" :value="themeMode" @change="setThemeMode($event.target.value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label><label class="theme-control visual-mode-control"><span class="theme-control__label">VISUAL</span><select aria-label="选择视觉模式" :value="visualMode" @change="setVisualMode($event.target.value)"><option value="balanced">平衡视觉</option><option value="lightweight">轻量视觉</option><option value="reduced-motion">减少动效</option></select></label><time>{{ currentTime }}</time></div>
        </header>
        <div class="workspace-context" :class="{ 'workspace-context--team': isTeamSpace, 'workspace-context--admin': currentRole === 'admin' }"><SpaceSwitcher /><span class="workspace-context__scope">{{ currentRole === 'admin' ? 'ADMIN SCOPE' : isTeamSpace ? 'TEAM SCOPE' : 'PERSONAL SCOPE' }}</span><template v-if="!isTeamSpace"><select aria-label="当前运维空间" :value="appStore.currentWorkspaceId" @change="appStore.setCurrentWorkspace($event.target.value)"><option v-for="workspace in availableWorkspaces" :key="workspace.id" :value="workspace.id">{{ workspace.name }}</option></select><small>{{ currentWorkspace.label }}</small></template><small v-else>团队权限独立 · 不共享个人资料</small></div>
        <main id="main-content" class="content" tabindex="-1"><PageStepper v-if="!isTeamSpace" :route-name="route.name?.toString()" /><RouterView /></main>
      </div>
    </div>
  </StellarOceanProvider>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Connection } from '@element-plus/icons-vue'
import LivingJellyfish from '../components/common/LivingJellyfish.vue'
import StellarOceanProvider from '../components/common/StellarOceanProvider.vue'
import OpsSpiderPet from '../components/common/OpsSpiderPet.vue'
import CompanionStatus from '../components/companion/CompanionStatus.vue'
import CommandPalette from '../components/navigation/CommandPalette.vue'
import { navigationEntries } from '../navigation/navigationDiscovery.js'
import PersonalSystemNavigation from '../components/navigation/PersonalSystemNavigation.vue'
import SpaceSwitcher from '../components/navigation/SpaceSwitcher.vue'
import PageStepper from '../components/navigation/PageStepper.vue'
import MeteorShower from '../components/common/MeteorShower.vue'
import { useCompanionStore } from '../stores/companion.js'
import { useOpsSpiderStore } from '../stores/opsSpider.js'
import { usePersonaPetStore } from '../stores/personaPet.js'
import { useAiChatStore } from '../stores/aiChat.js'
import { currentSession, logoutSession } from '../security/session.js'
import { isAdminSession } from '../security/portalPolicy.js'
import { resolvedTheme, setThemeMode, themeMode } from '../theme.js'
import { hasExplicitVisualMode, isLightweightVisualMode, setVisualMode, visualMode, visualModeExplicit } from '../visual/visualMode.js'
import { personalSystemGroups } from '../navigation/personalSystemNavigation.js'
import { navHealthBadgeMap } from '../navigation/navigationHealth.js'
import { getVisibleNavigationGroups, ROLE_LABELS } from '../security/accessModel.js'
import { availableWorkspaces, useAppStore } from '../stores/app'
import { startGlobalOpsPolling, useGlobalOpsStatus } from '../composables/useGlobalOpsStatus'

const CanvasParticleWhale = defineAsyncComponent(() => import('../components/common/CanvasParticleWhale.vue'))
const CanvasAmbientField = defineAsyncComponent(() => import('../components/common/CanvasAmbientField.vue'))
const ParticleWhale = defineAsyncComponent({ loader: () => import('../components/common/ParticleWhale.vue'), loadingComponent: CanvasParticleWhale, errorComponent: CanvasParticleWhale })
const MilkyWay = defineAsyncComponent({ loader: () => import('../components/ui/milky-way.vue'), loadingComponent: CanvasAmbientField, errorComponent: CanvasAmbientField })
const SmartInquiryDrawer = defineAsyncComponent(() => import('../components/investigation/SmartInquiryDrawer.vue'))
const PersonaPet = defineAsyncComponent(() => import('../components/persona/PersonaPet.vue'))

const appStore = useAppStore()
const companion = useCompanionStore()
const opsSpider = useOpsSpiderStore()
const personaPetStore = usePersonaPetStore()
// 桌宠展开期间鲸让位（同屏 WebGL 主体 ≤ 1，PET.md §2）；收起小球与关闭后恢复
const personaPetActive = computed(() => personaPetStore.enabled && !personaPetStore.collapsed && route.name !== 'AgentPersona')
const aiChat = useAiChatStore()
aiChat.syncAccount()
let disconnectCompanion
const route = useRoute()
const isTeamSpace = computed(() => route.meta.space === 'team')
/* 知识库为长文阅读页，桌宠漫游会遮挡检索结果，因此该区不显示桌宠。 */
const isKnowledgeSpace = computed(() => route.path.startsWith('/knowledge'))
const router = useRouter()
const isConnectionWorkspace = computed(() => route.name === 'Connections')
const isToolsPage = computed(() => route.name === 'Tools')
const currentTime = ref('')
const toolsOpen = ref(false)
const accountMenuOpen = ref(false)
const accountMenuRoot = ref(null)
const leaving = ref(false)
const toolGroups = ref([])
let toolCatalogPromise
const isNarrowViewport = ref(false)
const navigationPanel = ref(null)
let timer
const setTheme = setThemeMode
// P0/P3 自适应视觉预算：工具层默认不加载 WebGL 装饰，首次访问即简约高性能；
// 只有用户显式选择过视觉档位（且为 balanced）才启用增强层。保留计算属性名与模板字符串契约。
const showEnhancedHomeVisuals = computed(() => route.name === 'Dashboard' && !isLightweightVisualMode.value && visualModeExplicit.value && hasExplicitVisualMode())

const systemNav = [
  { label: 'TRACE', cn: '执行轨迹', to: '/agent/trace', icon: Connection }
]
const whalePlacement = computed(() => route.meta.whalePlacement || (route.name === 'Knowledge' ? 'knowledge' : route.name === 'AgentCommandCenter' ? 'agent' : route.name?.toString().includes('Inspector') ? 'memory' : route.name?.toString().includes('Server') ? 'operations' : 'home'))
const whaleState = computed(() => companion.states.whale === 'DEGRADED' ? 'warning' : 'idle')
const jellyfishState = computed(() => companion.states.jellyfish === 'WAIT' ? 'idle' : 'observing')
const currentWorkspace = computed(() => availableWorkspaces.find(workspace => workspace.id === appStore.currentWorkspaceId) || availableWorkspaces[0])
const opsSpiderState = computed(() => companion.drawerOpen ? 'observing' : companion.attentionPolicy !== 'silent' ? 'warning' : 'idle')
const routeContext = computed(() => route.meta.section || route.name?.toString().replace(/([A-Z])/g, ' $1').trim().toUpperCase() || 'PERSONAL SYSTEM')
const currentRole = computed(() => isAdminSession(currentSession.value) ? 'admin' : 'operator')
const avatarChar = computed(() => (currentSession.value?.username || 'U').charAt(0).toUpperCase())
const navigationGroups = computed(() => getVisibleNavigationGroups(personalSystemGroups, currentRole.value))

/* 顶栏全局运行态：只读真实接口，失败显示「—」。 */
const { activeAlerts, healthScore, inspectorOffline } = useGlobalOpsStatus()
const alertTone = computed(() => activeAlerts.value === null ? 'is-muted' : activeAlerts.value > 0 ? 'is-danger' : 'is-success')
const healthTone = computed(() => healthScore.value === null ? 'is-muted' : healthScore.value >= 90 ? 'is-success' : healthScore.value >= 70 ? 'is-warning' : 'is-danger')

const discoveryEntries = computed(() => navigationEntries(navigationGroups.value))

const navHealthBadges = computed(() => navHealthBadgeMap(navigationGroups.value, {
  capabilities: companion.capabilities,
  activeFault: companion.context.faultEvent || null
}))

function updateTime() { currentTime.value = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short' }).format(new Date()) }
// 个人账户菜单：点击开关。对齐管理台 AdminLayout 用户菜单的修法——
// 旧管理台菜单是纯 :hover 实现，芯片与菜单之间有 8px 鼠标死区，移向菜单途中
// mouseleave → 菜单 display:none 复现 → 闪掉且点不中。这里打开状态由
// accountMenuOpen 单一数据源驱动，鼠标怎么移动都不闪；外点关闭（capture 阶段
// pointerdown + contains 判定）、Escape 关闭且焦点归位、路由切换关闭。
function onDocumentPointerdown(event) {
  if (!accountMenuOpen.value) return
  if (accountMenuRoot.value && !accountMenuRoot.value.contains(event.target)) accountMenuOpen.value = false
}
function onDocumentKeydown(event) {
  if (event.key !== 'Escape' || !accountMenuOpen.value) return
  accountMenuOpen.value = false
  accountMenuRoot.value?.querySelector('.account-menu-trigger')?.focus()
}
watch(() => route.fullPath, () => { accountMenuOpen.value = false })

async function enterAdmin() {
  if (leaving.value) return
  leaving.value = true
  accountMenuOpen.value = false
  try { await logoutSession() } catch (error) { leaving.value = false; window.alert(error.message || '退出失败，请重试'); return }
  aiChat.syncAccount()
  await router.replace({ path: '/login', query: { portal: 'admin' } })
}
function updateViewportMode() { isNarrowViewport.value = window.matchMedia('(max-width: 767px)').matches; if (!isNarrowViewport.value) appStore.closeMobileNavigation() }
async function logout() {
  if (leaving.value) return
  leaving.value = true
  accountMenuOpen.value = false
  try { await logoutSession() } catch (error) { leaving.value = false; window.alert(error.message || '退出失败，请重试'); return }
  aiChat.syncAccount()
  await router.replace({ path: '/login', query: { redirect: '/' } })
}
async function loadToolGroups() {
  if (!toolCatalogPromise) {
    toolCatalogPromise = import('../views/operations/toolCatalog.js').then(module => {
      toolGroups.value = module.operationToolGroups
    })
  }
  await toolCatalogPromise
}

function toggleToolsMenu() {
  toolsOpen.value = !toolsOpen.value
  if (toolsOpen.value) loadToolGroups()
}

function openOpsSpiderAction(destination) { router.push(destination) }
function closeMobileNavigation() { appStore.closeMobileNavigation() }
function expandSidebar() { appStore.expandSidebar() }
function collapseSidebar() { appStore.collapseSidebar() }
function togglePersonalSystemGroup(groupId) { appStore.togglePersonalSystemGroup(groupId, route.name?.toString()) }
async function toggleNavigation() {
  if (!isNarrowViewport.value) { appStore.toggleSidebar(); return }
  appStore.toggleMobileNavigation()
  if (appStore.mobileNavigationOpen) {
    await nextTick()
    navigationPanel.value?.querySelector('.navigation-group__link')?.focus()
  }
}

watch(() => route.name, routeName => appStore.setRouteNavigation(routeName?.toString()), { immediate: true })
watch(() => route.fullPath, value => companion.setPage(value), { immediate: true })
onMounted(() => { disconnectCompanion = companion.connectLegacyEvents(window); updateViewportMode(); updateTime(); startGlobalOpsPolling(); window.addEventListener('resize', updateViewportMode); timer = window.setInterval(updateTime, 30000); document.addEventListener('pointerdown', onDocumentPointerdown, true); document.addEventListener('keydown', onDocumentKeydown) })
onBeforeUnmount(() => { disconnectCompanion?.(); window.removeEventListener('resize', updateViewportMode); window.clearInterval(timer); document.removeEventListener('pointerdown', onDocumentPointerdown, true); document.removeEventListener('keydown', onDocumentKeydown) })
</script>

<style scoped>
.topbar-right { flex-wrap: wrap; }
.app-layout[data-visual-mode='reduced-motion'] :deep(*) { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
.home-galaxy { position: fixed; opacity: .7; }
.workspace-context { display: flex; align-items: center; gap: 8px; padding: 8px 18px 0; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .1em; }.workspace-context select { min-height: 26px; max-width: 220px; padding: 3px 20px 3px 7px; border: 1px solid var(--smart-border); border-radius: 4px; background: var(--smart-surface); color: var(--smart-text); font: 11px var(--font-cn); }.workspace-context small { color: var(--smart-primary-strong); font: 9px var(--font-mono); }
.tools-menu { position: relative; margin-left: auto; }.tools-trigger { border: 0; background: transparent; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .1em; cursor: pointer; }.tools-dropdown { position: absolute; z-index: 30; top: 28px; right: 0; display: grid; grid-template-columns: repeat(3, 170px); gap: 18px; padding: 18px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); box-shadow: 0 18px 45px rgba(0,0,0,.38); }.tools-dropdown section { display: grid; align-content: start; gap: 8px; }.tools-dropdown strong { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .1em; }.tools-dropdown a { color: var(--smart-text); font: 12px var(--font-cn); text-decoration: none; }.tools-dropdown a:hover { color: var(--smart-primary-strong); }
.theme-control { display: inline-flex; align-items: center; gap: 7px; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .08em; }.theme-control select { min-height: 28px; padding: 3px 22px 3px 7px; border: 1px solid var(--smart-border); border-radius: 4px; background: var(--smart-surface); color: var(--smart-text); font: 10px var(--font-cn); cursor: pointer; }.theme-control select:hover { border-color: var(--smart-primary-strong); }
.theme-control.visual-mode-control select { min-width: 96px; min-height: 44px; font-size: 12px; }
.visual-mode-control select:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.nav-icon { width: 14px; height: 14px; }.nav-copy { display: grid; gap: 1px; min-width: 0; }.nav-copy b { color: inherit; font: 10px var(--font-mono); letter-spacing: .1em; font-weight: 400; }.nav-copy small { color: var(--smart-muted); font: 12px var(--font-cn); letter-spacing: 0; }.nav-label { display: grid; gap: 3px; }.nav-label b { font: 10px var(--font-mono); letter-spacing: .13em; font-weight: 400; }.nav-label small { color: var(--smart-muted); font: 11px var(--font-cn); letter-spacing: 0; }.nav-label--system { margin-top: 28px; }
.app-jellyfish { position: fixed; z-index: 0; top: 7vh; right: 4vw; width: min(24vw, 320px); height: min(40vh, 380px); opacity: .38; pointer-events: none; }.app-jellyfish--agent { top: 11vh; right: 7vw; width: min(32vw, 420px); height: min(52vh, 500px); opacity: .62; }.app-jellyfish--knowledge { top: 5vh; right: 1vw; opacity: .28; transform: scale(.84); }.app-jellyfish--operations { top: auto; right: 4vw; bottom: 4vh; opacity: .38; transform: scale(.82); }.app-jellyfish--memory { top: auto; right: -1vw; bottom: 4vh; opacity: .26; transform: scale(.76); }
.app-companion-status{position:fixed;z-index:9;left:24px;bottom:18px;pointer-events:none}
.spider-restore-control {
  position: fixed;
  z-index: 21;
  right: 24px;
  bottom: 20px;
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  padding: 0;
  border: 1px solid var(--smart-border-strong);
  border-radius: 50%;
  background: var(--smart-surface);
  color: var(--smart-primary-strong);
  font: 11px var(--font-mono);
  cursor: pointer;
  box-shadow: 0 8px 22px rgba(0,0,0,.28);
  transition: border-color 160ms ease, color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}
.spider-restore-control:hover,
.spider-restore-control:focus-visible {
  border-color: var(--smart-primary-strong);
  color: var(--smart-primary-strong);
  box-shadow: 0 0 0 3px var(--smart-primary-soft, rgba(122,215,245,.12)), 0 8px 22px rgba(0,0,0,.28);
  outline: 0;
  transform: translateY(-1px);
}
/* Scope motion to the desktop rail. Keep icon columns fixed while revealing labels. */
@media (min-width: 768px) {
  /* T19：侧栏用新设计令牌，展开 256px / 收起 64px */
  .app-layout:not(.app-layout--tools) > .main-area { margin-left: var(--ds-sidebar-width-collapsed, 64px); }
  .app-layout:not(.app-layout--tools):not(.app-layout--sidebar-collapsed) > .main-area { margin-left: var(--ds-sidebar-width, 256px); }
  .app-layout:not(.app-layout--tools) > .sidebar {
    width: var(--ds-sidebar-width-collapsed, 64px); padding: 22px 12px 18px; overflow-x: hidden; overflow-y: auto;
    align-items: stretch; justify-content: flex-start;
    transition: width var(--ds-duration-micro, 150ms) var(--ds-ease-out, cubic-bezier(.22,1,.36,1));
  }
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded {
    width: var(--ds-sidebar-width, 256px); transition-duration: var(--ds-duration-micro, 150ms);
  }
  .app-layout:not(.app-layout--tools) > .sidebar .wordmark {
    position: relative; flex: 0 0 72px; height: 72px; padding: 0 0 24px;
    align-content: start; white-space: nowrap;
  }
  .app-layout:not(.app-layout--tools) > .sidebar .wordmark::before {
    content: 'S'; position: absolute; top: 0; left: 13px; font-size: 16px; color: var(--smart-primary-strong);
  }
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded .wordmark::before { visibility: hidden; }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.nav-icon) {
    width: 19px; height: 19px; justify-self: center;
  }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.personal-system-navigation),
  .app-layout:not(.app-layout--tools) > .sidebar .section-nav,
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.navigation-group) {
    min-width: 0; width: 100%;
  }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.nav-copy) { overflow: hidden; }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.navigation-group__row) {
    display: grid; grid-template-columns: minmax(0, 1fr) 0; min-height: 44px;
  }
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded :deep(.navigation-group__row) {
    grid-template-columns: minmax(0, 1fr) 28px;
  }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.navigation-group__link),
  .app-layout:not(.app-layout--tools) > .sidebar .section-nav a {
    grid-template-columns: 44px minmax(0, 1fr); min-height: 44px;
    padding: 0; border-left: 0; border-radius: 9px; text-align: left;
    transition: background-color 100ms ease-out, color 100ms ease-out;
  }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.navigation-group__link.active),
  .app-layout:not(.app-layout--tools) > .sidebar .section-nav a.router-link-active {
    background: var(--smart-primary-soft, rgba(122,215,245,.12));
  }
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.nav-copy),
  .app-layout:not(.app-layout--tools) > .sidebar :deep(.nav-label),
  .app-layout:not(.app-layout--tools) > .sidebar .wordmark span,
  .app-layout:not(.app-layout--tools) > .sidebar .wordmark small {
    display: grid; white-space: nowrap; opacity: 0; visibility: hidden; pointer-events: none;
    transition: opacity 180ms ease, visibility 0s linear 180ms;
  }
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded :deep(.nav-copy),
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded :deep(.nav-label),
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded .wordmark span,
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded .wordmark small {
    opacity: 1; visibility: visible; pointer-events: auto;
    transition: opacity 180ms ease, visibility 0s linear 0s;
  }
  .app-layout:not(.app-layout--tools) > .sidebar:not(.sidebar--expanded) :deep(.navigation-group__toggle) {
    visibility: hidden; pointer-events: none;
  }
  .app-layout:not(.app-layout--tools) > .sidebar:not(.sidebar--expanded) :deep(.navigation-group__children),
  .app-layout:not(.app-layout--tools) > .sidebar:not(.sidebar--expanded) .system-status { display: none; }
  .app-layout:not(.app-layout--tools) > .sidebar.sidebar--expanded .system-status {
    display: grid; opacity: 1; pointer-events: auto;
  }
  .sidebar-expand-control {
    position: fixed; z-index: 20; top: 34px; left: 45px; display: grid; gap: 4px;
    width: 34px; height: 34px; place-content: center; padding: 0; border: 1px solid var(--smart-border);
    border-radius: 8px; background: var(--smart-surface); color: var(--smart-primary-strong); cursor: pointer;
  }
  .sidebar-expand-control span { display: block; width: 16px; height: 2px; border-radius: 2px; background: currentColor; }
  .sidebar-collapse-control {
    position: fixed; z-index: 20; left: calc(var(--ds-sidebar-width-collapsed, 64px) + var(--ds-space-5, 20px) + 112px); bottom: 34px; width: auto; min-width: 66px; margin: 0; padding: 6px 9px;
    border: 1px solid var(--smart-border); border-radius: 7px; background: color-mix(in srgb, var(--smart-surface) 92%, transparent);
    color: var(--smart-muted); font: 10px var(--font-cn); line-height: 1; text-align: center; cursor: pointer;
  }
  .sidebar-expand-control:hover, .sidebar-expand-control:focus-visible,
  .sidebar-collapse-control:hover, .sidebar-collapse-control:focus-visible {
    border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); outline: none;
    box-shadow: 0 0 0 3px var(--smart-primary-soft, rgba(122,215,245,.12));
  }
  .app-layout:not(.app-layout--sidebar-collapsed) .sidebar-expand-control {
    left: 225px;
  }
}
@media (max-width: 767px) { .app-jellyfish { width: 230px; height: 280px; top: 54px; right: -44px; opacity: .24; }.app-jellyfish--agent { top: 62px; right: -18px; opacity: .4; }.app-jellyfish--operations, .app-jellyfish--memory { top: auto; bottom: 20px; right: -54px; }.section-nav { display: none; }.theme-control__label { display: none; }.theme-control select { min-height: 26px; } }
@media (max-width: 767px) { .spider-restore-control { right: 16px; bottom: 16px; } }
@media (prefers-reduced-motion: reduce) { .app-jellyfish { opacity: .12; } }
@media (max-width: 767px) {
  .sidebar-expand-control, .sidebar-collapse-control { display: none; }
  .topbar { justify-content: flex-start; flex-wrap: wrap; gap: 8px; padding-block: 6px; overflow: visible; }
  .menu-button { flex: 0 0 44px; min-height: 44px; white-space: nowrap; }
  .route-context { flex: 1; min-width: 0; }
  .tools-menu { flex: 0 0 auto; }
  .topbar-right { flex-basis: 100%; min-width: 0; gap: 10px; justify-content: space-between; }
  .topbar-right > time { font-size: 9px; }
  .tools-dropdown { width: min(330px, calc(100vw - 36px)); grid-template-columns: 1fr; max-height: 65dvh; overflow-y: auto; }
}
.app-jellyfish--home { top: 44vh; right: 3vw; width: min(23vw, 300px); height: min(38vh, 340px); opacity: .62; }
.team-scope-note{padding:12px;color:var(--smart-muted);font-size:12px;line-height:1.7}
.workspace-context{flex-wrap:wrap}
@media (max-width: 767px) { .app-jellyfish--home { top: 52vh; right: -20px; left: auto; width: 180px; height: 230px; opacity: .36; } }
.sidebar :deep(.nav-discovery-trigger) { width:100%; margin-bottom:20px; flex-shrink:0; }
.sidebar :deep(.nav-discovery-trigger kbd) { margin-left:auto; font-size:8px; padding-left:6px; }
@media(min-width:768px) {
  .sidebar.collapsed :deep(.nav-discovery-trigger) { width:44px; justify-content:center; padding:8px; }
  .sidebar.collapsed :deep(.nav-discovery-trigger span), .sidebar.collapsed :deep(.nav-discovery-trigger kbd) { display:none; }
}
/* Navigation shell: editorial coordinates and a quiet instrument edge. */
.sidebar { border-top: 2px solid var(--smart-primary-strong); }
.sidebar--expanded .wordmark { border-bottom: 1px solid var(--smart-border); margin-bottom: 20px; }
.sidebar--expanded .wordmark small { margin-top: 8px; }
.topbar { gap: 14px; }
@media(max-width:1023px) { .topbar { flex-wrap:wrap; } }
/* 个人账户芯片：点击开关的小窗口用户中心（交互契约对齐管理台用户菜单）。 */
/* lggc 包给 .lggc 设了 overflow:hidden，顶栏带着 lggc 类——不放开的话下拉面板
   （本菜单与 TOOLS 下拉）在桌面端会被裁得只剩一条边，看得见的位置点不中。 */
.topbar { overflow: visible; }
.account-menu { position: relative; }
.account-menu-trigger { display: flex; align-items: center; gap: 8px; min-height: 34px; padding: 3px 12px 3px 4px; border: 1px solid transparent; border-radius: 999px; background: transparent; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .1em; cursor: pointer; transition: border-color 160ms ease, background-color 160ms ease, color 160ms ease; }
.account-menu-trigger:hover, .account-menu-trigger[aria-expanded='true'] { border-color: var(--smart-border-strong); background: var(--smart-primary-soft); color: var(--smart-text); }
.account-menu-avatar { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; flex: 0 0 auto; border-radius: 50%; background: var(--smart-primary-strong); color: var(--smart-bg); font: 600 12px var(--font-mono); }
.account-menu-caret { font-size: 9px; line-height: 1; transition: transform 160ms ease; }
.account-menu-trigger[aria-expanded='true'] .account-menu-caret { transform: rotate(180deg); }
.account-menu-dropdown { position: absolute; z-index: 40; top: calc(100% + 8px); left: 0; display: grid; gap: 2px; min-width: 212px; padding: 8px; border: 1px solid var(--smart-border-strong); border-radius: 12px; background: var(--smart-surface); box-shadow: var(--smart-shadow-command); }
.account-menu-header { display: grid; gap: 3px; padding: 6px 10px 10px; margin-bottom: 4px; border-bottom: 1px solid var(--smart-border); }
.account-menu-header strong { color: var(--smart-text); font: 500 13px var(--font-cn); letter-spacing: 0; }
.account-menu-header small { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .12em; }
.account-menu-dropdown a, .account-menu-dropdown button { display: flex; align-items: center; min-height: 38px; padding: 7px 12px; border: 0; border-radius: 8px; background: transparent; color: var(--smart-text); font: 12px var(--font-cn); text-align: left; cursor: pointer; transition: background-color 120ms ease, color 120ms ease; }
.account-menu-dropdown a:hover, .account-menu-dropdown button:hover { background: var(--smart-primary-soft); color: var(--smart-primary-strong); }
.account-menu-dropdown button:disabled { opacity: .55; cursor: default; }
.account-menu-dropdown button:disabled:hover { background: transparent; color: var(--smart-text); }
@media (max-width: 767px) { .account-menu-name { display: none; } .account-menu-trigger { padding: 3px 8px 3px 4px; } .account-menu-dropdown { left: auto; right: 0; } }
@media (prefers-reduced-motion: reduce) { .account-menu-trigger, .account-menu-caret, .account-menu-dropdown a, .account-menu-dropdown button { transition: none; } }

/* T20 控制台外壳：侧栏 / 顶栏改用分层表面令牌，去掉旧的玻璃与装饰描边。 */
.app-layout:not(.app-layout--tools) > .sidebar,
.app-layout:not(.app-layout--tools) > .main-area > .topbar {
  background: var(--ds-surface-raised) !important;
  border-color: var(--ds-hairline) !important;
  box-shadow: var(--ds-elevation-1) !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
}
.app-layout:not(.app-layout--tools) > .sidebar { border-top: 0 !important; }
.ops-statusbar__item b.is-success { color: var(--ds-semantic-success); }
.ops-statusbar__item b.is-warning { color: var(--ds-semantic-warning); }
.ops-statusbar__item b.is-danger { color: var(--ds-semantic-danger); }
.ops-statusbar__item b.is-muted { color: var(--ds-color-muted); }
.ops-statusbar__item:hover { color: var(--ds-color-text); }
</style>
