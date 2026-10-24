<template>
  <aside
    v-if="!store.hidden"
    ref="host"
    class="ops-spider-pet"
    :class="[{ 'ops-spider-pet--compact': compact, 'ops-spider-pet--dragging': dragging, 'ops-spider-pet--menu-open': store.menuOpen, 'menu-side-left': menuSideLeft, 'menu-side-right': !menuSideLeft, 'menu-side-up': menuSideUp, 'menu-side-down': !menuSideUp }, `ops-spider-pet--${visualState}`]"
    :style="positionStyle"
    aria-label="运维哨兵"
    @pointerenter="store.markActive()"
    @pointerdown="beginDrag"
    @pointermove="moveDrag"
    @pointerup="endDrag"
    @pointercancel="endDrag"
    @lostpointercapture="endDrag"
    @contextmenu="openContext"
  >
    <div class="orb-shell" aria-hidden="true">
      <span v-for="index in 10" :key="index" class="micro-star" :class="`micro-star--${index}`"></span>
      <KubernetesSpider :state="visualState" :size="size" pet />
    </div>

    <button
      class="core-control"
      type="button"
      :aria-expanded="store.menuOpen"
      aria-label="展开蜘蛛功能节点"
      @click.stop="toggleActions"
      @keydown.esc.prevent="store.closeMenus()"
    >
      <span>AI</span>
    </button>

    <!-- Status details stay available through the alert action; no hover panel is rendered. -->
    <section v-if="false" class="status-panel" :class="panelClass" aria-live="polite">
      <p>运维哨兵</p>
      <dl>
        <div><dt>集群</dt><dd>未接入</dd></div>
        <div><dt>智能体</dt><dd>{{ agentLabel }}</dd></div>
      </dl>
      <button v-if="investigationStore.activeFault" type="button" class="fault-entry" @click.stop="openInvestigation">
        <span>发现异常</span><strong>{{ investigationStore.activeFault.title }}</strong>
      </button>
    </section>

    <nav v-if="store.menuOpen" ref="actionMenu" class="action-orbit" :style="actionMenuStyle" aria-label="蜘蛛功能节点" @pointerdown.stop>
      <button v-for="action in actions" :key="action.id" type="button" class="action-orbit__button" :class="`action-orbit__${action.direction}`" :aria-label="action.label" :title="action.label" @click.stop="activateAction(action)">
        <component :is="actionIcons[action.id]" aria-hidden="true" />
        <span>{{ action.label }}</span>
      </button>
    </nav>

    <section v-if="chatOpen" ref="chatPanel" class="pet-chat" :style="chatPanelStyle" aria-label="桌宠 AI 对话" @pointerdown.stop>
      <button class="pet-chat__close" type="button" aria-label="关闭 AI 对话" title="关闭" @click.stop="chatOpen = false">×</button>
      <header><strong>AI 对话</strong><button type="button" aria-label="打开完整聊天" title="打开完整聊天" @click.stop="navigate('/chat')">↗</button></header>
      <AssistantSelector />
      <div ref="petMessages" class="pet-chat__messages" aria-live="polite">
        <article v-for="message in chatMessages.slice(-6)" :key="message.id" :class="`pet-chat__message--${message.role}`">
          <span v-if="message.pending" class="pet-chat__pending">正在思考…</span><span v-else :class="{ 'pet-chat__error': message.error }">{{ message.content }}</span>
          <AssistantEvidence v-if="!message.pending && !message.error" :message="message" />
        </article>
        <p v-if="!chatMessages.length" class="pet-chat__empty">说说你遇到的运维问题</p>
      </div>
      <form class="pet-chat__composer" @submit.prevent="sendPetMessage">
        <input v-model="petDraft" type="text" maxlength="2000" aria-label="输入运维问题" placeholder="输入问题…" :disabled="chatSending" />
        <button type="submit" aria-label="发送消息" title="发送消息" :disabled="chatSending || !chatCanSend || !petDraft.trim()">↑</button>
      </form>
    </section>

    <section v-if="store.contextOpen" ref="contextMenu" class="context-menu" :style="contextMenuStyle" aria-label="运维哨兵菜单" @pointerdown.stop>
      <button v-for="action in actions" :key="action.id" type="button" @click="activateAction(action)">{{ action.label }}</button>
      <div class="corner-actions"><button v-for="corner in corners" :key="corner.id" type="button" @click="moveToCorner(corner.id)">{{ corner.label }}</button></div>
      <button type="button" @click="visualState === 'sleeping' ? store.wake() : store.sleep()">{{ visualState === 'sleeping' ? '唤醒' : '休眠' }}</button>
      <button type="button" @click="store.hide()">隐藏</button>
    </section>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Bell, ChatDotRound, Collection, Connection, Cpu, Hide, Monitor, Moon } from '@element-plus/icons-vue'
