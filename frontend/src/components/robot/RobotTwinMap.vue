<template>
  <section class="twin" aria-labelledby="twin-title">
    <header class="twin-head">
      <div>
        <p class="twin-eyebrow">DIGITAL TWIN · 多设备实时态势</p>
        <h2 id="twin-title">数字孪生总览</h2>
      </div>
      <div class="twin-tools">
        <div class="theme-switch" role="group" aria-label="孪生地图主题">
          <button
            v-for="item in THEMES"
            :key="item.key"
            type="button"
            class="theme-btn"
            :class="{ active: theme === item.key }"
            @click="theme = item.key"
          >{{ item.label }}</button>
        </div>
        <span class="twin-hint">
          {{ editable ? '规划模式：点击地图添加路点，点击编号可删除' : '点击设备标记切换当前设备' }}
        </span>
      </div>
    </header>

    <div class="twin-stage">
      <svg
        ref="svgEl"
        class="twin-svg"
        viewBox="0 0 960 600"
        role="img"
        :aria-label="ariaLabel"
        @click="onMapClick"
        @mousemove="onMouseMove"
      >
        <!-- 主题底图：装饰层固定于画布坐标系，不随数据范围缩放 -->
        <rect x="0" y="0" width="960" height="600" :fill="palette.bg" />

        <g v-if="theme === 'campus'" class="deco">
          <rect x="60" y="70" width="260" height="170" rx="18" :fill="palette.green" opacity="0.8" />
          <rect x="640" y="330" width="250" height="190" rx="18" :fill="palette.green" opacity="0.72" />
          <rect x="80" y="400" width="180" height="140" rx="14" :fill="palette.green" opacity="0.55" />
          <path d="M40 330 H920" :stroke="palette.road" stroke-width="34" stroke-linecap="round" />
          <path d="M480 30 V570" :stroke="palette.road" stroke-width="26" stroke-linecap="round" />
          <path d="M40 330 H920" stroke="#3a5065" stroke-width="2" stroke-dasharray="14 14" opacity="0.8" />
          <path d="M480 30 V570" stroke="#3a5065" stroke-width="2" stroke-dasharray="14 14" opacity="0.8" />
          <g :fill="palette.block" :stroke="palette.blockStroke">
            <rect x="360" y="120" width="90" height="120" rx="8" />
            <rect x="520" y="120" width="120" height="90" rx="8" />
            <rect x="520" y="390" width="90" height="110" rx="8" />
            <rect x="300" y="390" width="120" height="80" rx="8" />
          </g>
          <g class="deco-label" :fill="palette.decoText">
            <text x="405" y="105">图书馆</text>
            <text x="580" y="105">实验楼</text>
            <text x="565" y="385">教学楼</text>
            <text x="360" y="385">宿舍区</text>
            <text x="120" y="165">中心广场</text>
          </g>
          <circle cx="180" cy="160" r="34" :fill="palette.green" opacity="0.9" />
          <circle cx="780" cy="430" r="46" :fill="palette.green" opacity="0.7" />
        </g>

        <g v-else-if="theme === 'industrial'" class="deco">
          <defs>
            <pattern id="twin-grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M48 0 H0 V48" fill="none" stroke="#1b2a3a" stroke-width="1" />
            </pattern>
          </defs>
          <rect x="0" y="0" width="960" height="600" fill="url(#twin-grid)" />
          <rect x="70" y="90" width="220" height="140" rx="8" :fill="palette.block" :stroke="palette.blockStroke" />
          <rect x="650" y="80" width="230" height="160" rx="8" :fill="palette.block" :stroke="palette.blockStroke" />
          <rect x="680" y="350" width="200" height="170" rx="8" :fill="palette.block" :stroke="palette.blockStroke" />
          <path d="M290 160 H650 M290 430 H680 M70 430 H290" :stroke="palette.road" stroke-width="14" stroke-linecap="round" />
          <g :fill="palette.decoText">
            <text x="96" y="120">巡检车间 A</text>
            <text x="676" y="110">能源站</text>
            <text x="706" y="382">仓储区</text>
          </g>
          <circle cx="490" cy="250" r="54" fill="none" :stroke="palette.blockStroke" stroke-width="10" opacity="0.6" />
          <circle cx="490" cy="250" r="26" fill="none" :stroke="palette.blockStroke" stroke-width="8" opacity="0.6" />
        </g>

        <g v-else class="deco">
          <defs>
            <pattern id="twin-dots" width="36" height="36" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1.4" fill="#203247" />
            </pattern>
          </defs>
          <rect x="0" y="0" width="960" height="600" fill="url(#twin-dots)" />
          <g fill="none" :stroke="palette.blockStroke" opacity="0.55">
            <circle cx="480" cy="300" r="120" stroke-width="1" />
            <circle cx="480" cy="300" r="220" stroke-width="1" stroke-dasharray="6 10" />
            <circle cx="480" cy="300" r="320" stroke-width="1" stroke-dasharray="2 12" />
          </g>
        </g>

        <!-- 坐标网格（跟随数据范围） -->
        <g class="grid" :stroke="palette.grid" stroke-width="1">
          <line v-for="tick in gridLines.vertical" :key="`gv-${tick.value}`" :x1="tick.sx" y1="40" :x2="tick.sx" y2="560" />
          <line v-for="tick in gridLines.horizontal" :key="`gh-${tick.value}`" x1="40" :y1="tick.sy" x2="920" :y2="tick.sy" />
        </g>
        <g class="grid-label" :fill="palette.decoText" opacity="0.7">
          <text v-for="tick in gridLines.vertical" :key="`gvl-${tick.value}`" :x="tick.sx + 4" y="586">{{ tick.value }}m</text>
        </g>

        <!-- 历史轨迹：非当前设备弱化显示 -->
        <g class="trails">
          <polyline
            v-for="trail in otherTrails"
            :key="`trail-${trail.key}`"
            :points="trail.points"
            fill="none"
            :stroke="palette.trail"
            stroke-width="2"
            stroke-dasharray="3 5"
            opacity="0.45"
          />
          <polyline
            v-if="selectedTrail.points"
            :points="selectedTrail.points"
            fill="none"
            :stroke="palette.trailActive"
            stroke-width="2.5"
            opacity="0.9"
          />
        </g>

        <!-- 最新任务路线：已走完的路点弱化 -->
        <g v-if="routePoints.length" class="route">
          <polyline
            :points="routePolyline"
            fill="none"
            :stroke="palette.route"
            stroke-width="2.5"
            stroke-dasharray="7 6"
            opacity="0.85"
          />
          <g v-for="(point, index) in routePoints" :key="`route-${index}`">
            <circle
              :cx="point.sx"
              :cy="point.sy"
              :r="index < routeProgress ? 4 : 6"
              :fill="index < routeProgress ? palette.routeDone : palette.route"
              :opacity="index < routeProgress ? 0.5 : 0.95"
            />
            <text :x="point.sx" :y="point.sy - 10" text-anchor="middle" class="route-index" :fill="palette.route">
              {{ point.label || index + 1 }}
            </text>
          </g>
        </g>

        <!-- 规划草稿 -->
        <g v-if="draftPoints.length" class="draft">
          <polyline :points="draftPolyline" fill="none" :stroke="palette.draft" stroke-width="2" stroke-dasharray="5 5" />
          <g
            v-for="(point, index) in draftPoints"
            :key="`draft-${index}`"
            class="draft-point"
            @click.stop="emit('remove-draft', index)"
          >
            <circle :cx="point.sx" :cy="point.sy" r="9" :fill="palette.draftFill" :stroke="palette.draft" stroke-width="2" />
            <text :x="point.sx" :y="point.sy + 3.5" text-anchor="middle" class="draft-index">{{ index + 1 }}</text>
          </g>
        </g>

        <!-- 告警光晕 -->
        <g class="alert-pins">
          <g v-for="pin in alertPins" :key="pin.id" :transform="`translate(${pin.sx} ${pin.sy})`">
            <circle r="17" :fill="pin.color" opacity="0.18">
              <animate attributeName="r" values="14;22;14" dur="2.4s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.28;0.06;0.28" dur="2.4s" repeatCount="indefinite" />
            </circle>
            <circle r="4" :fill="pin.color" />
          </g>
        </g>

        <!-- 设备标记 -->
        <g
          v-for="marker in markers"
          :key="marker.key"
          class="device-marker"
          :class="{ selected: marker.key === selectedKey, offline: !marker.online }"
          :transform="`translate(${marker.sx} ${marker.sy})`"
          role="button"
          tabindex="0"
          @click.stop="emit('select', marker.key)"
          @keydown.enter.stop="emit('select', marker.key)"
        >
          <title>{{ marker.name }} · {{ marker.modeLabel }} · 电量 {{ marker.batteryText }}</title>
          <circle v-if="marker.key === selectedKey" r="23" class="marker-ring" :stroke="palette.selected" />
          <circle r="14" :fill="marker.fill" :stroke="marker.stroke" stroke-width="2" />
          <g :transform="`rotate(${-marker.theta})`">
            <path d="M0 -20 L4 -12 L-4 -12 Z" :fill="marker.stroke" />
          </g>
          <text y="4.5" text-anchor="middle" class="marker-glyph">{{ marker.glyph }}</text>
          <rect x="-58" y="20" width="116" height="34" rx="7" :fill="palette.labelBg" opacity="0.9" />
          <text y="33" text-anchor="middle" class="marker-name">{{ marker.name }}</text>
          <text y="47" text-anchor="middle" class="marker-meta">{{ marker.modeLabel }} · {{ marker.batteryText }}</text>
        </g>
      </svg>

      <div class="twin-kpis" aria-live="polite">
        <span><b>{{ onlineCount }}</b> / {{ deviceCount }} 在线</span>
        <span><b>{{ runningTasks }}</b> 任务执行中</span>
        <span :class="{ danger: activeAlertCount > 0 }"><b>{{ activeAlertCount }}</b> 未确认预警</span>
      </div>

      <div v-if="editable" class="twin-cursor">
        {{ cursor.x === null ? '移动鼠标读取坐标' : `坐标 ${cursor.x.toFixed(1)} , ${cursor.y.toFixed(1)} m` }}
      </div>

      <p v-if="!markers.length" class="twin-empty">
        暂无设备位姿上报。地图只渲染真实遥测位置，不虚构设备点位。
      </p>
    </div>

    <footer class="twin-foot">
      <div class="legend">
        <span><i class="dot" :style="{ background: palette.route }"></i>巡检路线</span>
        <span><i class="dot" :style="{ background: palette.draft }"></i>规划草稿</span>
        <span><i class="dot" :style="{ background: palette.trailActive }"></i>历史轨迹</span>
        <span><i class="dot" style="background: #e3a008"></i>未确认预警</span>
      </div>
      <div v-if="unpositioned.length" class="unpositioned">
        无位姿：
        <button
          v-for="device in unpositioned"
          :key="device.deviceKey"
          type="button"
          class="unpositioned-chip"
          @click="emit('select', device.deviceKey)"
        >{{ device.name || device.deviceKey }}</button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 数字孪生总览地图（SVG，不新增第二个 WebGL 主体）。
 *
 * 数据契约：
 * - 设备位置只取真实遥测 pose；没有位姿的设备归入「无位姿」列表，不在地图上编造坐标；
 * - 路线优先使用目标的绝对坐标 targetX/targetY（规划器下发），历史任务无该字段时回落到 x/y；
 * - 告警光晕只来自真实预警（遥测阈值 / 纠察事件），已确认的预警不再闪烁。
 */

