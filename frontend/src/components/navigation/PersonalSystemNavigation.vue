<template>
  <nav
    v-show="!mobile || mobileOpen"
    class="personal-system-navigation"
    :class="{ 'personal-system-navigation--mobile': mobile, 'is-collapsed': collapsed }"
    aria-label="Personal system navigation"
    :aria-hidden="mobile && !mobileOpen ? 'true' : undefined"
  >
    <p class="nav-label"><b>PERSONAL SYSTEM</b><small>个人系统</small></p>
    <div v-for="(group, index) in groups" :key="group.id" class="navigation-group" :style="{ '--nav-order': index }" @mouseenter="openFlyout(group, $event)" @mouseleave="scheduleCloseFlyout" @focusin="openFlyout(group, $event)" @focusout="onGroupFocusOut">
      <div class="navigation-group__row">
        <RouterLink
          class="navigation-group__link"
          :class="{ active: groupContainsRoute(group, currentRouteName) }"
          :to="group.to"
          :aria-label="`${group.cn} / ${group.label}`"
          :title="`${group.cn} / ${group.label}`"
          @click="navigate"
        >
          <component :is="iconFor(group.icon)" class="nav-icon" aria-hidden="true" />
          <span class="nav-copy"><span class="nav-coordinate" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span><b>{{ group.label }}</b><small>{{ group.cn }}</small></span>
          <NavHealthBadge v-if="healthBadges[group.id]" class="nav-health-badge-slot" :level="healthBadges[group.id]" :label="`${group.cn} / ${group.label}`" />
        </RouterLink>
        <button
          v-if="groupView(group).expandable"
          type="button"
          class="navigation-group__toggle"
          :aria-expanded="groupView(group).expanded"
          :aria-controls="`personal-nav-${group.id}`"
          :aria-label="`${groupView(group).expanded ? 'Collapse' : 'Expand'} ${group.label} navigation`"
          @click="emit('toggle-group', group.id)"
        >
          <ArrowDown v-if="groupView(group).expanded" aria-hidden="true" />
          <ArrowRight v-else aria-hidden="true" />
        </button>
      </div>
      <div
        v-if="groupView(group).expandable && groupView(group).expanded"
        :id="`personal-nav-${group.id}`"
        class="navigation-group__children"
      >
        <RouterLink
          v-for="child in group.children"
          :key="child.routeName"
          :to="child.to"
          :class="{ active: child.routeName === currentRouteName }"
          @click="navigate"
        >
          <span aria-hidden="true">·</span>
          <span><b>{{ child.label }}</b><small>{{ child.cn }}</small></span>
        </RouterLink>
      </div>
      <Teleport to="body">
        <div v-if="collapsed && flyoutGroupId === group.id" ref="setFlyoutEl" class="navigation-flyout" role="menu" :aria-label="`${group.cn} / ${group.label}`" :style="{ top: `${flyoutTop}px`, left: `${flyoutLeft}px`, maxHeight: `calc(100dvh - ${flyoutTop + 28}px)` }" @mouseenter="cancelCloseFlyout" @focusin="cancelCloseFlyout" @keydown="onFlyoutKeydown">
          <p class="navigation-flyout__title"><b>{{ group.label }}</b><small>{{ group.cn }}</small></p>
          <RouterLink
            v-for="child in group.children"
            :key="child.routeName"
            :to="child.to"
            :class="{ active: child.routeName === currentRouteName }"
            role="menuitem"
            @click="navigate"
          >
            <span aria-hidden="true">·</span>
            <span><b>{{ child.label }}</b><small>{{ child.cn }}</small></span>
          </RouterLink>
        </div>
      </Teleport>
    </div>
  </nav>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, ChatDotRound, CircleCheck, Collection, Cpu, DataAnalysis, Grid, HomeFilled, Link, Memo, Monitor, Setting, Trophy } from '@element-plus/icons-vue'
import NavHealthBadge from './NavHealthBadge.vue'
import { navigationGroupView } from '../../navigation/personalSystemNavigation.js'