import KubernetesSpider from './KubernetesSpider.vue'
import { calculateOpsSpiderDragPosition, cornerPosition, getOpsSpiderActions, resolveOpsSpiderSize, resolveOpsSpiderPanelPosition, shouldBeginOpsSpiderDrag, snapOpsSpiderToNearbyEdge } from './opsSpiderState.js'
import { useOpsSpiderStore } from '../../stores/opsSpider.js'
import { useInvestigationStore } from '../../stores/investigation.js'
import { useCompanionStore } from '../../stores/companion.js'
import { useAiChatStore } from '../../stores/aiChat.js'
import AssistantSelector from '../ai/AssistantSelector.vue'
import AssistantEvidence from '../ai/AssistantEvidence.vue'

const props = defineProps({ state: { type: String, default: 'idle' }, agentState: { type: String, default: 'idle' }, compact: { type: Boolean, default: false } })
const emit = defineEmits(['navigate'])
const store = useOpsSpiderStore()
const investigationStore = useInvestigationStore()
const companionStore = useCompanionStore()
const chatStore = useAiChatStore()
const { messages: chatMessages, sending: chatSending, canSend: chatCanSend, accountEpoch } = storeToRefs(chatStore)
const host = ref(null)
const actionMenu = ref(null)
const chatPanel = ref(null)
const contextMenu = ref(null)
const panelSizes = reactive({ actions: { width: 248, height: 210 }, chat: { width: 300, height: 200 }, context: { width: 208, height: 560 } })
let panelObserver
const petMessages = ref(null)
const petDraft = ref('')
watch(accountEpoch, () => { petDraft.value = '' }, { flush: 'sync' })
const chatOpen = ref(false)
const dragging = ref(false)
const viewportWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
const viewportHeight = ref(typeof window === 'undefined' ? 900 : window.innerHeight)
const drag = { pointerId: null, startX: 0, startY: 0, grabOffsetX: 0, grabOffsetY: 0, moved: false, coreOrigin: false }
const currentPosition = reactive({ x: 0, y: 0 })
const latestPointer = { x: 0, y: 0 }
let dragFrame = 0
let settleTimer
let sleepTimer
let suppressCoreClick = false
let suppressCoreTimer

const actions = getOpsSpiderActions()
const actionIcons = { chat: ChatDotRound, agent: Cpu, cluster: Connection, terminal: Monitor, knowledge: Collection, alerts: Bell, sleep: Moon, hide: Hide }
const corners = [{ id: 'top-left', label: '左上' }, { id: 'top-right', label: '右上' }, { id: 'bottom-left', label: '左下' }, { id: 'bottom-right', label: '右下' }]
const size = computed(() => props.compact ? 52 : resolveOpsSpiderSize({ width: viewportWidth.value }))
// Keep the pet and its orbit outside the expanded navigation rail on desktop.
const navigationSafeLeft = computed(() => viewportWidth.value >= 768 ? 272 : 12)
const viewport = computed(() => ({ viewportWidth: viewportWidth.value, viewportHeight: viewportHeight.value, size: size.value, inset: 20, safeLeft: navigationSafeLeft.value }))
const visualState = computed(() => store.sleeping ? 'sleeping' : props.state)
const agentLabel = computed(() => ({ idle: '待命', observing: '观察中', thinking: '思考中', executing: '执行中', warning: '注意', error: '异常', recovering: '恢复中' })[props.agentState] || '待命')
// The outer position has one owner: the drag/snap controller below. Keeping
// transform out of Vue's reactive style prevents a render from racing a
// pointer frame and makes direct manipulation pixel-for-pixel.
const positionStyle = computed(() => ({ '--pet-size': `${size.value}px` }))
// During a drag the store is intentionally updated only on release. Read the
// live controller position so the orbit can change direction with the pet.
const livePosition = computed(() => dragging.value ? currentPosition : (store.position || currentPosition))
const menuSideLeft = computed(() => livePosition.value.x > viewportWidth.value / 2)
const menuSideUp = computed(() => livePosition.value.y > viewportHeight.value / 2)
const panelClass = computed(() => ({ 'panel--left': menuSideLeft.value, 'panel--bottom': livePosition.value.y > viewportHeight.value / 2 }))