const props = defineProps({
  devices: { type: Array, default: () => [] },
  states: { type: Object, default: () => ({}) },
  selectedKey: { type: String, default: '' },
  trails: { type: Object, default: () => ({}) },
  alerts: { type: Array, default: () => [] },
  route: { type: Array, default: () => [] },
  routeProgress: { type: Number, default: 0 },
  draft: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
  runningTasks: { type: Number, default: 0 },
  activeAlertCount: { type: Number, default: 0 }
})

const emit = defineEmits(['select', 'pick', 'remove-draft'])

const THEMES = [
  { key: 'campus', label: '校园园区' },
  { key: 'industrial', label: '工业园区' },
  { key: 'abstract', label: '抽象网格' }
]

const THEME_KEY = 'smartops_robot_twin_theme'
const FORM_GLYPHS = { CAR: '车', DOG: '犬', SPIDER: '蛛', ROBOT: '人' }
const MODE_LABELS = {
  OFFLINE: '离线',
  IDLE: '空闲',
  AUTONOMOUS: '自主',
  HUMAN_CONTROL: '人工',
  E_STOP: '急停',
  FAULT: '故障'
}

const PALETTES = {
  campus: {
    bg: '#081410',
    grid: '#173029',
    road: '#20323f',
    green: '#1b4536',
    block: '#12222f',
    blockStroke: '#3a5b75',
    decoText: '#7a9db1',
    trail: '#3f6f8f',
    trailActive: '#5b8cff',
    route: '#5b8cff',
    routeDone: '#35527d',
    draft: '#43d1a0',
    draftFill: 'rgba(67,209,160,.18)',
    selected: '#8bd6ff',
    labelBg: 'rgba(6,14,20,.88)'
  },
  industrial: {
    bg: '#080f16',
    grid: '#1c2d3f',
    road: '#223446',
    green: '#16332d',
    block: '#101e2b',
    blockStroke: '#34506b',
    decoText: '#6b8aa3',
    trail: '#3f6f8f',
    trailActive: '#5b8cff',
    route: '#5b8cff',
    routeDone: '#35527d',
    draft: '#43d1a0',
    draftFill: 'rgba(67,209,160,.18)',
    selected: '#8bd6ff',
    labelBg: 'rgba(6,14,20,.9)'
  },
  abstract: {
    bg: '#070d16',
    grid: '#16263a',
    road: '#182839',
    green: '#16332d',
    block: '#0e1a29',
    blockStroke: '#2b4560',
    decoText: '#6a8aa5',
    trail: '#3f6f8f',
    trailActive: '#5b8cff',
    route: '#5b8cff',
    routeDone: '#35527d',
    draft: '#43d1a0',
    draftFill: 'rgba(67,209,160,.18)',
    selected: '#8bd6ff',
    labelBg: 'rgba(6,14,20,.9)'
  }
}

