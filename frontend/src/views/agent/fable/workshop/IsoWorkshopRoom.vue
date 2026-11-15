<template>
  <div class="ws-room" :class="{ 'is-rehearsal': isRehearsal, 'is-stale': stale, 'is-narrow': narrow }">
    <WorkshopFallbackList
      v-if="narrow"
      :tools="tools"
      :activity="activity"
      :rehearsal="isRehearsal"
    />

    <svg
      v-else
      class="ws-room-svg"
      :viewBox="viewBoxStr"
      role="group"
      aria-label="Agent 工坊等距视图：六张工具工位环绕中央闭环轨道"
    >
      <g :style="breathStyle">
        <!-- 后墙 × 2 + 地板（surface 令牌，双主题同构） -->
        <polygon class="ws-wall" :points="wallRight" />
        <polygon class="ws-wall ws-wall--left" :points="wallLeft" />
        <polygon class="ws-floor" :points="floorPoints" />

        <!-- 墙屏（E4）：近 N 轮闭环耗时真实折线 -->
        <g :transform="`translate(${layout.screen.sx} ${layout.screen.sy})`">
          <polygon
            class="ws-screen-face"
            :points="`0,0 ${screenDx},${screenDy} ${screenDx},${screenDy - layout.screen.height} 0,${-layout.screen.height}`"
          />
          <text class="ws-screen-title" :x="screenDx / 2" :y="-layout.screen.height + 12">
            LOOP DURATION · 近{{ sparkline.length || 0 }}轮
          </text>
          <polyline v-if="sparkPoints" class="ws-screen-line" :points="sparkPoints" />
          <text v-else class="ws-screen-empty" :x="screenDx / 2" :y="-layout.screen.height / 2">
            NO DATA
          </text>
        </g>

        <!-- 服务器机柜（E5）：LED 随拉取成功心跳明灭，断连常灭 -->
        <g :transform="`translate(${layout.cabinet.sx} ${layout.cabinet.sy})`">
          <polygon class="ws-cab-top" points="0,-64 26,-51 0,-38 -26,-51" />
          <polygon class="ws-cab-left" points="-26,-51 0,-38 0,0 -26,-13" />
          <polygon class="ws-cab-right" points="0,-38 26,-51 26,-13 0,0" />
          <circle
            v-for="(led, i) in layout.cabinet.leds"
            :key="i"
            class="ws-cab-led"
            :class="{ 'is-on': ledsOn }"
            :cx="led.dx"
            :cy="led.dy"
            r="2.4"
          />
        </g>

        <!-- 中央闭环轨道（E3）：四站菱形 + 事件徽章逐站移动 -->
        <path class="ws-track" :d="trackPath" />
        <g v-for="station in layout.track" :key="station.en">
          <circle
            class="ws-station"
            :class="{ 'is-active': station.index === badgeTo && badgeSettled }"
            :cx="station.sx"
            :cy="station.sy"
            r="3.4"
          />
          <text class="ws-station-label" :x="station.sx" :y="station.sy + 14">{{ station.cn }}</text>
        </g>
        <circle class="ws-badge" :class="{ 'is-resting': badgeSettled }" :cx="badgePos.x" :cy="badgePos.y" r="4.5" />

        <!-- 缆线（E2）：轨道中心 → 工位；有事件才有光点 -->
        <IsoCable
          v-for="desk in layout.desks"
          :key="`cable-${desk.id}`"
          :from="layout.trackCenter"
          :to="desk"
          :tone="desk.tone"
          :progress="pulseProgress(desk.id)"
        />

        <!-- 工位（E1）：按画家序渲染 -->
        <IsoDesk
          v-for="desk in layout.desks"
          :key="desk.id"
          :desk="desk"
          :state="deskState(desk.id)"
          :info="infoByDesk.get(desk.id) || null"
          :gaze="gazeOf(desk)"
          @select="onDeskSelect"
        />
      </g>

      <text v-if="isRehearsal" class="ws-watermark" :x="watermarkPos.x" :y="watermarkPos.y">
        REHEARSAL · 演练构成
      </text>
    </svg>

    <p class="ws-room-foot">
      <span class="mono-label">ISO WORKSHOP · Agent 工坊</span>
      <span :class="isRehearsal ? 'ws-state ws-state--off' : 'ws-state ws-state--live'">
        {{ isRehearsal ? 'REHEARSAL · 无实时闭环数据' : 'LIVE · 数据源 decision-loops' }}
      </span>
      <span class="ws-state">无事件 = 静默 · 禁假繁忙</span>
    </p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import IsoDesk from './IsoDesk.vue'
