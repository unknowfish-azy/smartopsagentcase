<template>
  <section class="fleet" aria-labelledby="fleet-title">
    <header class="fleet-head">
      <div>
        <p class="fleet-eyebrow">FLEET · 统一接入</p>
        <h3 id="fleet-title">设备态势</h3>
      </div>
      <span class="fleet-count">{{ onlineCount }} / {{ devices.length }} 在线</span>
    </header>

    <div v-if="!devices.length" class="fleet-empty">尚未登记巡检设备</div>

    <div v-else class="fleet-grid">
      <article
        v-for="card in cards"
        :key="card.key"
        class="fleet-card"
        :class="{ selected: card.key === selectedKey, offline: !card.online }"
        @click="emit('select', card.key)"
      >
        <div class="card-top">
          <span class="card-glyph">{{ card.glyph }}</span>
          <div class="card-title">
            <strong>{{ card.name }}</strong>
            <span class="card-key">{{ card.key }}</span>
          </div>
          <span class="mode-pill" :class="card.modeClass">{{ card.modeLabel }}</span>
        </div>

        <div class="card-battery">
          <div class="battery-track">
            <span class="battery-fill" :class="card.batteryClass" :style="{ width: `${card.battery ?? 0}%` }"></span>
          </div>
          <span class="battery-text">{{ card.battery === null ? '电量 —' : `电量 ${card.battery}%` }}</span>
        </div>

        <dl class="card-meta">
          <div><dt>控制桥</dt><dd :class="{ good: card.online, bad: !card.online }">{{ card.online ? '已连接' : '未连接' }}</dd></div>
          <div><dt>位姿</dt><dd>{{ card.poseText }}</dd></div>
          <div><dt>心跳</dt><dd>{{ card.heartbeatText }}</dd></div>
        </dl>

        <div class="card-actions">
          <button type="button" class="ghost-btn" @click.stop="emit('select', card.key)">
            {{ card.key === selectedKey ? '当前设备' : '切换' }}
          </button>
          <button
            type="button"
            class="danger-btn"
            :disabled="!card.online || card.key !== selectedKey"
            :title="card.key !== selectedKey ? '请先切换到该设备' : '立即急停'"
            @click.stop="emit('estop', card.key)"
          >急停</button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  devices: { type: Array, default: () => [] },
  states: { type: Object, default: () => ({}) },
  selectedKey: { type: String, default: '' }
})

const emit = defineEmits(['select', 'estop'])

const FORM_GLYPHS = { CAR: '车', DOG: '犬', SPIDER: '蛛', ROBOT: '人' }
const MODE_LABELS = {
  OFFLINE: '离线',
  IDLE: '空闲',
  AUTONOMOUS: '自主巡检',
  HUMAN_CONTROL: '人工操控',
  E_STOP: '急停',
  FAULT: '故障'
}

const now = ref(Date.now())
let timer = null