const MAP_W = 960
const MAP_H = 600
const PAD = 56
const MIN_SPAN = 12

function loadTheme() {
  try {
    const saved = window.localStorage.getItem(THEME_KEY)
    return THEMES.some(item => item.key === saved) ? saved : 'campus'
  } catch {
    return 'campus'
  }
}

const theme = ref(loadTheme())
watch(theme, (value) => {
  try {
    window.localStorage.setItem(THEME_KEY, value)
  } catch {
    /* 隐私模式：仅当次生效 */
  }
})
const palette = computed(() => PALETTES[theme.value] || PALETTES.campus)

const svgEl = ref(null)
const cursor = ref({ x: null, y: null })

function batteryPercent(raw) {
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  return Math.round(value <= 1 ? value * 100 : value)
}

function pointOf(item) {
  if (!item || typeof item !== 'object') return null
  const x = Number(item.targetX ?? item.x)
  const y = Number(item.targetY ?? item.y)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { x, y, label: item.label ?? '' }
}

const routePointsRaw = computed(() => (props.route || []).map(pointOf).filter(Boolean))
const draftPointsRaw = computed(() => (props.draft || []).map(pointOf).filter(Boolean))

const positioned = computed(() => props.devices.map((device) => {
  const state = props.states[device.deviceKey] || {}
  const pose = state.telemetry?.pose
  const x = Number(pose?.x)
  const y = Number(pose?.y)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { device, state, pose, x, y }
}).filter(Boolean))

