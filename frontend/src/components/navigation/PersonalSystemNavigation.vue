<template>
  <nav
    ref="navRoot"
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
          :class="{ active: groupContainsRoute(group, currentRouteName), 'is-hazard': isGroupHazard(group) }"
          :to="group.to"
          :aria-label="groupAriaLabel(group)"
          :title="groupTitle(group)"
          @mouseenter="showDockTip(group, $event)"
          @mouseleave="hideDockTip"
          @focus="showDockTip(group, $event)"
          @blur="hideDockTip"
          @click="navigate"
        >
          <span class="nav-dock-tile" :data-dock-item="collapsed && !mobile ? '' : null" aria-hidden="true">
            <span class="nav-dock-tile__halo" />
            <component :is="iconFor(group.icon)" class="nav-icon" />
            <span class="nav-dock-tile__floor"><component :is="iconFor(group.icon)" class="nav-icon" /></span>
          </span>
          <span v-if="collapsed && !mobile" class="nav-dock-dot" :class="{ 'is-active': groupContainsRoute(group, currentRouteName) }" aria-hidden="true" />
          <span class="nav-copy"><span class="nav-coordinate" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span><b>{{ group.label }}</b><small>{{ group.cn }}</small></span>
          <Lock v-if="isGroupHazard(group)" class="nav-hazard-lock" aria-hidden="true" title="高危操作，语音不可直达" />
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
          <ArrowDown class="navigation-group__caret" :class="{ 'is-open': groupView(group).expanded }" aria-hidden="true" />
        </button>
      </div>
      <Transition name="navigation-collapse" @enter="onChildrenEnter" @after-enter="onChildrenAfterEnter" @leave="onChildrenLeave">
        <div
          v-if="groupView(group).expandable && groupView(group).expanded"
          :id="`personal-nav-${group.id}`"
          class="navigation-group__children"
        >
          <RouterLink
            v-for="(child, childIndex) in group.children"
            :key="child.routeName"
            :to="child.to"
            :class="{ active: child.routeName === currentRouteName, 'is-hazard': isChildHazard(child) }"
            :style="{ '--child-order': childIndex }"
            :aria-label="childAriaLabel(child)"
            :title="childTitle(child)"
            @click="navigate"
          >
            <span aria-hidden="true">·</span>
            <span><b>{{ child.label }}</b><small>{{ child.cn }}</small></span>
            <Lock v-if="isChildHazard(child)" class="nav-hazard-lock" aria-hidden="true" title="高危操作，语音不可直达" />
          </RouterLink>
        </div>
      </Transition>
      <Teleport to="body">
        <Transition :name="flyoutTransition">
          <div v-if="collapsed && flyoutGroupId === group.id" ref="setFlyoutEl" class="navigation-flyout" role="menu" :aria-label="`${group.cn} / ${group.label}`" :style="{ top: `${flyoutTop}px`, left: `${flyoutLeft}px`, maxHeight: `calc(100dvh - ${flyoutTop + 28}px)` }" @mouseenter="cancelCloseFlyout" @focusin="cancelCloseFlyout" @keydown="onFlyoutKeydown">
            <p class="navigation-flyout__title"><b>{{ group.label }}</b><small>{{ group.cn }}</small></p>
            <RouterLink
              v-for="child in group.children"
              :key="child.routeName"
              :to="child.to"
              :class="{ active: child.routeName === currentRouteName, 'is-hazard': isChildHazard(child) }"
              role="menuitem"
              :aria-label="childAriaLabel(child)"
              :title="childTitle(child)"
              @click="navigate"
            >
              <span aria-hidden="true">·</span>
              <span><b>{{ child.label }}</b><small>{{ child.cn }}</small></span>
              <Lock v-if="isChildHazard(child)" class="nav-hazard-lock" aria-hidden="true" title="高危操作，语音不可直达" />
            </RouterLink>
          </div>
        </Transition>
      </Teleport>
    </div>
    <Teleport to="body">
      <Transition name="nav-dock-tip">
        <span
          v-if="dockTip"
          class="nav-dock-tip"
          role="presentation"
          :style="{ top: `${dockTip.top}px`, left: `${dockTip.left}px` }"
        >
          <b>{{ dockTip.label }}</b><small>{{ dockTip.cn }}</small>
        </span>
      </Transition>
    </Teleport>
  </nav>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, Box, ChatDotRound, CircleCheck, Collection, Connection, Cpu, DataAnalysis, Grid, HomeFilled, Link, Lock, Memo, Monitor, Reading, Setting, Trophy } from '@element-plus/icons-vue'