function panelStyle(name) {
  const position = resolveOpsSpiderPanelPosition({
    ...livePosition.value, size: size.value, panelWidth: panelSizes[name].width, panelHeight: panelSizes[name].height,
    viewportWidth: viewportWidth.value, viewportHeight: viewportHeight.value, safeLeft: navigationSafeLeft.value
  })
  return { left: `${position.left}px`, top: `${position.top}px`, right: 'auto', bottom: 'auto' }
}
const actionMenuStyle = computed(() => panelStyle('actions'))
const chatPanelStyle = computed(() => panelStyle('chat'))
const contextMenuStyle = computed(() => panelStyle('context'))

function measurePanels() {
  for (const [name, element] of [['actions', actionMenu.value], ['chat', chatPanel.value], ['context', contextMenu.value]]) {
    if (!element) continue
    const rect = element.getBoundingClientRect()
    panelSizes[name] = { width: rect.width, height: rect.height }
  }
}
watch([actionMenu, chatPanel, contextMenu], elements => {
  panelObserver?.disconnect()
  for (const element of elements) if (element) panelObserver?.observe(element)
  measurePanels()
}, { flush: 'post' })

function ensurePosition() {
  if (store.position) store.move(store.position, viewport.value)
  else store.setCorner('bottom-right', viewport.value)
  currentPosition.x = store.position?.x ?? 0
  currentPosition.y = store.position?.y ?? 0
  applyOuterTransform(currentPosition)
}
function applyOuterTransform(position) {
  host.value?.style.setProperty('transform', `translate3d(${position.x}px, ${position.y}px, 0)`)
}
function queueDragFrame() { if (!dragFrame) dragFrame = requestAnimationFrame(flushDragFrame) }
function flushDragFrame() {
  dragFrame = 0
  if (!dragging.value) return
  const position = calculateOpsSpiderDragPosition({ pointerX: latestPointer.x, pointerY: latestPointer.y, grabOffsetX: drag.grabOffsetX, grabOffsetY: drag.grabOffsetY, ...viewport.value })
  currentPosition.x = position.x
  currentPosition.y = position.y
  applyOuterTransform(position)
}
function beginDrag(event) {
  if ((event.pointerType === 'mouse' && event.button !== 0) || !shouldBeginOpsSpiderDrag({ menuOpen: store.menuOpen || store.contextOpen || chatOpen.value, interactiveTarget: Boolean(event.target?.closest?.('.action-orbit, .context-menu, .status-panel, .pet-chat')) })) return
  store.markActive()
  window.clearTimeout(settleTimer)
  host.value?.style.removeProperty('transition')
  drag.pointerId = event.pointerId
  drag.startX = event.clientX
  drag.startY = event.clientY
  drag.grabOffsetX = event.clientX - currentPosition.x
  drag.grabOffsetY = event.clientY - currentPosition.y
  latestPointer.x = event.clientX
  latestPointer.y = event.clientY
  drag.moved = false
  drag.coreOrigin = Boolean(event.target.closest('.core-control'))
  host.value?.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}