const unpositioned = computed(() => props.devices.filter(device => {
  const pose = props.states[device.deviceKey]?.telemetry?.pose
  return !Number.isFinite(Number(pose?.x)) || !Number.isFinite(Number(pose?.y))
}))

const bounds = computed(() => {
  const xs = [0]
  const ys = [0]
  positioned.value.forEach(item => { xs.push(item.x); ys.push(item.y) })
  routePointsRaw.value.forEach(item => { xs.push(item.x); ys.push(item.y) })
  draftPointsRaw.value.forEach(item => { xs.push(item.x); ys.push(item.y) })
  Object.values(props.trails || {}).forEach((trail) => {
    (trail || []).forEach((point) => {
      const x = Number(point?.x)
      const y = Number(point?.y)
      if (Number.isFinite(x) && Number.isFinite(y)) { xs.push(x); ys.push(y) }
    })
  })
  let minX = Math.min(...xs) - 1.5
  let maxX = Math.max(...xs) + 1.5
  let minY = Math.min(...ys) - 1.5
  let maxY = Math.max(...ys) + 1.5
  const spanX = maxX - minX
  const spanY = maxY - minY
  if (spanX < MIN_SPAN) {
    const extra = (MIN_SPAN - spanX) / 2
    minX -= extra
    maxX += extra
  }
  if (spanY < MIN_SPAN) {
    const extra = (MIN_SPAN - spanY) / 2
    minY -= extra
    maxY += extra
  }
  return { minX, maxX, minY, maxY }
})