import NavHealthBadge from './NavHealthBadge.vue'
import { useDockMagnification } from '../../composables/useDockMagnification.js'
import { navigationGroupView } from '../../navigation/personalSystemNavigation.js'
import { visualMode } from '../../visual/visualMode.js'
import { isHazardRoute, HAZARD_ROUTES } from '../persona/voiceCommandRegistry.js'

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

const icons = { Box, ChatDotRound, CircleCheck, Collection, Connection, Cpu, DataAnalysis, Grid, HomeFilled, Link, Memo, Monitor, Reading, Setting, Trophy }

function iconFor(name) {
  return icons[name]
}

function groupView(group) {
  return navigationGroupView(group, props.expandedGroupIds)
}

function groupContainsRoute(group, routeName) {
  return group.routeName === routeName || group.children.some(child => child.routeName === routeName)
}

/* ── 高危菜单视觉标记：与 voiceCommandRegistry 共用同一份注册表，
     让侧栏视觉、路由守卫、语音拦截三方同源。 ── */
function isGroupHazard(group) {
  if (isHazardRoute(group.to)) return true
  return group.children?.some(child => isChildHazard(child)) ?? false
}
function isChildHazard(child) {
  return isHazardRoute(child.to)
}
function _hazardSuffix(path) {
  const hazard = HAZARD_ROUTES[path]
  if (!hazard) return ''
  const levelTag = hazard.level === 'critical' ? '高危' : hazard.level === 'high' ? '较高危' : '需注意'
  return ` | ${levelTag}：${hazard.reason}（语音不可直达）`
}
function groupAriaLabel(group) {
  const hazard = _hazardSuffix(group.to)
  return `${group.cn} / ${group.label}${hazard}`
}
function groupTitle(group) {
  return groupAriaLabel(group)
}
function childAriaLabel(child) {
  const hazard = _hazardSuffix(child.to)
  return `${child.cn} / ${child.label}${hazard}`
}
function childTitle(child) {
  return childAriaLabel(child)
}

function navigate() {
  closeFlyout()
  emit('navigate')
  if (props.mobile) emit('close-mobile')
}

/* ── 展开组高度过渡（G3：无全局副作用；G5：reduced-motion 即时呈现） ── */
function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
/* 浮出层 Teleport 到 body，.app-layout 的视觉档选择器罩不到，直接读状态：
   减少动效/轻量档下交空名（无对应 CSS 类 → 即时呈现）。 */
