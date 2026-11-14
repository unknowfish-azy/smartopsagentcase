<template>
  <aside
    ref="host"
    class="persona-pet"
    :class="{ 'persona-pet--collapsed': store.collapsed, 'persona-pet--dragging': dragging }"
    :style="positionStyle"
    aria-label="数字人桌宠"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @lostpointercapture="onPointerUp"
  >
    <template v-if="!store.collapsed">
      <header class="persona-pet__bar" aria-label="数字人桌宠控制条">
        <span class="persona-pet__title">数字人</span>
        <span class="persona-pet__bar-actions">
          <button type="button" class="persona-pet__mini" :disabled="speaking" aria-label="播报一句问候（Web Speech）" title="播报一句问候" @click.stop="speakGreeting">说</button>
          <button type="button" class="persona-pet__mini" aria-label="打开全页数字人" title="全页模式" @click.stop="openFullPage">↗</button>
          <button type="button" class="persona-pet__mini" aria-label="收起桌宠" title="收起" @click.stop="store.setCollapsed(true, currentViewport)">—</button>
          <button type="button" class="persona-pet__mini" aria-label="关闭桌宠" title="关闭" @click.stop="store.disable()">×</button>
        </span>
      </header>
      <div class="persona-pet__stage">
        <AgentPersona ref="personaRef" mode="vrm" :state="agentState" @ready="onReady" />
      </div>
      <p class="persona-pet__note" aria-live="polite">
        {{ speechLabel }}
        <span class="persona-pet__note-hint">口型为近似同步，非音素级</span>
      </p>
    </template>
    <button
      v-else
      type="button"
      class="persona-pet__orb"
      :aria-label="`展开数字人桌宠，当前状态：${agentStateLabel}`"
      :title="`数字人（${agentStateLabel}）· 点击展开`"
      @click.stop="store.setCollapsed(false, currentViewport)"
    />
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AgentPersona from './AgentPersona.vue'
import { createPetSpeech, isSpeechSynthesisAvailable } from './petSpeech.js'
import { PERSONA_PET_INSET, usePersonaPetStore } from '../../stores/personaPet.js'
import { useCompanionStore } from '../../stores/companion.js'

const GREETING = '正在检查集群节点健康状态，发现两个副本延迟偏高，准备滚动重启。'

const store = usePersonaPetStore()
const companion = useCompanionStore()
const router = useRouter()

const host = ref(null)
const personaRef = ref(null)
const dragging = ref(false)
const speaking = ref(false)
const ready = ref(false)
const speechSupported = isSpeechSynthesisAvailable()

const viewport = reactive({ width: window.innerWidth, height: window.innerHeight })
const currentViewport = computed(() => ({ viewportWidth: viewport.width, viewportHeight: viewport.height }))
const drag = { pointerId: null, startX: 0, startY: 0, lastX: 0, lastY: 0, originX: 0, originY: 0, moved: false }
const positionStyle = computed(() => ({
  transform: `translate(${store.position.x}px, ${store.position.y}px)`
}))

const agentState = computed(() => (companion.states.whale === 'DEGRADED' ? 'warning' : 'idle'))
const agentStateLabel = computed(() =>
  ({ idle: '待命', warning: '注意' })[agentState.value] ?? '待命'
)
const speechLabel = computed(() => {
  if (!speechSupported) return '当前浏览器不支持语音播报，仅文字近似口型'
  if (speaking.value) return '语音播报中'
  return ready.value ? '静默' : '加载中'
})

const petSpeech = createPetSpeech({
  onBoundary: (charIndex) => personaRef.value?.seekSpeech?.(charIndex),
  onEnd: () => stopSpeech(),
  onError: () => stopSpeech()
})

function onPointerDown(event) {
  // 收起小球：整颗可拖；展开态：仅标题栏把手可拖，避免劫持画布区
  if (!store.collapsed && !event.target.closest('.persona-pet__bar')) return
  if (event.button !== 0) return
  drag.pointerId = event.pointerId
  drag.startX = event.clientX
  drag.startY = event.clientY
  drag.lastX = event.clientX
  drag.lastY = event.clientY
  drag.originX = store.position.x
  drag.originY = store.position.y
  drag.moved = false
  dragging.value = true
  host.value?.setPointerCapture?.(event.pointerId)
}

function onPointerMove(event) {
  if (drag.pointerId !== event.pointerId) return
  const deltaX = event.clientX - drag.startX
  const deltaY = event.clientY - drag.startY
  if (!drag.moved && Math.hypot(deltaX, deltaY) < 3) return
  drag.moved = true
  store.moveBy(event.clientX - (drag.lastX ?? drag.startX), event.clientY - (drag.lastY ?? drag.startY), {
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
    inset: PERSONA_PET_INSET
  })
  drag.lastX = event.clientX
  drag.lastY = event.clientY
}

function onPointerUp(event) {
  if (drag.pointerId !== event.pointerId) return
  drag.pointerId = null
  drag.lastX = 0
  drag.lastY = 0
  dragging.value = false
  if (drag.moved) {
    store.setPosition(store.position, {
      viewportWidth: viewport.width,
      viewportHeight: viewport.height
    })
  }
}

function onReady() {
  ready.value = true
}