const view = computed(() => {
  const box = bounds.value
  const scale = Math.min(
    (MAP_W - PAD * 2) / (box.maxX - box.minX),
    (MAP_H - PAD * 2) / (box.maxY - box.minY)
  )
  return {
    scale,
    cx: (box.minX + box.maxX) / 2,
    cy: (box.minY + box.maxY) / 2
  }
})

function toScreen(x, y) {
  return {
    sx: MAP_W / 2 + (x - view.value.cx) * view.value.scale,
    sy: MAP_H / 2 - (y - view.value.cy) * view.value.scale
  }
}

function toWorld(sx, sy) {
  return {
    x: view.value.cx + (sx - MAP_W / 2) / view.value.scale,
    y: view.value.cy - (sy - MAP_H / 2) / view.value.scale
  }
}

const gridLines = computed(() => {
  const box = bounds.value
  const step = niceStep((box.maxX - box.minX) / 8)
  const vertical = []
  const horizontal = []
  const startX = Math.ceil(box.minX / step) * step
  for (let value = startX; value <= box.maxX; value += step) {
    vertical.push({ value: Math.round(value * 10) / 10, sx: toScreen(value, 0).sx })
  }
  const startY = Math.ceil(box.minY / step) * step
  for (let value = startY; value <= box.maxY; value += step) {
    horizontal.push({ value: Math.round(value * 10) / 10, sy: toScreen(0, value).sy })
  }
  return { vertical, horizontal }
})

function niceStep(raw) {
  const value = Math.max(raw, 0.5)
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return nice * magnitude
}

const markers = computed(() => positioned.value.map(({ device, state, pose, x, y }) => {
  const point = toScreen(x, y)
  const percent = batteryPercent(state.telemetry?.battery)
  const online = Boolean(state.bridgeConnected)
  const mode = state.mode || 'OFFLINE'
  const danger = mode === 'E_STOP' || mode === 'FAULT'
  return {
    key: device.deviceKey,
    name: device.name || device.deviceKey,
    glyph: FORM_GLYPHS[device.formFactor] || '机',
    sx: point.sx,
    sy: point.sy,
    theta: Number(pose?.theta) || 0,
    online,
    modeLabel: MODE_LABELS[mode] || mode,
    batteryText: percent === null ? '—' : `${percent}%`,
    fill: danger ? 'rgba(220,96,110,.28)' : online ? 'rgba(41,110,160,.34)' : 'rgba(90,105,120,.22)',
    stroke: danger ? '#e0646e' : online ? '#7fc2e6' : '#5d6d7c'
  }
}))

const routePoints = computed(() => routePointsRaw.value.map((point, index) => ({
  ...point,
  ...toScreen(point.x, point.y),
  label: point.label || index + 1
})))

const draftPoints = computed(() => draftPointsRaw.value.map((point, index) => ({
  ...point,
  ...toScreen(point.x, point.y)
})))

const routePolyline = computed(() => routePoints.value.map(point => `${point.sx},${point.sy}`).join(' '))
const draftPolyline = computed(() => draftPoints.value.map(point => `${point.sx},${point.sy}`).join(' '))

const trailsOf = computed(() => Object.entries(props.trails || {}).map(([key, trail]) => {
  const points = (trail || []).map((point) => {
    const screen = toScreen(Number(point.x), Number(point.y))
    return `${screen.sx},${screen.sy}`
  })
  return { key, points: points.join(' ') }
}).filter(item => item.points))

const selectedTrail = computed(() => trailsOf.value.find(item => item.key === props.selectedKey) || { points: '' })
const otherTrails = computed(() => trailsOf.value.filter(item => item.key !== props.selectedKey))

const alertPins = computed(() => {
  const pins = []
  const seen = new Set()
  props.alerts.forEach((alert) => {
    if (!alert.deviceKey || alert.acked) return
    if (seen.has(alert.deviceKey)) return
    const item = positioned.value.find(entry => entry.device.deviceKey === alert.deviceKey)
    if (!item) return
    seen.add(alert.deviceKey)
    const point = toScreen(item.x, item.y)
    pins.push({
      id: alert.id,
      sx: point.sx,
      sy: point.sy,
      color: alert.severity === 'CRITICAL' ? '#e0646e' : alert.severity === 'HIGH' ? '#e3a008' : '#d9b96d'
    })
  })
  return pins
})

