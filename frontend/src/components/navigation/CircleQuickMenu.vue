<template>
  <div
    ref="root"
    class="circle-menu"
    :data-open="open"
    :data-shake="shake"
    :data-reduced="reduced"
    :data-variant="variant"
    :style="{ '--ring-size': `${size}px`, '--item-size': `${itemSize}px` }"
    @keydown.esc.stop="close(true)"
    @focusout="onFocusOut"
  >
    <span class="circle-menu__orbit" aria-hidden="true" />

    <ul
      id="circle-quick-menu-items"
      class="circle-menu__items"
      role="menu"
      :aria-label="label"
      :aria-hidden="!open"
      :inert="!open || null"
      @keydown="onMenuKeydown"
    >
      <li v-for="(item, index) in items" :key="item.to" class="circle-menu__slot" role="none" :style="slotStyle(index)">
        <RouterLink
          :ref="el => setItemRef(el, index)"
          class="circle-menu__node"
          :to="item.to"
          role="menuitem"
          :tabindex="open ? 0 : -1"
          :aria-label="`${item.cn} / ${item.en}`"
          @focus="active = index"
          @mouseenter="active = index"
          @click="close(false)"
        >
          <component :is="item.icon" class="circle-menu__icon" aria-hidden="true" />
          <span class="circle-menu__label" aria-hidden="true">
            <b>{{ item.cn }}</b><small>{{ item.en }}</small>
          </span>
        </RouterLink>
      </li>
    </ul>

    <button
      ref="trigger"
      type="button"
      class="circle-menu__trigger"
      :class="`circle-menu__trigger--${variant}`"
      :aria-expanded="open"
      aria-controls="circle-quick-menu-items"
      :aria-label="open ? `收起${label}` : `展开${label}`"
      @click="toggle"
    >
      <template v-if="variant === 'orb'">
        <!-- 悬浮球形态：与桌宠 AI 球同一视觉语言，嵌入快捷操作卡片 -->
        <span class="circle-menu__orb-stars" aria-hidden="true">
          <span v-for="index in 10" :key="index" class="circle-menu__orb-star" :style="{ '--i': index - 1 }" />
        </span>
        <span class="circle-menu__orb-core" aria-hidden="true">{{ open ? '×' : 'AI' }}</span>
      </template>
      <template v-else>
        <span class="circle-menu__trigger-ring" aria-hidden="true" />
        <component :is="open ? Close : Grid" class="circle-menu__trigger-icon" aria-hidden="true" />
      </template>
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Close, Grid } from '@element-plus/icons-vue'
import { visualMode } from '../../visual/visualMode.js'

const props = defineProps({
  items: { type: Array, required: true },
  label: { type: String, default: '快捷操作' },
  size: { type: Number, default: 160 },
  /** 触发按钮形态：grid 网格图标（原样式） / orb 悬浮球（与桌宠 AI 球融合） */
  variant: { type: String, default: 'grid' }
})

const itemSize = 36
const root = ref(null)
const trigger = ref(null)
const open = ref(false)
const shake = ref(false)
const active = ref(0)
const itemRefs = ref([])
let shakeTimer = 0

const radius = computed(() => Math.max(props.size / 2 - itemSize / 2 - 10, 0))
/** 视觉档与系统偏好任一要求减少动态，就只保留显隐，不做扇出位移。 */
const reduced = computed(() => visualMode.value !== 'balanced'
  || (typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches))

function slotStyle(index) {
  const angle = (2 * Math.PI * index) / props.items.length - Math.PI / 2
  return {
    '--tx': `${Math.round(Math.cos(angle) * radius.value)}px`,
    '--ty': `${Math.round(Math.sin(angle) * radius.value)}px`,
    '--i': index,
    '--n': props.items.length
  }
}

function setItemRef(el, index) {
  itemRefs.value[index] = el
}

function focusItem(index) {
  const node = itemRefs.value[index]?.$el || itemRefs.value[index]
  node?.focus?.()
}

function toggle(event) {
  if (open.value) {
    close(false)
    return
  }
  open.value = true
  active.value = 0
  // 键盘（Enter/Space）唤出时把焦点交给首项；鼠标点击保持焦点在触发器
  if (event?.detail === 0) nextTick(() => focusItem(0))
}

function close(restoreFocus = false) {
  if (!open.value) return
  open.value = false
  active.value = 0
  shake.value = true
  window.clearTimeout(shakeTimer)
  shakeTimer = window.setTimeout(() => { shake.value = false }, 360)
  if (restoreFocus) nextTick(() => trigger.value?.focus())
}

