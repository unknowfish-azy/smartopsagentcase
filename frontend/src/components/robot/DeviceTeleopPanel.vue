<template>
  <div class="teleop-panel">
    <header class="teleop-head">
      <div class="teleop-id">
        <span class="teleop-name">{{ device?.name || '未选择设备' }}</span>
        <span class="teleop-tag">{{ profile.label }}</span>
        <span class="teleop-tag teleop-tag-muted">{{ profile.kinematics }}</span>
      </div>
      <span class="teleop-state" :class="stateClass">{{ stateText }}</span>
    </header>

    <p v-if="!profile.known" class="teleop-warn">
      该形态未在能力清单登记，已按最保守的差速模型渲染（前进 + 自转），不可横移。
    </p>

    <div class="teleop-body">
      <VirtualJoystick
        :disabled="locked"
        :hint="joystickHint"
        @update="onJoystickUpdate"
        @release="onJoystickRelease"
      />

      <div class="teleop-side">
        <div v-if="!strafes" class="teleop-note">
          <span class="teleop-note-title">差速遥控</span>
          <span class="teleop-note-text">摇杆上下＝前进/后退，左右＝原地转向；该形态无横移执行器。</span>
        </div>

        <div v-if="strafes" class="teleop-note">
          <span class="teleop-note-title">全向遥控</span>
          <span class="teleop-note-text">摇杆上下＝前进/后退，左右＝横移；自转用下方左右键。</span>
        </div>

        <div v-if="strafes" class="teleop-yaw" role="group" aria-label="原地转向">
          <button
            type="button"
            class="yaw-btn"
            :disabled="locked"
            aria-label="左转"
            @pointerdown="startYaw(-1)"
            @pointerup="stopYaw"
            @pointercancel="stopYaw"
            @pointerleave="stopYaw"
            @keydown.enter.prevent="startYaw(-1)"
            @keyup.enter.prevent="stopYaw"
            @blur="stopYaw"
          >
            ⟲ 左转
          </button>
          <button
            type="button"
            class="yaw-btn"
            :disabled="locked"
            aria-label="右转"
            @pointerdown="startYaw(1)"
            @pointerup="stopYaw"
            @pointercancel="stopYaw"
            @pointerleave="stopYaw"
            @keydown.enter.prevent="startYaw(1)"
            @keyup.enter.prevent="stopYaw"
            @blur="stopYaw"
          >
            右转 ⟳
          </button>
        </div>

        <label v-if="profile.gaits.length" class="teleop-gait">
          <span class="teleop-gait-label">步态</span>
          <select :disabled="locked" :value="gait" @change="onGaitChange">
            <option v-for="item in profile.gaits" :key="item" :value="item">{{ GAIT_LABELS[item] || item }}</option>
          </select>
        </label>
      </div>
    </div>

    <p class="teleop-foot">
      {{ profile.maxSpeedNote }}｜限速 {{ Math.round(profile.maxSpeed.linear * 100) }}%
      <span v-if="unsupportedText" class="teleop-unsupported">｜{{ unsupportedText }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import VirtualJoystick from './VirtualJoystick.vue'
import {
  buildMoveParams,
  createCommandPacer,
  isIdleIntent,
  mapJoystickToAxes,
  resolveTeleopProfile,
  TELEOP_INTERVAL_MS
} from '../../utils/teleopCapabilities.js'

/**
 * 统一遥控面板：**只读能力清单**渲染，不判断设备类型。
 *
 * 输出契约：`command` 事件携带后端 MOVE 的完整参数（x/y/theta/speed/ttlMs[/gait]），
 * 由父组件负责通道（WS / REST）与续传；本组件只管「意图 → 合法参数」。
 */
const props = defineProps({
  device: { type: Object, default: null },
  /** 未进入人工态、桥未连接、急停中时为 true */
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['command', 'release'])

const GAIT_LABELS = Object.freeze({ TROT: '小跑 (TROT)', WALK: '踱步 (WALK)', STAND: '站立 (STAND)' })

const profile = computed(() => resolveTeleopProfile(props.device))
const strafes = computed(() => profile.value.axes.includes('lateral'))
const locked = computed(() => props.disabled || !profile.value.teleopCapable)

const gait = ref('')
watch(
  () => profile.value.formFactor,
  () => {
    gait.value = profile.value.gaits[0] || ''
  },
  { immediate: true }
)

const joystickHint = computed(() =>
  strafes.value ? '拖动或 WASD：上下前进、左右横移' : '拖动或 WASD：上下前进、左右转向'
)

const stateText = computed(() => {
  if (!profile.value.teleopCapable) return profile.value.reason || '不可遥控'
  return props.disabled ? '未就绪' : '可遥控'
})

const stateClass = computed(() => {
  if (!profile.value.teleopCapable) return 'is-blocked'
  return props.disabled ? 'is-idle' : 'is-ready'
})

const unsupportedText = computed(() => {
  const axes = profile.value.axes
  const missing = []
  if (!axes.includes('lateral')) missing.push('横移')
  if (!axes.includes('yaw')) missing.push('自转')
  if (!axes.includes('gait')) missing.push('步态')
  return missing.length ? `该形态不支持：${missing.join(' / ')}` : ''
})

const pacer = createCommandPacer(TELEOP_INTERVAL_MS)
const intent = ref({ forward: 0, lateral: 0, yaw: 0 })
const yawHeld = ref(0)
let yawTimer = null

function pushIntent() {
  const { params, unsupportedAxes } = buildMoveParams(profile.value, intent.value, {
    gait: gait.value || undefined
  })
  emit('command', { ...params, unsupportedAxes })
}

function onJoystickUpdate(vector) {
  if (locked.value) return
  const mapped = mapJoystickToAxes(profile.value, vector)
  intent.value = {
    forward: mapped.forward,
    lateral: mapped.lateral,
    yaw: yawHeld.value !== 0 ? yawHeld.value : mapped.yaw
  }
  if (isIdleIntent(intent.value)) return
  if (!pacer.allow(Date.now())) return
  pushIntent()
}

function onJoystickRelease() {
  if (locked.value) return
  intent.value = { forward: 0, lateral: 0, yaw: 0 }
  stopYaw()
  emit('release')
}

function startYaw(direction) {
  if (locked.value) return
  yawHeld.value = direction
  intent.value = { ...intent.value, yaw: direction }
  if (pacer.allow(Date.now())) pushIntent()
  if (yawTimer) window.clearInterval(yawTimer)
  // 按住期间持续续传，与摇杆共用 80ms 节流口径
  yawTimer = window.setInterval(() => {
    if (locked.value || yawHeld.value === 0) return
    if (!pacer.allow(Date.now())) return
    pushIntent()
  }, TELEOP_INTERVAL_MS)
}

function stopYaw() {
  if (yawTimer) {
    window.clearInterval(yawTimer)
    yawTimer = null
  }
  if (yawHeld.value === 0) return
  yawHeld.value = 0
  intent.value = { ...intent.value, yaw: 0 }
  emit('release')
}

function onGaitChange(event) {
  gait.value = event.target.value
  if (!isIdleIntent(intent.value)) pushIntent()
}

onBeforeUnmount(() => {
  if (yawTimer) window.clearInterval(yawTimer)
  yawTimer = null
})
</script>

<style scoped>
.teleop-panel {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
}

.teleop-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.teleop-id {
  display: flex;
  align-items: center;
  gap: var(--ds-space-2);
  min-width: 0;
}

.teleop-name {
  font-size: var(--ds-font-sm);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.teleop-tag {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--ds-color-border);
  font-size: var(--ds-font-xs);
  color: var(--ds-color-text);
}

.teleop-tag-muted {
  color: var(--ds-color-muted);
}

.teleop-state {
  font-size: var(--ds-font-xs);
}

.teleop-state.is-ready {
  color: var(--ds-color-success, #22c55e);
}

.teleop-state.is-idle {
  color: var(--ds-color-muted);
}

.teleop-state.is-blocked {
  color: var(--ds-color-danger, #ef4444);
}

.teleop-warn {
  margin: 0;
  padding: var(--ds-space-2) var(--ds-space-3);
  border-radius: var(--ds-radius-sm, 6px);
  background: color-mix(in srgb, var(--ds-color-warning, #f59e0b) 12%, transparent);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
}

.teleop-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space-4);
}

.teleop-side {
  display: flex;
  flex: 1 1 180px;
  flex-direction: column;
  gap: var(--ds-space-2);
  min-width: 160px;
}

.teleop-note {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.teleop-note-title {
  font-size: var(--ds-font-xs);
  font-weight: 600;
}

.teleop-note-text {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.5;
}

.teleop-yaw {
  display: flex;
  gap: var(--ds-space-2);
}

.yaw-btn {
  flex: 1;
  padding: var(--ds-space-2) var(--ds-space-3);
  border-radius: var(--ds-radius-sm, 6px);
  border: 1px solid var(--ds-color-border-strong);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
  cursor: pointer;
  touch-action: none;
  user-select: none;
}

.yaw-btn:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
}

.yaw-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.teleop-gait {
  display: flex;
  align-items: center;
  gap: var(--ds-space-2);
  font-size: var(--ds-font-xs);
  color: var(--ds-color-muted);
}

.teleop-gait select {
  flex: 1;
  padding: 4px 6px;
  border-radius: var(--ds-radius-sm, 6px);
  border: 1px solid var(--ds-color-border-strong);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
}

.teleop-foot {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.5;
}

.teleop-unsupported {
  color: var(--ds-color-warning, #f59e0b);
}
</style>