function moveDrag(event) {
  if (event.pointerId !== drag.pointerId) return
  const dx = event.clientX - drag.startX
  const dy = event.clientY - drag.startY
  if (!drag.moved && Math.hypot(dx, dy) < 6) return
  drag.moved = true
  dragging.value = true
  host.value?.style.setProperty('transition', 'none')
  latestPointer.x = event.clientX
  latestPointer.y = event.clientY
  queueDragFrame()
  event.preventDefault()
}
function endDrag(event) {
  if (drag.pointerId === null || (event?.pointerId !== undefined && event.pointerId !== drag.pointerId)) return
  if (dragFrame) { cancelAnimationFrame(dragFrame); dragFrame = 0; flushDragFrame() }
  const pointerId = drag.pointerId
  drag.pointerId = null
  if (host.value?.hasPointerCapture?.(pointerId)) host.value.releasePointerCapture(pointerId)
  const activateCore = !drag.moved && drag.coreOrigin && event?.type === 'pointerup'
  if (drag.moved) {
    suppressCoreClick = drag.coreOrigin
    const finalPosition = snapOpsSpiderToNearbyEdge({ ...currentPosition, ...viewport.value, threshold: 48 })
    const snapped = finalPosition.x !== currentPosition.x || finalPosition.y !== currentPosition.y
    // Persist the final logical position, while the inline transform animates
    // only after pointer release. No spring/lerp is used during dragging.
    store.setPosition(finalPosition, viewport.value)
    if (snapped) {
      host.value?.style.setProperty('transition', 'transform 190ms cubic-bezier(.2,.8,.2,1)')
      requestAnimationFrame(() => applyOuterTransform(finalPosition))
      settleTimer = window.setTimeout(() => host.value?.style.removeProperty('transition'), 210)
    } else applyOuterTransform(finalPosition)
    currentPosition.x = finalPosition.x
    currentPosition.y = finalPosition.y
  }
  drag.coreOrigin = false
  dragging.value = false
  if (activateCore) {
    suppressCoreClick = true
    store.markActive()
    store.toggleMenu()
    window.clearTimeout(suppressCoreTimer)
    suppressCoreTimer = window.setTimeout(() => { suppressCoreClick = false }, 0)
  }
}
function toggleActions() {
  if (suppressCoreClick) { suppressCoreClick = false; return }
  store.markActive()
  chatOpen.value = false
  store.toggleMenu()
}
function openContext(event) {
  if (event.target.closest('.action-orbit, .context-menu, .pet-chat')) return
  event.preventDefault()
  store.markActive()
  chatOpen.value = false
  store.toggleContext()
}
function navigate(route) { chatOpen.value = false; store.closeMenus(); emit('navigate', route) }
function activateAction(action) {
  if (action.id === 'chat') {
    chatOpen.value = true
    store.closeMenus()
    nextTick(() => petMessages.value?.scrollTo({ top: petMessages.value.scrollHeight, behavior: 'smooth' }))
    return
  }
  if (action.action === 'investigation') { openInvestigation(); return }
  if (action.action === 'sleep') { store.sleep(); return }
  if (action.action === 'hide') { store.hide(); return }
  if (action.route) navigate(action.route)
}
async function sendPetMessage() {
  const prompt = petDraft.value.trim()
  if (!prompt || chatSending.value || !chatCanSend.value) return
  petDraft.value = ''
  const generation = accountEpoch.value
  const conversationId = chatStore.activeId
  const success = await chatStore.sendMessage(prompt)
  if (!success && generation === accountEpoch.value && (!conversationId || chatStore.activeId === conversationId) && !petDraft.value) petDraft.value = prompt
  await nextTick()
  petMessages.value?.scrollTo({ top: petMessages.value.scrollHeight, behavior: 'smooth' })
}
function openInvestigation() {
  store.closeMenus()
  companionStore.openInvestigation()
}
function moveToCorner(corner) {
  const next = cornerPosition(corner, viewport.value)
  store.setCorner(corner, viewport.value)
  currentPosition.x = next.x
  currentPosition.y = next.y
  host.value?.style.setProperty('transition', 'transform 190ms cubic-bezier(.2,.8,.2,1)')
  requestAnimationFrame(() => applyOuterTransform(next))
  window.clearTimeout(settleTimer)
  settleTimer = window.setTimeout(() => host.value?.style.removeProperty('transition'), 210)
  store.closeMenus()
}
function onResize() { viewportWidth.value = window.innerWidth; viewportHeight.value = window.innerHeight; ensurePosition() }
function onKeydown(event) { if (event.key === 'Escape') { store.closeMenus(); chatOpen.value = false } else store.markActive() }
function markActive() { store.markActive() }
function onOutsidePointerDown(event) {
  store.markActive()
  if (!host.value?.contains(event.target)) store.closeMenus()
}
function onWindowBlur() { endDrag(); store.closeMenus() }
function checkSleep() { if (Date.now() - store.lastActivityAt >= 30 * 60 * 1000) store.sleep() }
function onVisibilityChange() { if (!document.hidden) store.markActive() }
onMounted(() => {
  panelObserver = new ResizeObserver(measurePanels)
  ensurePosition()
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('pointerdown', onOutsidePointerDown, { passive: true })
  window.addEventListener('touchstart', markActive, { passive: true })
  window.addEventListener('focus', markActive)
  window.addEventListener('blur', onWindowBlur)
  document.addEventListener('visibilitychange', onVisibilityChange)
  sleepTimer = window.setInterval(checkSleep, 30000)
})
onBeforeUnmount(() => {
  panelObserver?.disconnect()
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointerdown', onOutsidePointerDown)
  window.removeEventListener('touchstart', markActive)
  window.removeEventListener('focus', markActive)
  window.removeEventListener('blur', onWindowBlur)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.clearInterval(sleepTimer)
  window.clearTimeout(settleTimer)
  window.clearTimeout(suppressCoreTimer)
  cancelAnimationFrame(dragFrame)
})
</script>