const props = defineProps({
  groups: { type: Array, required: true },
  expandedGroupIds: { type: Array, required: true },
  currentRouteName: { type: String, default: '' },
  mobile: { type: Boolean, default: false },
  mobileOpen: { type: Boolean, default: false },
  // 桌面图标轨（收起态）下子菜单以浮出层呈现；移动端/展开态为 false
  collapsed: { type: Boolean, default: false },
  // { groupId: level }，见 navigation/navigationHealth.js
  healthBadges: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['toggle-group', 'navigate', 'close-mobile'])

const icons = { ChatDotRound, CircleCheck, Collection, Cpu, DataAnalysis, Grid, HomeFilled, Link, Memo, Monitor, Setting, Trophy }

function iconFor(name) {
  return icons[name]
}

function groupView(group) {
  return navigationGroupView(group, props.expandedGroupIds)
}

function groupContainsRoute(group, routeName) {
  return group.routeName === routeName || group.children.some(child => child.routeName === routeName)
}

function navigate() {
  closeFlyout()
  emit('navigate')
  if (props.mobile) emit('close-mobile')
}

/* 收起态浮出层：hover / 键盘聚焦均可唤出，180ms 宽限期允许指针移入浮层。 */
const flyoutGroupId = ref('')
const flyoutTop = ref(0)
const flyoutLeft = ref(0)
const flyoutEl = ref(null)
let flyoutRow = null
let flyoutTimer = 0

function openFlyout(group, event) {
  if (!props.collapsed || groupView(group).expandable === false) return
  window.clearTimeout(flyoutTimer)
  flyoutRow = event.currentTarget
  flyoutGroupId.value = group.id
  const rect = flyoutRow.getBoundingClientRect()
  flyoutTop.value = Math.round(rect.top)
  flyoutLeft.value = Math.round(rect.right + 12)
  // 键盘唤出时焦点跟进浮层首项（与原生菜单行为一致）
  if (event.type === 'focusin') {
    nextTick().then(() => flyoutEl.value?.querySelector('a')?.focus())
  }
}
function scheduleCloseFlyout() {
  window.clearTimeout(flyoutTimer)
  flyoutTimer = window.setTimeout(() => { flyoutGroupId.value = '' }, 180)
}
function cancelCloseFlyout() { window.clearTimeout(flyoutTimer) }
function closeFlyout(restoreFocus = false) {
  window.clearTimeout(flyoutTimer)
  flyoutGroupId.value = ''
  if (restoreFocus) flyoutRow?.querySelector('.navigation-group__link')?.focus()
  flyoutRow = null
}
function onFlyoutKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeFlyout(true)
  }
}
function onGroupFocusOut(event) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  scheduleCloseFlyout()
}
function setFlyoutEl(element) { flyoutEl.value = element }
/* 渲染后测量并夹取进视窗：行靠近视窗底部时浮层整体上移，不出屏。 */
function clampFlyout() {
  if (!flyoutEl.value || !flyoutRow?.isConnected) return
  const rowTop = Math.round(flyoutRow.getBoundingClientRect().top)
  const limit = window.innerHeight - flyoutEl.value.offsetHeight - 12
  flyoutTop.value = Math.max(12, Math.min(rowTop, limit))
}
function syncFlyoutPosition() {
  if (!flyoutRow?.isConnected) { closeFlyout(); return }
  clampFlyout()
}
function handleFlyoutResize() { closeFlyout() }
watch(flyoutGroupId, async value => {
  if (value) {
    window.addEventListener('scroll', syncFlyoutPosition, true)
    window.addEventListener('resize', handleFlyoutResize)
    window.addEventListener('keydown', onFlyoutKeydown)
    await nextTick()
    clampFlyout()
  } else {
    window.removeEventListener('scroll', syncFlyoutPosition, true)
    window.removeEventListener('resize', handleFlyoutResize)
    window.removeEventListener('keydown', onFlyoutKeydown)
  }
}, { flush: 'post' })
watch(() => props.currentRouteName, () => closeFlyout())
onBeforeUnmount(() => {
  window.clearTimeout(flyoutTimer)
  window.removeEventListener('scroll', syncFlyoutPosition, true)
  window.removeEventListener('resize', handleFlyoutResize)
  window.removeEventListener('keydown', onFlyoutKeydown)
})
</script>