const flyoutTransition = computed(() => (visualMode.value === 'balanced' ? 'navigation-flyout' : ''))
function onChildrenEnter(el) {
  if (prefersReducedMotion()) return
  const target = el.scrollHeight
  el.style.height = '0px'
  el.style.opacity = '0'
  requestAnimationFrame(() => {
    el.style.height = `${target}px`
    el.style.opacity = '1'
  })
}
function onChildrenAfterEnter(el) {
  el.style.height = ''
}
function onChildrenLeave(el) {
  if (prefersReducedMotion()) return
  el.style.height = `${el.scrollHeight}px`
  void el.offsetHeight
  requestAnimationFrame(() => {
    el.style.height = '0px'
    el.style.opacity = '0'
  })
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

/* ── 收起态 Dock 图标轨：磁吸放大 + 叶级浮签 ── */
const navRoot = ref(null)
const dockTip = ref(null)
let dockTipTimer = 0

const { refresh: refreshDock } = useDockMagnification(navRoot, {
  radius: 92,
  peak: 1.28,
  enabled: () => props.collapsed && !props.mobile && visualMode.value === 'balanced'
})

function showDockTip(group, event) {
  if (!props.collapsed || props.mobile) return
  // 可展开组悬停即出浮出层，已有完整标题，不再叠一枚浮签
  if (group.children.length) return
  window.clearTimeout(dockTipTimer)
  const rect = event.currentTarget.getBoundingClientRect()
  dockTip.value = {
    top: Math.round(rect.top + rect.height / 2),
    left: Math.round(rect.right + 10),
    label: group.label,
    cn: group.cn
  }
}
function hideDockTip() {
  window.clearTimeout(dockTipTimer)
  dockTipTimer = window.setTimeout(() => { dockTip.value = null }, 70)
}

watch(() => [props.collapsed, props.mobile, visualMode.value], () => {
  hideDockTip()
  nextTick(() => refreshDock())
})

onBeforeUnmount(() => {
  window.clearTimeout(flyoutTimer)
  window.clearTimeout(dockTipTimer)
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

/* ── 侧栏动效（G3：scoped + 克制时长；G5：reduced-motion 全量关闭） ── */
/* 1. 展开组高度过渡：JS 钩子驱动 height/opacity，结束后 height 归位 auto */
.navigation-collapse-enter-active,
.navigation-collapse-leave-active { overflow: hidden; transition: height 180ms cubic-bezier(.22,1,.36,1), opacity 150ms ease-out; }
/* 2. 折叠箭头：单图标旋转代替组件切换，方向变化有连续感 */
.navigation-group__caret { transition: transform 150ms cubic-bezier(.22,1,.36,1); }
.navigation-group__caret:not(.is-open) { transform: rotate(-90deg); }
/* 3. 子项级联入场：随 --child-order 依次淡入，30ms 步进封顶 180ms */
.navigation-group__children a { animation: nav-child-arrive 200ms ease backwards; animation-delay: calc(var(--child-order, 0) * 30ms); }
@keyframes nav-child-arrive { from { opacity: 0; transform: translateX(-5px); } to { opacity: 1; transform: none; } }
/* 4. 收起态浮出层：左侧 6px 滑入 + 淡入 */
.navigation-flyout-enter-active,
.navigation-flyout-leave-active { transition: opacity 140ms ease-out, transform 140ms cubic-bezier(.22,1,.36,1); }
.navigation-flyout-enter-from,
.navigation-flyout-leave-to { opacity: 0; transform: translateX(-6px); }

@media(prefers-reduced-motion:reduce) {
  .navigation-group { animation: none; }
  .navigation-collapse-enter-active,
  .navigation-collapse-leave-active,
  .navigation-group__caret,
  .navigation-group__children a,
  .navigation-flyout-enter-active,
  .navigation-flyout-leave-active { animation: none; transition: none; }
}
/* 轻量视觉档：去掉子项级联装饰层（浮出层由 flyoutTransition 状态控制，Teleport 不受选择器作用域限制） */
.app-layout[data-visual-mode='lightweight'] .navigation-group__children a { animation: none; }
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

/* ── 高危菜单视觉弱化 + 锁图标（与 voiceCommandRegistry 同源） ── */
.navigation-group__link.is-hazard .nav-icon,
.navigation-group__link.is-hazard .nav-copy b,
.navigation-group__link.is-hazard .nav-copy small { color: var(--smart-danger, #e06c75); opacity: 0.72; }
.navigation-group__link.is-hazard::after {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0; width: 2px;
  background: var(--smart-danger, #e06c75);
  border-radius: 1px;
  opacity: 0.55;
}
.nav-hazard-lock {
  width: 11px; height: 11px;
  color: var(--smart-danger, #e06c75);
  opacity: 0.85;
  margin-left: auto;
  flex-shrink: 0;
}
.navigation-group__link .nav-hazard-lock { position: absolute; right: 28px; top: 11px; }
.navigation-group__children a.is-hazard,
.navigation-flyout a.is-hazard { color: var(--smart-danger, #e06c75) !important; opacity: 0.78; }
.navigation-group__children a.is-hazard .nav-hazard-lock,
.navigation-flyout a.is-hazard .nav-hazard-lock { margin-left: auto; }

/* ── 收起态 Dock 图标轨：磁吸放大 + 悬停浮签 + 地面倒影 + 运行光点 ── */
.nav-dock-tile {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
}
.nav-dock-tile__halo,
.nav-dock-tile__floor { position: absolute; pointer-events: none; opacity: 0; }
.nav-dock-tile__halo {
  inset: -6px;
  border-radius: 14px;
  background: radial-gradient(circle at 50% 32%, color-mix(in srgb, var(--smart-primary-strong) 38%, transparent), transparent 72%);
  transition: opacity 220ms ease;
}
.nav-dock-tile__floor {
  left: 50%;
  top: 100%;
  display: grid;
  place-items: center;
  width: 20px;
  height: 12px;
  overflow: hidden;
  transform: translateX(-50%) scaleY(-1);
  mask-image: linear-gradient(to top, rgba(0, 0, 0, .5), transparent 78%);
  -webkit-mask-image: linear-gradient(to top, rgba(0, 0, 0, .5), transparent 78%);
  transition: opacity 220ms ease;
}
.nav-dock-tile__floor .nav-icon { width: 17px; height: 17px; color: var(--smart-primary-strong); }

.personal-system-navigation.is-collapsed .nav-dock-tile {
  width: 40px;
  height: 40px;
  justify-self: center;
  border: 1px solid transparent;
  border-radius: 11px;
  background: color-mix(in srgb, var(--smart-text) 5%, transparent);
  transform: scale(var(--dock-scale, 1));
  transform-origin: center;
  transition: border-color 200ms ease, background-color 200ms ease, box-shadow 220ms ease;
  will-change: transform;
}
.personal-system-navigation.is-collapsed .navigation-group__link:hover .nav-dock-tile,
.personal-system-navigation.is-collapsed .navigation-group__link.active .nav-dock-tile {
  border-color: color-mix(in srgb, var(--smart-primary-strong) 45%, transparent);
  background: color-mix(in srgb, var(--smart-primary-strong) 13%, transparent);
  box-shadow: 0 8px 20px color-mix(in srgb, var(--smart-primary-strong) 20%, transparent);
}
.personal-system-navigation.is-collapsed .nav-dock-tile .nav-icon { width: 18px; height: 18px; }
.personal-system-navigation.is-collapsed .navigation-group__link:hover .nav-icon,
.personal-system-navigation.is-collapsed .navigation-group__link.active .nav-icon { color: var(--smart-primary-strong); }
.personal-system-navigation.is-collapsed .nav-dock-tile:hover .nav-dock-tile__halo,
.personal-system-navigation.is-collapsed .navigation-group__link.active .nav-dock-tile__halo { opacity: .9; }
.personal-system-navigation.is-collapsed .navigation-group__link:hover .nav-dock-tile__floor { opacity: .3; }
.personal-system-navigation.is-collapsed .navigation-group__link { overflow: visible; }
.personal-system-navigation.is-collapsed .navigation-group__link:hover,
.personal-system-navigation.is-collapsed .navigation-group__link.active {
  padding-left: 0;
  border-left-color: transparent;
  background: transparent;
}
.personal-system-navigation.is-collapsed .navigation-group__link:hover { z-index: 3; }
.personal-system-navigation.is-collapsed .navigation-group__link.is-hazard::after { display: none; }

.nav-dock-dot {
  position: absolute;
  left: 50%;
  bottom: -6px;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--smart-text);
  opacity: 0;
  transform: translateX(-50%) scale(.6);
  transition: opacity 200ms ease, transform 200ms ease;
  pointer-events: none;
}
.nav-dock-dot.is-active { opacity: .9; transform: translateX(-50%) scale(1); }
.personal-system-navigation.is-collapsed .navigation-group__link:hover .nav-dock-dot { opacity: .55; transform: translateX(-50%) scale(1); }

/* 浮签：叶级菜单（无可展开子项）悬停/聚焦时贴图标右侧 */
.nav-dock-tip {
  position: fixed;
  z-index: 70;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--smart-border-strong);
  border-radius: 8px;
  background: var(--smart-surface);
  box-shadow: 0 14px 36px rgba(0, 0, 0, .38);
  transform: translateY(-50%);
  pointer-events: none;
  white-space: nowrap;
}
.nav-dock-tip b { color: var(--smart-primary-strong); font: 400 10px var(--font-mono); letter-spacing: .1em; }
.nav-dock-tip small { color: var(--smart-muted); font: 11px var(--font-cn); }
.nav-dock-tip::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 50%;
  width: 7px;
  height: 7px;
  border-left: 1px solid var(--smart-border-strong);
  border-bottom: 1px solid var(--smart-border-strong);
  background: var(--smart-surface);
  transform: translateY(-50%) rotate(45deg);
}
.nav-dock-tip-enter-active,
.nav-dock-tip-leave-active { transition: opacity 120ms ease-out, transform 140ms cubic-bezier(.22, 1, .36, 1); }
.nav-dock-tip-enter-from,
.nav-dock-tip-leave-to { opacity: 0; transform: translateY(-50%) translateX(-4px); }

@media (prefers-reduced-motion: reduce) {
  .nav-dock-tile { transition: none !important; }
  .nav-dock-tip-enter-active,
  .nav-dock-tip-leave-active { transition: none; }
}
.app-layout[data-visual-mode='lightweight'] .personal-system-navigation.is-collapsed .nav-dock-tile { transition: none; }
</style>