function onMenuKeydown(event) {
  if (!open.value) return
  const total = props.items.length
  let next = active.value
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (active.value + 1) % total
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (active.value - 1 + total) % total
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = total - 1
  else return
  event.preventDefault()
  active.value = next
  focusItem(next)
}

function onFocusOut(event) {
  if (!open.value) return
  if (root.value && root.value.contains(event.relatedTarget)) return
  close(false)
}

function onDocumentPointerDown(event) {
  if (!open.value) return
  if (root.value?.contains(event.target)) return
  close(false)
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown, true))
onBeforeUnmount(() => {
  window.clearTimeout(shakeTimer)
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
})
</script>

<style scoped>
.circle-menu {
  position: relative;
  display: grid;
  place-items: center;
  width: calc(var(--ring-size) + 40px);
  height: calc(var(--ring-size) + 40px);
  margin: 0 auto;
  isolation: isolate;
}

.circle-menu__orbit {
  position: absolute;
  width: calc(var(--ring-size) - var(--item-size) - 20px);
  height: calc(var(--ring-size) - var(--item-size) - 20px);
  border: 1px dashed color-mix(in srgb, var(--smart-primary-strong) 30%, transparent);
  border-radius: 50%;
  opacity: 0;
  transform: scale(0.82);
  transition: opacity 260ms ease, transform 420ms cubic-bezier(.22, 1, .36, 1);
  pointer-events: none;
}
.circle-menu[data-open='true'] .circle-menu__orbit { opacity: .75; transform: scale(1); }

.circle-menu__items {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  pointer-events: none;
}
.circle-menu[data-open='true'] .circle-menu__items { pointer-events: auto; }