function speakGreeting() {
  if (!personaRef.value || speaking.value) return
  if (!speechSupported || !petSpeech.speak(GREETING)) {
    // 无语音能力：退化为纯文字时间线，UI 已如实标注
    personaRef.value.speakText(GREETING, { cps: 5 })
    speaking.value = false
    return
  }
  speaking.value = true
  personaRef.value.speakText(GREETING, { cps: 5 })
}

function stopSpeech() {
  speaking.value = false
  personaRef.value?.stopSpeaking()
}

function openFullPage() {
  stopSpeech()
  router.push('/agent/persona')
}

function updateViewport() {
  viewport.width = window.innerWidth
  viewport.height = window.innerHeight
  store.setPosition(store.position, {
    viewportWidth: viewport.width,
    viewportHeight: viewport.height
  })
}

onMounted(() => window.addEventListener('resize', updateViewport))
onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
  petSpeech.dispose()
  personaRef.value?.stopSpeaking?.()
})
</script>

<style scoped>
.persona-pet {
  position: fixed;
  left: 0;
  top: 0;
  z-index: 60;
  width: 232px;
  display: grid;
  gap: var(--ds-space-2);
  padding: var(--ds-space-2);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: radial-gradient(120% 90% at 50% 0%, rgba(36, 150, 237, .14), transparent 62%), var(--ds-color-surface-raised);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .35);
  touch-action: none;
  user-select: none;
}

.persona-pet--dragging {
  cursor: grabbing;
}

.persona-pet__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
  cursor: grab;
}

.persona-pet--dragging .persona-pet__bar {
  cursor: grabbing;
}

.persona-pet__title {
  font-size: var(--ds-type-caption-size);
  letter-spacing: .12em;
  color: var(--ds-color-muted);
}

.persona-pet__bar-actions {
  display: inline-flex;
  gap: 4px;
}

.persona-pet__mini {
  min-width: 22px;
  min-height: 22px;
  padding: 0 4px;
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.persona-pet__mini:hover:not(:disabled) {
  color: var(--ds-color-text);
}

.persona-pet__mini:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.persona-pet__stage {
  position: relative;
  min-width: 0;
  isolation: isolate;
}

/* 生物发光氛围层：canvas 四周柔光晕 + 底部微弱青蓝渐变 */
.persona-pet__stage::before,
.persona-pet__stage::after {
  content: '';
  position: absolute;
  inset: -6% -4%;
  pointer-events: none;
  z-index: 0;
  border-radius: inherit;
}

.persona-pet__stage::before {
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .22), transparent 62%),
    radial-gradient(90% 70% at 50% 30%, rgba(122, 215, 245, .12), transparent 60%);
  filter: blur(1.2px);
}

.persona-pet__stage::after {
  box-shadow: 0 0 24px rgba(36, 150, 237, .12), inset 0 0 18px rgba(36, 150, 237, .06);
  animation: ocean-breath 4.8s ease-in-out infinite;
}

@keyframes ocean-breath {
  0%, 100% { opacity: .7; transform: scale(1) }
  50% { opacity: 1; transform: scale(1.02) }
}

.persona-pet__stage :deep(.persona) {
  position: relative;
  z-index: 1;
  padding: var(--ds-space-2);
  border: none;
  background: none;
}

.persona-pet__stage :deep(.webgl-host) {
  max-width: none;
}

.persona-pet__note {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-pet__note-hint {
  margin-left: var(--ds-space-1);
  color: var(--ds-color-text);
}

.persona-pet--collapsed {
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid rgba(122, 215, 245, .4);
  background:
    radial-gradient(circle at 50% 45%, rgba(180, 235, 255, .7), rgba(122, 215, 245, .35) 38%, rgba(36, 150, 237, .18) 62%, transparent 78%),
    var(--ds-color-surface-raised);
  box-shadow:
    0 0 0 1px rgba(36, 150, 237, .08),
    0 0 14px rgba(36, 150, 237, .28),
    0 0 36px rgba(36, 150, 237, .12),
    0 6px 18px rgba(0, 0, 0, .3);
  cursor: pointer;
  animation: orb-pulse 3.2s ease-in-out infinite;
}

@keyframes orb-pulse {
  0%, 100% { box-shadow: 0 0 0 1px rgba(36, 150, 237, .08), 0 0 14px rgba(36, 150, 237, .28), 0 0 36px rgba(36, 150, 237, .12), 0 6px 18px rgba(0, 0, 0, .3) }
  50% { box-shadow: 0 0 0 1px rgba(122, 215, 245, .14), 0 0 22px rgba(122, 215, 245, .42), 0 0 52px rgba(36, 150, 237, .22), 0 6px 18px rgba(0, 0, 0, .3) }
}

.persona-pet__orb {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
  position: relative;
}

/* 内部核心光点 */
.persona-pet__orb::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: rgba(220, 247, 255, .92);
  box-shadow: 0 0 8px 2px rgba(180, 235, 255, .7), 0 0 16px 4px rgba(122, 215, 245, .4);
  animation: orb-core 3.2s ease-in-out infinite;
}

@keyframes orb-core {
  0%, 100% { opacity: .6; transform: translate(-50%, -50%) scale(.9) }
  50% { opacity: 1; transform: translate(-50%, -50%) scale(1.1) }
}

@media (prefers-reduced-motion: reduce) {
  .persona-pet {
    background: var(--ds-color-surface-raised);
  }
}
</style>