const onlineCount = computed(() => positioned.value.filter(item => item.state.bridgeConnected).length)
const deviceCount = computed(() => props.devices.length)

const ariaLabel = computed(() => `数字孪生态势图，${deviceCount.value} 台设备，${onlineCount.value} 台在线`)

function onMapClick(event) {
  if (!props.editable || !svgEl.value) return
  const point = locate(event)
  if (!point) return
  emit('pick', { x: Math.round(point.x * 10) / 10, y: Math.round(point.y * 10) / 10 })
}

function onMouseMove(event) {
  if (!props.editable) return
  const point = locate(event)
  cursor.value = point || { x: null, y: null }
}

function locate(event) {
  const svg = svgEl.value
  if (!svg) return null
  const matrix = svg.getScreenCTM()
  if (!matrix) return null
  const point = svg.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const local = point.matrixTransform(matrix.inverse())
  return toWorld(local.x, local.y)
}

onBeforeUnmount(() => {
  cursor.value = { x: null, y: null }
})
</script>

<style scoped>
.twin {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
  min-width: 0;
}

.twin-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-3);
}

.twin-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.twin-head h2 {
  margin: 0;
  font-size: var(--ds-font-lg);
}

.twin-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space-3);
}

.theme-switch {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-pill);
  background: var(--ds-color-surface-raised);
}

.theme-btn {
  padding: 4px 10px;
  border: 0;
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  cursor: pointer;
  transition: background-color var(--ds-duration-fast) ease, color var(--ds-duration-fast) ease;
}

.theme-btn.active {
  background: rgba(36, 150, 237, 0.18);
  color: var(--ds-color-text);
}

.twin-hint {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.twin-stage {
  position: relative;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  overflow: hidden;
  background: #070d14;
}

.twin-svg {
  display: block;
  width: 100%;
  height: auto;
  cursor: default;
}

.twin-kpis {
  position: absolute;
  top: 10px;
  left: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: rgba(6, 13, 20, 0.82);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  backdrop-filter: blur(4px);
}

.twin-kpis b {
  color: var(--ds-color-text);
  font-variant-numeric: tabular-nums;
}

.twin-kpis .danger b {
  color: var(--ds-color-warning);
}

.twin-cursor {
  position: absolute;
  right: 10px;
  bottom: 10px;
  padding: 3px 8px;
  border-radius: var(--ds-radius-pill);
  background: rgba(6, 13, 20, 0.82);
  color: var(--ds-color-muted);
  font-family: var(--ds-font-mono);
  font-size: 10px;
}

.twin-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: var(--ds-space-6);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  text-align: center;
  pointer-events: none;
}

.twin-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-3);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.legend .dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 4px;
  border-radius: 50%;
  vertical-align: middle;
}

.unpositioned {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.unpositioned-chip {
  padding: 2px 8px;
  border: 1px dashed var(--ds-color-border-strong);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  cursor: pointer;
}

.unpositioned-chip:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.grid-label {
  font-family: var(--ds-font-mono);
  font-size: 9px;
}

.deco-label {
  font-size: 12px;
  letter-spacing: 0.04em;
}

.marker-glyph {
  fill: #d9ecff;
  font-size: 10px;
  font-weight: 600;
  pointer-events: none;
}

.marker-name {
  fill: #e8f2fb;
  font-size: 11px;
  pointer-events: none;
}

.marker-meta {
  fill: #8ba6bb;
  font-size: 9px;
  pointer-events: none;
}

.device-marker {
  cursor: pointer;
}

.device-marker.offline {
  opacity: 0.65;
}

.marker-ring {
  fill: none;
  stroke-width: 1.5;
  stroke-dasharray: 4 4;
  opacity: 0.9;
  animation: marker-spin 8s linear infinite;
  transform-origin: center;
}

.route-index {
  font-family: var(--ds-font-mono);
  font-size: 9px;
}

.draft-index {
  fill: #d8fff1;
  font-size: 9px;
  font-weight: 600;
  cursor: pointer;
}

.draft-point {
  cursor: pointer;
}

@keyframes marker-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .marker-ring,
  .alert-pins animate {
    animation: none;
  }
}
</style>