import IsoCable from './IsoCable.vue'
import WorkshopFallbackList from './WorkshopFallbackList.vue'
import { subscribe } from '../../../../visual/motionScheduler.js'
import {
  buildWorkshop,
  deskActivity,
  sparklineFromLoops,
  isNarrowViewport,
  NARROW_VIEWPORT_MAX
} from './workshopLayout.js'

const PULSE_MS = 650
const LIT_MS = 900
const BADGE_MS = 450

const props = defineProps({
  tools: { type: Array, required: true },
  loopSteps: { type: Array, required: true },
  /** 真实闭环列表（list 接口返回），工坊不另拉数据（门禁 10：切视图不换轴） */
  loops: { type: Array, default: () => [] },
  loopsStatus: { type: String, default: 'loading' },
  /** 最近一次成功拉取时间戳（E5 心跳）；0 = 无心跳 */
  heartbeatAt: { type: Number, default: 0 },
  reduced: { type: Boolean, default: false },
  stale: { type: Boolean, default: false }
})

const emit = defineEmits(['select'])

/* ---------------------------- 布局与数据派生 ---------------------------- */

const layout = computed(() => buildWorkshop(props.tools, props.loopSteps))
const viewBoxStr = computed(() => {
  const v = layout.value.viewBox
  return `${v.x} ${v.y} ${v.width} ${v.height}`
})
const isRehearsal = computed(() => props.loopsStatus !== 'live')
const activity = computed(() => (isRehearsal.value ? [] : deskActivity(props.loops)))
const infoByDesk = computed(() => new Map(activity.value.map(item => [item.deskId, item])))
const activityKey = computed(() => activity.value.map(a => `${a.deskId}:${a.loopId}:${a.stage}`).join('|'))

const floorPoints = computed(() => layout.value.floor.map(p => `${p.sx},${p.sy}`).join(' '))
const wallRight = computed(() => {
  const [o, xEdge] = layout.value.floor
  return `${o.sx},${o.sy} ${xEdge.sx},${xEdge.sy} ${xEdge.sx},${xEdge.sy - WALL_H} ${o.sx},${o.sy - WALL_H}`
})
const wallLeft = computed(() => {
  const [o, , , yEdge] = layout.value.floor
  return `${o.sx},${o.sy} ${yEdge.sx},${yEdge.sy} ${yEdge.sx},${yEdge.sy - WALL_H} ${o.sx},${o.sy - WALL_H}`
})
const WALL_H = 72

const screenDx = computed(() => layout.value.screen.lenTiles * layout.value.unit.tw)
const screenDy = computed(() => layout.value.screen.lenTiles * layout.value.unit.th)