<style scoped>
.ops-spider-pet {
  position: fixed; z-index: 8; top: 0; left: 0; width: var(--pet-size); height: var(--pet-size);
  touch-action: none; user-select: none; -webkit-user-drag: none; cursor: grab;
  transition: transform 190ms cubic-bezier(.2,.8,.2,1), opacity 180ms ease; will-change: transform;
}
.ops-spider-pet--dragging { cursor: grabbing; transition: none !important; }
.ops-spider-pet--menu-open { cursor: default; }
.orb-shell {
  position: relative; display: grid; place-items: center; width: 100%; height: 100%;
  border: 1px solid var(--pet-border); border-radius: 50%;
  background: radial-gradient(circle at 42% 36%, color-mix(in srgb, var(--smart-primary) 20%, var(--smart-surface)), var(--smart-surface) 58%, var(--smart-bg));
  box-shadow: inset 0 0 18px rgba(77,179,255,.1), 0 0 18px rgba(36,150,237,.13); animation: orb-breathe 6.8s ease-in-out infinite;
}
.orb-shell::before { content: ''; position: absolute; inset: 5px; border: 1px solid var(--pet-panel-border); border-radius: 50%; }
.orb-shell :deep(.spider) { position: relative; z-index: 2; filter: drop-shadow(0 0 4px rgba(122,215,245,.3)); }
.micro-star { position: absolute; z-index: 1; width: 1.5px; height: 1.5px; border-radius: 50%; background: var(--smart-primary-strong); opacity: .38; animation: star-drift 7s ease-in-out infinite; }
.micro-star--1 { left: 19%; top: 25%; animation-delay: -1.2s; }
.micro-star--2 { left: 73%; top: 17%; animation-delay: -2.8s; }
.micro-star--3 { left: 13%; top: 59%; animation-delay: -5.3s; }
.micro-star--4 { left: 81%; top: 68%; animation-delay: -.8s; }
.micro-star--5 { left: 66%; top: 82%; animation-delay: -3.8s; }
.micro-star--6 { left: 37%; top: 14%; animation-delay: -6.3s; }
.micro-star--7 { left: 29%; top: 77%; animation-delay: -4.4s; }
.micro-star--8 { left: 87%; top: 42%; animation-delay: -2.1s; }
.micro-star--9 { left: 8%; top: 39%; animation-delay: -5.8s; }
.micro-star--10 { left: 57%; top: 10%; animation-delay: -1.7s; }
.core-control {
  position: absolute; z-index: 3; inset: 50% auto auto 50%; width: 40px; height: 40px;
  transform: translate(-50%,-50%); border: 1px solid var(--pet-core-border); border-radius: 50%;
  background: var(--pet-core-bg); color: var(--pet-core-text); font: 11px var(--font-mono); cursor: pointer;
}
.ops-spider-pet--dragging .core-control { cursor: grabbing; }
.core-control:hover { border-color: var(--smart-primary-strong); box-shadow: 0 0 0 3px color-mix(in srgb, var(--smart-primary) 18%, transparent); }
.core-control:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.action-orbit, .status-panel, .context-menu, .pet-chat {
  position: absolute; z-index: 5; border: 1px solid var(--pet-panel-border); border-radius: 12px;
  background: var(--pet-panel-bg); color: var(--smart-text); box-shadow: var(--pet-action-shadow);
  max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); overflow-y: auto;
  cursor: default; touch-action: auto; user-select: text;
}
.action-orbit { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); width: 248px; gap: 6px; padding: 8px; }
.action-orbit .action-orbit__button {
  display: flex; align-items: center; justify-content: flex-start; gap: 8px; min-width: 0; min-height: 44px;
  padding: 9px 10px; border:1px solid var(--pet-action-border); border-radius: 8px;
  background:var(--pet-action-bg); color:var(--pet-action-text); font: 12px/1.4 var(--font-cn);
  cursor: pointer; transform: none; transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease;
}
.action-orbit__button :deep(svg) { width: 16px; height: 16px; flex: none; }
.action-orbit .action-orbit__button:hover, .action-orbit .action-orbit__button:focus-visible {
  transform: none; border-color: var(--smart-primary-strong); color: var(--smart-primary-strong);
  background: color-mix(in srgb, var(--smart-primary) 8%, var(--pet-action-bg));
}
.action-orbit .action-orbit__button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 1px; }
.pet-chat { display: flex; flex-direction: column; width: 300px; padding: 0; overflow: hidden; }
.pet-chat header { display: flex; flex: none; align-items: center; justify-content: space-between; padding: 8px 48px 8px 12px; border-bottom: 1px solid var(--pet-panel-border); font: 12px var(--font-cn); color: var(--smart-primary-strong); }
.pet-chat header button, .pet-chat__close {
  display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 1px solid var(--pet-panel-border); border-radius: 6px;
  background: var(--pet-action-bg); color: var(--smart-text); font-size: 18px; line-height: 1; cursor: pointer;
}
.pet-chat__close { position: absolute; z-index: 2; top: 8px; right: 8px; }
.pet-chat header button:hover, .pet-chat__close:hover { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }
.pet-chat__messages { display: grid; gap: 8px; min-height: 0; max-height: 220px; overflow: auto; padding: 12px; }
.pet-chat__messages article { padding: 8px 10px; border: 1px solid var(--pet-panel-border); border-radius: 8px; font: 12px/1.6 var(--font-cn); white-space: pre-wrap; overflow-wrap: anywhere; }
.pet-chat__message--user { justify-self: end; max-width: 88%; background: color-mix(in srgb, var(--smart-primary) 10%, var(--pet-action-bg)); color: var(--smart-text); }
.pet-chat__message--assistant { max-width: 92%; background: var(--smart-card); color: var(--smart-text); }
.pet-chat__empty { margin: 0; padding: 20px 4px; color: var(--smart-muted); font-size: 12px; text-align: center; }
.pet-chat__error { color: var(--smart-danger); }
.pet-chat > :deep(.assistant-selector) { margin: 8px 8px 0; }
.pet-chat__pending { color: var(--smart-muted); }
.pet-chat__composer { display: flex; flex: none; padding: 6px; gap: 6px; border-top: 1px solid var(--pet-panel-border); }
.pet-chat__composer input { min-width: 0; flex: 1; padding: 9px; border: 1px solid var(--pet-panel-border); border-radius: 6px; background: var(--pet-action-bg); color: var(--smart-text); font: 12px var(--font-cn); }
.pet-chat__composer input::placeholder { color: var(--smart-muted); opacity: 1; }
.pet-chat__composer button { width: 40px; min-height: 40px; border: 0; border-radius: 6px; background: var(--smart-primary); color: var(--pet-action-bg); font-weight: 700; cursor: pointer; }
.pet-chat__composer button:disabled { background: var(--smart-card); color: var(--smart-muted); border: 1px solid var(--pet-panel-border); cursor: not-allowed; }
.context-menu { width: 208px; display: grid; gap: 2px; padding: 8px; }
.context-menu button { min-height: 36px; padding: 8px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--smart-text); font: 12px var(--font-cn); text-align: left; cursor: pointer; }
.context-menu button:hover { color: var(--smart-primary-strong); border-color: var(--pet-panel-border); background: color-mix(in srgb, var(--smart-primary) 8%, var(--pet-action-bg)); }
.corner-actions { display: grid; grid-template-columns: repeat(2, 1fr); border-block: 1px solid var(--pet-panel-border); }
.status-panel { width: 172px; padding: 12px; }
.ops-spider-pet--compact .orb-shell { opacity: .8; }
.ops-spider-pet--warning .orb-shell { border-color: var(--smart-warning); }
.ops-spider-pet--error .orb-shell { border-color: var(--smart-danger); }
.ops-spider-pet--sleeping .orb-shell { opacity: .56; animation-duration: 12s; }
.ops-spider-pet--sleeping .micro-star { animation: none; opacity: .1; }
@keyframes orb-breathe { 0%, 100% { transform: scale(.98); } 50% { transform: scale(1.02); } }
@keyframes star-drift { 0%, 100% { transform: translate(0,0); opacity: .22; } 48% { transform: translate(2px,-2px); opacity: .62; } }
@media (prefers-reduced-motion: reduce) {
  .ops-spider-pet, .orb-shell, .action-orbit .action-orbit__button { transition: none; animation: none; }
  .micro-star { animation: none; }
}
</style>