.circle-menu__slot {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.circle-menu__node {
  position: relative;
  display: grid;
  place-items: center;
  width: var(--item-size);
  height: var(--item-size);
  border: 1px solid var(--smart-border);
  border-radius: 50%;
  background: var(--smart-surface-raised);
  color: var(--smart-primary-strong);
  text-decoration: none;
  opacity: 0;
  transform: translate(var(--tx, 0), var(--ty, 0)) scale(.55);
  transition:
    transform 320ms cubic-bezier(.22, 1.35, .36, 1),
    opacity 160ms ease,
    border-color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease;
  transition-delay: calc((var(--n) - var(--i)) * 16ms);
}
.circle-menu[data-open='true'] .circle-menu__node {
  opacity: 1;
  transform: translate(var(--tx, 0), var(--ty, 0)) scale(1);
  transition-delay: calc(var(--i) * 26ms);
}
.circle-menu__node:hover,
.circle-menu__node:focus-visible {
  border-color: var(--smart-primary-strong);
  background: color-mix(in srgb, var(--smart-primary-strong) 15%, var(--smart-surface-raised));
  box-shadow: 0 6px 18px color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  outline: none;
}
.circle-menu[data-open='true'] .circle-menu__node:hover,
.circle-menu[data-open='true'] .circle-menu__node:focus-visible {
  transform: translate(var(--tx, 0), var(--ty, 0)) scale(1.1);
}
.circle-menu__icon { width: 16px; height: 16px; }

.circle-menu__label {
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  display: flex;
  align-items: baseline;
  gap: 5px;
  padding: 3px 7px;
  border: 1px solid var(--smart-border-strong);
  border-radius: 6px;
  background: var(--smart-surface);
  box-shadow: 0 8px 20px rgba(0, 0, 0, .35);
  white-space: nowrap;
  opacity: 0;
  transform: translateX(-50%) translateY(-3px);
  transition: opacity 140ms ease, transform 140ms ease;
  pointer-events: none;
}
.circle-menu__label b { color: var(--smart-text); font: 400 10px var(--font-cn); }
.circle-menu__label small { color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .06em; }
.circle-menu__node:hover .circle-menu__label,
.circle-menu__node:focus-visible .circle-menu__label {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.circle-menu__trigger {
  position: relative;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 1px solid var(--smart-primary-strong);
  border-radius: 50%;
  background: color-mix(in srgb, var(--smart-primary-strong) 14%, var(--smart-surface-raised));
  color: var(--smart-primary-strong);
  cursor: pointer;
  box-shadow: 0 10px 26px rgba(0, 0, 0, .32);
  transition: transform 200ms cubic-bezier(.22, 1, .36, 1), background-color 200ms ease, color 200ms ease, box-shadow 200ms ease;
}
.circle-menu__trigger:hover { transform: scale(1.06); }
.circle-menu__trigger:focus-visible { outline: 2px solid var(--smart-focus-ring, var(--smart-primary-strong)); outline-offset: 3px; }
.circle-menu[data-open='true'] .circle-menu__trigger {
  background: var(--smart-primary-strong);
  color: var(--smart-bg);
  box-shadow: 0 12px 30px color-mix(in srgb, var(--smart-primary-strong) 34%, transparent);
}
.circle-menu__trigger-icon { width: 18px; height: 18px; }

/* ===== orb 形态：嵌入卡片的 AI 悬浮球（替代桌面悬浮快捷） ===== */
.circle-menu__trigger--orb {
  width: 82px;
  height: 82px;
  border-color: color-mix(in srgb, var(--smart-primary-strong) 62%, transparent);
  background:
    radial-gradient(circle at 32% 26%,
      color-mix(in srgb, var(--smart-primary-strong) 30%, transparent),
      color-mix(in srgb, var(--smart-primary) 12%, var(--smart-surface-raised)) 58%,
      var(--smart-surface-raised) 82%);
  box-shadow:
    0 0 0 7px color-mix(in srgb, var(--smart-primary-strong) 6%, transparent),
    0 16px 38px rgba(0, 0, 0, .4);
}
.circle-menu__trigger--orb::after {
  content: '';
  position: absolute;
  inset: 3px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 24%, transparent);
  border-radius: 50%;
  pointer-events: none;
}
.circle-menu__trigger--orb:hover { transform: scale(1.04); }
.circle-menu[data-open='true'] .circle-menu__trigger--orb {
  background: var(--smart-primary-strong);
  box-shadow:
    0 0 0 9px color-mix(in srgb, var(--smart-primary-strong) 12%, transparent),
    0 16px 40px color-mix(in srgb, var(--smart-primary-strong) 38%, transparent);
}
.circle-menu__orb-core {
  position: relative;
  z-index: 1;
  color: var(--smart-primary-strong);
  font: 600 16px/1 var(--font-mono);
  letter-spacing: .12em;
  transition: color 200ms ease;
}
.circle-menu[data-open='true'] .circle-menu__orb-core { color: var(--smart-bg); }
.circle-menu__orb-stars {
  position: absolute;
  inset: -12px;
  border-radius: 50%;
  animation: circle-menu-orbit 26s linear infinite;
  pointer-events: none;
}
.circle-menu__orb-star {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 3px;
  height: 3px;
  margin: -1.5px;
  border-radius: 50%;
  background: var(--smart-primary-strong);
  opacity: .45;
  transform: rotate(calc(var(--i) * 36deg)) translateY(-47px);
}
.circle-menu__orb-star:nth-child(odd) { opacity: .22; }
.circle-menu[data-open='true'] .circle-menu__orb-stars { animation-duration: 14s; }
.circle-menu[data-open='true'] .circle-menu__orb-star { opacity: .8; }

.circle-menu__trigger-ring {
  position: absolute;
  inset: -7px;
  border: 1px dashed color-mix(in srgb, var(--smart-primary-strong) 38%, transparent);
  border-radius: 50%;
  animation: circle-menu-orbit 12s linear infinite;
  pointer-events: none;
}
.circle-menu[data-open='true'] .circle-menu__trigger-ring {
  border-color: color-mix(in srgb, var(--smart-primary-strong) 65%, transparent);
  animation-duration: 6s;
}

.circle-menu[data-shake='true'] .circle-menu__trigger { animation: circle-menu-shake 320ms linear; }
.circle-menu[data-shake='true'] .circle-menu__node { filter: blur(1px); }

@keyframes circle-menu-orbit {
  to { transform: rotate(360deg); }
}
@keyframes circle-menu-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(2px); }
  40% { transform: translateX(-2px); }
  60% { transform: translateX(2px); }
  80% { transform: translateX(-2px); }
}

@media (prefers-reduced-motion: reduce) {
  .circle-menu__node,
  .circle-menu__orbit,
  .circle-menu__trigger,
  .circle-menu__trigger-ring,
  .circle-menu__orb-stars,
  .circle-menu__label { transition: none; animation: none; }
  .circle-menu[data-shake='true'] .circle-menu__trigger { animation: none; }
}
.circle-menu[data-reduced='true'] .circle-menu__node,
.circle-menu[data-reduced='true'] .circle-menu__orbit,
.circle-menu[data-reduced='true'] .circle-menu__trigger,
.circle-menu[data-reduced='true'] .circle-menu__trigger-ring,
.circle-menu[data-reduced='true'] .circle-menu__orb-stars { transition: none; animation: none; }
.circle-menu[data-reduced='true'] .circle-menu__node { transition-delay: 0s; }
</style>