onMounted(() => {
  timer = window.setInterval(() => { now.value = Date.now() }, 5000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

function batteryPercent(raw) {
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  return Math.round(value <= 1 ? value * 100 : value)
}

const cards = computed(() => props.devices.map((device) => {
  const state = props.states[device.deviceKey] || {}
  const telemetry = state.telemetry
  const pose = telemetry?.pose
  const online = Boolean(state.bridgeConnected)
  const mode = state.mode || 'OFFLINE'
  const battery = batteryPercent(telemetry?.battery)
  const x = Number(pose?.x)
  const y = Number(pose?.y)
  const age = state.telemetryAt ? Math.max(0, Math.round((now.value - state.telemetryAt) / 1000)) : null
  return {
    key: device.deviceKey,
    name: device.name || device.deviceKey,
    glyph: FORM_GLYPHS[device.formFactor] || '机',
    online,
    modeLabel: MODE_LABELS[mode] || mode,
    modeClass: mode === 'E_STOP' || mode === 'FAULT' ? 'danger' : online ? 'good' : 'muted',
    battery,
    batteryClass: battery === null ? 'muted' : battery < 15 ? 'danger' : battery < 30 ? 'warn' : 'good',
    poseText: Number.isFinite(x) && Number.isFinite(y) ? `${x.toFixed(2)}, ${y.toFixed(2)}` : '—',
    heartbeatText: age === null ? '—' : age <= 5 ? `${age}s 前` : `${age}s 前（超时）`,
    stale: age !== null && age > 5
  }
}))

const onlineCount = computed(() => cards.value.filter(card => card.online).length)
</script>

<style scoped>
.fleet {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.fleet-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.fleet-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.fleet-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.fleet-count {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  font-variant-numeric: tabular-nums;
}

.fleet-empty {
  padding: var(--ds-space-4);
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  text-align: center;
}

.fleet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: var(--ds-space-2);
}

.fleet-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  cursor: pointer;
  transition: border-color var(--ds-duration-fast) ease, transform var(--ds-duration-fast) ease;
}

.fleet-card:hover {
  border-color: var(--ds-color-border-strong);
  transform: translateY(-1px);
}

.fleet-card.selected {
  border-color: var(--ds-color-primary);
  box-shadow: inset 0 0 0 1px rgba(36, 150, 237, 0.35);
}

.fleet-card.offline {
  opacity: 0.72;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-glyph {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: rgba(36, 150, 237, 0.14);
  color: var(--ds-color-primary);
  font-size: var(--ds-font-sm);
  font-weight: 600;
}

.card-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.card-title strong {
  overflow: hidden;
  font-size: var(--ds-font-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-key {
  overflow: hidden;
  color: var(--ds-color-muted);
  font-family: var(--ds-font-mono);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-pill {
  padding: 2px 8px;
  border-radius: var(--ds-radius-pill);
  font-size: 10px;
  white-space: nowrap;
}

.mode-pill.good { background: rgba(58, 190, 132, 0.16); color: #6ddcab; }
.mode-pill.danger { background: rgba(224, 100, 110, 0.18); color: #ff9aa4; }
.mode-pill.muted { background: rgba(120, 140, 160, 0.14); color: var(--ds-color-muted); }

.card-battery {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.battery-track {
  height: 5px;
  border-radius: var(--ds-radius-pill);
  background: rgba(120, 140, 160, 0.18);
  overflow: hidden;
}

.battery-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width var(--ds-duration-base) ease;
}

.battery-fill.good { background: #3abe84; }
.battery-fill.warn { background: #e3a008; }
.battery-fill.danger { background: #e0646e; }
.battery-fill.muted { background: #526475; }

.battery-text {
  color: var(--ds-color-muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.card-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  margin: 0;
}

.card-meta div {
  min-width: 0;
}

.card-meta dt {
  color: var(--ds-color-muted);
  font-size: 10px;
}

.card-meta dd {
  margin: 1px 0 0;
  overflow: hidden;
  color: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta dd.good { color: #6ddcab; }
.card-meta dd.bad { color: var(--ds-color-warning); }

.card-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}

.ghost-btn,
.danger-btn {
  flex: 1;
  padding: 4px 8px;
  border-radius: var(--ds-radius-sm);
  font-size: var(--ds-font-xs);
  cursor: pointer;
  transition: border-color var(--ds-duration-fast) ease, background-color var(--ds-duration-fast) ease;
}

.ghost-btn {
  border: 1px solid var(--ds-color-border);
  background: transparent;
  color: var(--ds-color-muted);
}

.ghost-btn:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.danger-btn {
  border: 1px solid rgba(224, 100, 110, 0.4);
  background: rgba(224, 100, 110, 0.12);
  color: #ff9aa4;
}

.danger-btn:disabled {
  border-color: var(--ds-color-border);
  background: transparent;
  color: var(--ds-color-muted);
  cursor: not-allowed;
}
</style>
