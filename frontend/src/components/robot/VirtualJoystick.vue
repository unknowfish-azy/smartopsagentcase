<template>
  <div class="joystick-root" :class="{ 'is-disabled': disabled }">
    <div
      ref="padRef"
      class="joystick-pad"
      :style="{ width: `${size}px`, height: `${size}px` }"
      role="application"
      :aria-label="`虚拟摇杆，当前 X ${vector.x.toFixed(2)}，Y ${vector.y.toFixed(2)}`"
      aria-roledescription="摇杆"
      tabindex="0"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @keydown="onKeyDown"
      @keyup="onKeyUp"
    >
      <span class="joystick-axis joystick-axis-x" aria-hidden="true" />
      <span class="joystick-axis joystick-axis-y" aria-hidden="true" />
      <span
        class="joystick-knob"
        :style="{ transform: `translate(-50%, -50%) translate(${knobX}px, ${knobY}px)` }"
        aria-hidden="true"
      />
    </div>
    <p class="joystick-hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

/**
 * 虚拟摇杆：鼠标 / 触屏 / 键盘（WASD）三路输入统一输出归一化向量。
 *
 * - 输出范围 [-1, 1]，死区 0.08（避免手持抖动触发微动）
 * - 松手立即归零并触发 release 事件（配合后端 ttl dead-man switch 双保险）
 * - 不内置节流：由父组件按 80ms 节流，保证「输入频率」这一策略集中在一处
 */
const props = defineProps({
  size: { type: Number, default: 132 },
  disabled: { type: Boolean, default: false },
  hint: { type: String, default: '拖动或使用 WASD 控制移动' }
})

const emit = defineEmits(['update', 'release'])

const DEAD_ZONE = 0.08
const padRef = ref(null)
const vector = ref({ x: 0, y: 0 })
const active = ref(false)
const keyState = ref({ w: false, a: false, s: false, d: false })

const knobX = computed(() => vector.value.x * (props.size / 2 - 22))
const knobY = computed(() => -vector.value.y * (props.size / 2 - 22))

function clamp(value) {
  return Math.max(-1, Math.min(1, value))
}

function applyDeadZone(x, y) {
  const magnitude = Math.hypot(x, y)
  if (magnitude < DEAD_ZONE) return { x: 0, y: 0 }
  return { x, y }
}

function emitVector(x, y) {
  const next = applyDeadZone(clamp(x), clamp(y))
  vector.value = next
  emit('update', { ...next })
}

function onPointerDown(event) {
  if (props.disabled) return
  active.value = true
  padRef.value?.setPointerCapture?.(event.pointerId)
  updateFromEvent(event)
}

function onPointerMove(event) {
  if (!active.value || props.disabled) return
  updateFromEvent(event)
}

function onPointerUp() {
  if (!active.value) return
  active.value = false
  vector.value = { x: 0, y: 0 }
  emit('release')
}

function updateFromEvent(event) {
  const rect = padRef.value?.getBoundingClientRect()
  if (!rect) return
  const radius = rect.width / 2
  const x = (event.clientX - rect.left - radius) / radius
  const y = -(event.clientY - rect.top - radius) / radius
  emitVector(x, y)
}

function onKeyDown(event) {
  if (props.disabled) return
  const key = event.key.toLowerCase()
  if (!['w', 'a', 's', 'd'].includes(key)) return
  event.preventDefault()
  if (keyState.value[key]) return
  keyState.value = { ...keyState.value, [key]: true }
  syncKeyboard()
}

function onKeyUp(event) {
  const key = event.key.toLowerCase()
  if (!['w', 'a', 's', 'd'].includes(key)) return
  if (!keyState.value[key]) return
  keyState.value = { ...keyState.value, [key]: false }
  syncKeyboard()
}

function syncKeyboard() {
  const { w, a, s, d } = keyState.value
  const x = (d ? 1 : 0) - (a ? 1 : 0)
  const y = (w ? 1 : 0) - (s ? 1 : 0)
  if (x === 0 && y === 0) {
    vector.value = { x: 0, y: 0 }
    emit('release')
    return
  }
  // 键盘斜向不加速：归一化到单位长度，避免「同时按两键更快」
  const length = Math.hypot(x, y)
  emitVector(x / length, y / length)
}

onBeforeUnmount(() => {
  vector.value = { x: 0, y: 0 }
})
</script>

<style scoped>
.joystick-root {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--ds-space-2);
}

.joystick-pad {
  position: relative;
  border: 1px solid var(--ds-color-border-strong);
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, var(--ds-color-surface-raised), var(--ds-color-surface));
  cursor: grab;
  touch-action: none;
  user-select: none;
  transition: border-color var(--ds-duration-fast) ease;
}

.joystick-pad:focus-visible {
  outline: 2px solid var(--ds-color-primary);
  outline-offset: 2px;
}

.joystick-pad:active {
  cursor: grabbing;
  border-color: var(--ds-color-primary);
}

.joystick-root.is-disabled .joystick-pad {
  cursor: not-allowed;
  opacity: 0.45;
}

.joystick-axis {
  position: absolute;
  background: var(--ds-color-border);
}

.joystick-axis-x {
  left: 8%;
  right: 8%;
  top: 50%;
  height: 1px;
}

.joystick-axis-y {
  top: 8%;
  bottom: 8%;
  left: 50%;
  width: 1px;
}

.joystick-knob {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--ds-color-primary);
  background: var(--ds-color-primary);
  box-shadow: var(--ds-shadow-2);
  pointer-events: none;
  transition: transform 80ms linear;
}

.joystick-hint {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

@media (prefers-reduced-motion: reduce) {
  .joystick-knob,
  .joystick-pad {
    transition: none;
  }
}
</style>