<style scoped>
.personal-system-navigation { display: grid; gap: 3px; }
.nav-label { display: grid; gap: 3px; margin: 0 0 8px; }
.nav-label b { font: 10px var(--font-mono); letter-spacing: .13em; font-weight: 400; }.nav-label small { color: var(--smart-muted); font: 11px var(--font-cn); }
.navigation-group__row { display: grid; grid-template-columns: minmax(0, 1fr) 28px; align-items: stretch; min-height: 38px; }.navigation-group__link { display: grid; grid-template-columns: 28px minmax(0, 1fr); align-items: center; min-width: 0; color: var(--smart-muted); border-left: 1px solid transparent; text-decoration: none; transition: color var(--duration-fast), border-color var(--duration-fast), padding var(--duration-fast); }.navigation-group__link:hover, .navigation-group__link.active { padding-left: 8px; border-left-color: var(--smart-primary); color: var(--smart-text); }.navigation-group__link.active .nav-icon { color: var(--smart-primary-strong); }.nav-icon { width: 14px; height: 14px; color: rgba(146,166,181,.66); stroke-width: 1.6; }.nav-copy { display: grid; gap: 1px; min-width: 0; }.nav-copy b { color: inherit; font: 10px var(--font-mono); letter-spacing: .1em; font-weight: 400; }.nav-copy small { color: var(--smart-muted); font: 12px var(--font-cn); letter-spacing: 0; }
.navigation-group__toggle { display: grid; place-items: center; width: 28px; border: 0; background: transparent; color: var(--smart-muted); cursor: pointer; }.navigation-group__toggle:hover, .navigation-group__toggle:focus-visible { color: var(--smart-primary-strong); outline: 1px solid var(--smart-primary-strong); outline-offset: -3px; }.navigation-group__toggle svg { width: 13px; height: 13px; }
.navigation-group__children { display: grid; gap: 1px; margin: 2px 0 5px 28px; padding-left: 12px; border-left: 1px solid var(--smart-border); }.navigation-group__children a { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 7px; align-items: center; min-height: 30px; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .07em; text-decoration: none; }.navigation-group__children a:hover, .navigation-group__children a.active { color: var(--smart-primary-strong); }.navigation-group__children b, .navigation-group__children small { display: block; }.navigation-group__children b { font: inherit; font-weight: 400; }.navigation-group__children small { margin-top: 2px; color: var(--smart-muted); font: 11px var(--font-cn); letter-spacing: 0; }
@media (max-width: 767px) { .personal-system-navigation--mobile { gap: 7px; padding: 18px; border-top: 1px solid var(--smart-border); border-bottom: 1px solid var(--smart-border); background: var(--smart-surface); }.personal-system-navigation--mobile .navigation-group__row { min-height: 44px; }.personal-system-navigation--mobile .navigation-group__toggle { width: 44px; }.personal-system-navigation--mobile .navigation-group__children a { min-height: 40px; } }

.navigation-group { animation: nav-arrive 240ms ease both; animation-delay: calc(var(--nav-order) * 12ms); }
.navigation-group__link { position:relative; }
.nav-copy { position:relative; padding:8px 22px 8px 0; }
.nav-coordinate { position:absolute; top:11px; right:2px; font:9px var(--font-mono); color:var(--smart-muted); opacity:.65; }
.navigation-group__link.active { box-shadow:inset 2px 0 var(--smart-primary-strong); }
.navigation-group__link.active .nav-coordinate { color:var(--smart-primary-strong); opacity:1; }
.navigation-group__link:hover { background:var(--smart-primary-soft); }
.navigation-group__children { margin-left:22px; border-left-style:dashed; }
.navigation-group__children a { min-height:44px; padding:5px 0; }
.navigation-group__toggle { min-height:44px; }
@keyframes nav-arrive { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
@media(prefers-reduced-motion:reduce) { .navigation-group { animation:none; } }
/* 健康徽章：展开态贴链接右下（避开右上角坐标位），收起态贴图标右上角标。 */
.nav-health-badge-slot { position:absolute; right:10px; bottom:9px; }
.personal-system-navigation.is-collapsed .nav-health-badge-slot { right:6px; bottom:auto; top:7px; }
/* 收起态子菜单浮出层（桌面图标轨专用，fixed 定位避开侧栏 overflow 裁剪）。 */
.navigation-flyout { position:fixed; left:calc(var(--ds-sidebar-width-collapsed, 64px) + var(--ds-space-5, 20px)); z-index:60; min-width:210px; padding:10px 6px; overflow-y:auto; border:1px solid var(--smart-border-strong); border-radius:6px; background:var(--smart-surface); box-shadow:0 18px 45px rgba(0,0,0,.38); }
.navigation-flyout__title { display:flex; align-items:baseline; gap:8px; margin:0 0 6px; padding:0 12px 8px; border-bottom:1px solid var(--smart-border); }
.navigation-flyout__title b { color:var(--smart-primary-strong); font:10px var(--font-mono); letter-spacing:.1em; font-weight:400; }
.navigation-flyout__title small { color:var(--smart-muted); font:11px var(--font-cn); }
.navigation-flyout a { display:grid; grid-template-columns:10px minmax(0,1fr); gap:8px; align-items:center; min-height:40px; padding:4px 12px; border-left:2px solid transparent; color:var(--smart-muted); text-decoration:none; }
.navigation-flyout a:hover, .navigation-flyout a.active { background:var(--smart-primary-soft); border-left-color:var(--smart-primary-strong); color:var(--smart-primary-strong); }
.navigation-flyout a b { font:10px var(--font-mono); letter-spacing:.07em; font-weight:400; }
.navigation-flyout a small { display:block; margin-top:2px; font:11px var(--font-cn); }
</style>