const sparkline = computed(() => sparklineFromLoops(props.loops, 12))
const sparkPoints = computed(() => {
  const values = sparkline.value
  if (values.length < 2) return ''
  const inset = 0.1
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return values
    .map((v, i) => {
      const f = inset + (1 - inset * 2) * (i / (values.length - 1))
      // 注意：polyline 渲染在已 translate(screen.sx, screen.sy) 的组内，这里用组内局部坐标
      const x = f * screenDx.value
      const y = f * screenDy.value - 10 - (layout.value.screen.height - 22) * ((v - min) / span)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

const watermarkPos = computed(() => ({
  x: layout.value.viewBox.x + layout.value.viewBox.width / 2,
  y: layout.value.viewBox.y + layout.value.viewBox.height - 14
}))

/* ---------------------------- 动画状态（motionScheduler 统一调度） ---------------------------- */

const nowTick = ref(0)
const litIds = ref(new Set())
const litExpireAt = ref(0)
const pulses = ref([])
const badge = reactive({ from: 0, to: -1, start: 0 })
const ledsFlash = ref(false)
const breathY = ref(0)
let ledsTimer = 0

const badgeSettled = computed(() => badge.to < 0 || nowTick.value - badge.start >= BADGE_MS)
const badgeTo = computed(() => Math.max(0, badge.to))
const badgePos = computed(() => {
  const track = layout.value.track
  if (!track.length) return { x: 0, y: 0 }
  const a = track[Math.max(0, badge.from)] || track[0]
  const b = track[badgeTo.value] || track[0]
  const t = badgeSettled.value ? 1 : easeInOut((nowTick.value - badge.start) / BADGE_MS)
  return { x: a.sx + (b.sx - a.sx) * t, y: a.sy + (b.sy - a.sy) * t }
})

function easeInOut(t) {
  const x = Math.max(0, Math.min(1, t))
  return x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2
}

/** E2：该工位当前脉冲进度（0..1），无脉冲返回 null → IsoCable 不画光点。 */
function pulseProgress(deskId) {
  if (props.reduced) return null
  const pulse = pulses.value.find(item => item.deskId === deskId)
  if (!pulse) return null
  return Math.max(0, Math.min(1, (nowTick.value - pulse.start) / PULSE_MS))
}

function deskState(deskId) {
  if (isRehearsal.value) return 'rehearsal'
  return litIds.value.has(deskId) ? 'lit' : 'idle'
}

/** E6：空闲小人头朝活跃工位（无活跃则归零）。 */
function gazeOf(desk) {
  const lit = layout.value.desks.filter(item => litIds.value.has(item.id))
  if (!lit.length || litIds.value.has(desk.id)) return { dx: 0, dy: 0 }
  const cx = lit.reduce((sum, item) => sum + item.sx, 0) / lit.length
  const cy = lit.reduce((sum, item) => sum + item.sy, 0) / lit.length
  return {
    dx: Math.max(-1, Math.min(1, (cx - desk.sx) / 220)),
    dy: Math.max(-1, Math.min(1, (cy - desk.sy) / 220))
  }
}

const breathStyle = computed(() =>
  props.reduced ? undefined : { transform: `translateY(${breathY.value.toFixed(2)}px)` }
)

/* ---------------------------- 事件 → 动画（全部真实事件驱动） ---------------------------- */

watch(activityKey, () => {
  const now = Date.now()
  nowTick.value = now
  litIds.value = new Set(activity.value.map(item => item.deskId))
  litExpireAt.value = now + LIT_MS
  pulses.value = activity.value.map((item, i) => ({
    id: `${item.deskId}:${now}:${i}`,
    deskId: item.deskId,
    start: now + i * 80
  }))
  badge.from = badgeTo.value
  badge.to = (badgeTo.value + 1) % Math.max(1, layout.value.track.length)
  badge.start = now
  if (props.reduced) {
    // 门禁 1：静态单帧——亮灯状态保留，动画归零
    pulses.value = []
  } else {
    ensureTicker()
  }
})

/* E5 心跳：一次成功拉取 = 一次明灭 */
watch(
  () => props.heartbeatAt,
  at => {
    if (!at) return
    ledsFlash.value = true
    if (ledsTimer) window.clearTimeout(ledsTimer)
    ledsTimer = window.setTimeout(() => {
      ledsFlash.value = false
    }, 700)
  }
)
const ledsOn = computed(() => Boolean(props.heartbeatAt) && (props.reduced || ledsFlash.value))

let stopTick = null

function tick() {
  const now = Date.now()
  nowTick.value = now
  breathY.value = Math.sin((now / 7400) * Math.PI * 2) * 1.5
  if (litExpireAt.value && now >= litExpireAt.value) {
    litIds.value = new Set()
    litExpireAt.value = 0
  }
  if (pulses.value.length && pulses.value.every(p => now - p.start > PULSE_MS)) {
    pulses.value = []
  }
  const quiet =
    !litIds.value.size && !pulses.value.length && badgeSettled.value && !ledsFlash.value
  if (quiet) stopTicker() // 无事件静默：不再占用帧预算
}

function ensureTicker() {
  if (stopTick || props.reduced) return
  stopTick = subscribe(tick, { fps: 30, id: 'workshop-room' })
}

function stopTicker() {
  if (!stopTick) return
  stopTick()
  stopTick = null
}

watch(
  () => props.reduced,
  reducedNow => {
    if (reducedNow) {
      stopTicker()
      breathY.value = 0
      pulses.value = []
    } else {
      ensureTicker()
    }
  }
)

/* ---------------------------- 交互与窄屏 ---------------------------- */

function onDeskSelect(desk) {
  emit('select', { deskId: desk.id, labelCn: desk.labelCn, info: infoByDesk.value.get(desk.id) || null })
}

const narrow = ref(false)
let narrowMq = null

function onMqChange(event) {
  narrow.value = event.matches
}

onMounted(() => {
  narrow.value = isNarrowViewport(globalThis.innerWidth)
  if (typeof globalThis.matchMedia === 'function') {
    narrowMq = globalThis.matchMedia(`(max-width: ${NARROW_VIEWPORT_MAX - 1}px)`)
    if (narrowMq.addEventListener) narrowMq.addEventListener('change', onMqChange)
  }
})

onBeforeUnmount(() => {
  stopTicker()
  if (ledsTimer) window.clearTimeout(ledsTimer)
  if (narrowMq) {
    if (narrowMq.removeEventListener) narrowMq.removeEventListener('change', onMqChange)
    narrowMq = null
  }
})
</script>

<style scoped>
.ws-room {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px;
}

/* 窄屏：退回文档流自撑高度（stage-field 在窄屏只剩 ~78px，绝对定位会压扁列表） */
.ws-room.is-narrow {
  position: relative;
  inset: auto;
  width: 100%;
  min-height: 300px;
  background: var(--fab-bg, var(--ds-surface-base, #0E1116));
  justify-content: flex-start;
  z-index: 1;
}

.ws-room.is-narrow .ws-room-foot {
  display: none;
}

.ws-room.is-stale {
  filter: saturate(0.6);
}

.ws-room-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.ws-wall {
  fill: color-mix(in srgb, var(--ds-surface-base, #0E1116) 88%, var(--fab-clay, #2496ed) 6%);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.8;
}
.ws-wall--left {
  fill: color-mix(in srgb, var(--ds-surface-base, #0E1116) 94%, var(--fab-clay, #2496ed) 3%);
}
.ws-floor {
  fill: var(--ds-surface-base, #0E1116);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.8;
}

.ws-screen-face {
  fill: color-mix(in srgb, var(--ds-surface-raised, #151A21) 92%, transparent);
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 1;
}
.ws-screen-title {
  fill: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 7px/1 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.14em;
  text-anchor: middle;
}
.ws-screen-line {
  fill: none;
  stroke: var(--fab-sage, #8bcfb4);
  stroke-width: 1.4;
}
.ws-screen-empty {
  fill: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  font: 8px/1 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.2em;
  text-anchor: middle;
}

.ws-cab-top { fill: var(--ds-surface-raised, #151A21); stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26)); stroke-width: 0.8; }
.ws-cab-left { fill: var(--ds-surface-base, #0E1116); stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26)); stroke-width: 0.6; }
.ws-cab-right { fill: color-mix(in srgb, var(--ds-surface-base, #0E1116) 50%, var(--ds-surface-overlay, #1B212A) 50%); stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26)); stroke-width: 0.6; }
.ws-cab-led {
  fill: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  transition: fill 0.25s var(--fab-ease-io, cubic-bezier(0.4, 0, 0.2, 1));
}
.ws-cab-led.is-on {
  fill: var(--fab-sage, #8bcfb4);
}

.ws-track {
  fill: none;
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 1.2;
  stroke-dasharray: 5 4;
}
.ws-station {
  fill: var(--ds-surface-raised, #151A21);
  stroke: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  stroke-width: 1;
}
.ws-station.is-active {
  fill: var(--fab-gaze, #7ad7f5);
  stroke: var(--fab-gaze, #7ad7f5);
}
.ws-station-label {
  fill: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 7.5px/1 var(--fab-mono, ui-monospace, monospace);
  text-anchor: middle;
}
.ws-badge {
  fill: var(--fab-butter, #d9b96d);
  transition: opacity 0.4s var(--fab-ease-io, cubic-bezier(0.4, 0, 0.2, 1));
}
.ws-badge.is-resting {
  opacity: 0.4;
}

.ws-watermark {
  fill: var(--fab-plum, #a383a6);
  font: 11px/1 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.3em;
  text-anchor: middle;
  opacity: 0.75;
}

.ws-room-foot {
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 10px;
  margin: 0;
  display: flex;
  gap: 14px;
  align-items: baseline;
  color: var(--fab-paper-46, rgba(232, 242, 247, 0.46));
  font: 8.5px/1.4 var(--fab-mono, ui-monospace, monospace);
  letter-spacing: 0.12em;
}
.ws-state--live { color: var(--fab-sage, #8bcfb4); }
.ws-state--off { color: var(--fab-plum, #a383a6); }
</style>
