<template>
  <section class="ef3-wrap" aria-labelledby="ef3-title">
    <header class="ef3-head">
      <div>
        <p class="ef3-eyebrow">ENGINE FIELD · 3D / 真实状态驱动</p>
        <h2 id="ef3-title">引擎场</h2>
      </div>
      <p class="ef3-note">每个节点 = 一条真实流水线；只有心跳新鲜时才发光呼吸，无事件节点保持静止。</p>
    </header>

    <!-- WebGL 3D 场：容器必须常驻，ref 才能在 onMounted 拿到；显隐用 v-show（v-if 会造成 host 永不存在的死锁） -->
    <div v-show="webglReady && !staticMode" ref="host" class="ef3-stage" role="img" :aria-label="ariaLabel">
      <span
        v-for="node in nodeButtons"
        :key="`l-${node.id}`"
        class="ef3-node-label"
        :style="{ left: `${node.left}%`, top: `${node.top + 7}%` }"
        aria-hidden="true"
      >{{ node.name }}</span>
      <button
        v-for="node in nodeButtons"
        :key="node.id"
        type="button"
        class="ef3-node-hit"
        :style="{ left: `${node.left}%`, top: `${node.top}%` }"
        :aria-label="`选择 ${node.name}：${node.statusText}`"
        :aria-pressed="selectedId === node.id ? 'true' : 'false'"
        @click="$emit('select', node.id)"
      ></button>
      <div class="ef3-center" aria-hidden="true">
        <strong>{{ center.live }}</strong><span>运行中 / {{ center.total }}</span>
        <small>更新 {{ center.generatedAtText }}</small>
      </div>
    </div>

    <!-- 降级静态场：reduced-motion / lightweight / WebGL 不可用 / 窄屏 -->
    <div v-if="!webglReady || staticMode" class="ef3-stage ef3-stage--static" role="img" :aria-label="ariaLabel">
      <svg viewBox="0 0 600 240" class="ef3-static-svg" aria-hidden="true">
        <ellipse cx="300" cy="120" rx="230" ry="88" fill="none" :stroke="'var(--ds-hairline)'" stroke-width="1" />
        <g v-for="node in staticNodes" :key="node.id">
          <circle
            :cx="node.cx" :cy="node.cy" :r="node.outline ? 8 : 11"
            fill="none" :stroke="node.color" :stroke-width="node.outline ? 1 : 2"
            :stroke-dasharray="node.outline ? '3 3' : undefined"
          />
          <circle v-if="!node.outline" :cx="node.cx" :cy="node.cy" r="4" :fill="node.color" />
          <text :x="node.cx" :y="node.cy + 24" text-anchor="middle" :fill="'var(--ds-color-muted)'" font-size="10">{{ node.name }}</text>
        </g>
        <text x="300" y="116" text-anchor="middle" :fill="'var(--ds-color-text)'" font-size="18">{{ center.live }} / {{ center.total }}</text>
        <text x="300" y="136" text-anchor="middle" :fill="'var(--ds-color-muted)'" font-size="10">运行中 · {{ staticMode === 'narrow' ? '窄屏静态' : '静态单帧' }}</text>
      </svg>
      <button
        v-for="node in nodeButtons"
        :key="`s-${node.id}`"
        type="button"
        class="ef3-node-hit ef3-node-hit--static"
        :style="{ left: `${node.left}%`, top: `${node.top}%` }"
        :aria-label="`选择 ${node.name}：${node.statusText}`"
        @click="$emit('select', node.id)"
      ></button>
    </div>

    <p class="ef3-caption">{{ caption }}</p>
  </section>
</template>

<script setup>
/**
 * 3D 引擎场：只消费父级喂的 engines / generatedAt，不请求、不轮询、不伪造。
 * 动画强度全部由 engineField3D.js 的纯函数按真实 ageSec/expectedPeriodSec 推导。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, CircleGeometry, Color, Group,
  LineBasicMaterial, LineLoop, Mesh, MeshBasicMaterial, PerspectiveCamera,
  Scene, WebGLRenderer
} from 'three'
import { engineFieldCenter, engineNodeLayout, engineVisualState } from './engineField3D.js'
import { subscribe } from '../../visual/motionScheduler.js'
import { isLightweightVisualMode, isReducedMotionMode } from '../../visual/visualMode.js'
import { isDegraded } from '../../visual/motionScheduler.js'

const props = defineProps({
  engines: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  generatedAtText: { type: String, default: '—' },
  narrow: { type: Boolean, default: false }
})
defineEmits(['select'])

const host = ref(null)
const webglReady = ref(false)
const staticMode = computed(() => props.narrow || isLightweightVisualMode.value || isReducedMotionMode.value || isDegraded() || reduced.value)
const reduced = ref(false)

const visuals = computed(() => props.engines.map(engine => engineVisualState(engine)))
const center = computed(() => engineFieldCenter(props.engines, props.generatedAtText))
const statusLabelMap = { RUNNING: '运行中', STALLED: '疑似停摆', ERROR: '异常', NO_DATA: '无数据', NOT_RUN: '未运行' }
const nodeButtons = computed(() => props.engines.map((engine, index) => {
  const layout = engineNodeLayout(props.engines.map(e => e.id))[index] || { x: 0, y: 0 }
  return {
    id: engine.id,
    name: engine.name || engine.id,
    statusText: statusLabelMap[String(engine.status || '').toUpperCase()] || engine.status || '未知',
    /* 世界坐标 → 屏幕百分比：椭圆半径 1.7 / 相机距离 5.4 的经验映射，与 3D 节点对齐 */
    left: 50 + layout.x * 23,
    top: 50 - layout.y * 30
  }
}))
const staticNodes = computed(() => props.engines.map((engine, index) => {
  const layout = engineNodeLayout(props.engines.map(e => e.id))[index] || { x: 0, y: 0 }
  const v = visuals.value[index]
  return {
    id: engine.id,
    name: engine.name || engine.id,
    cx: 300 + layout.x * 132,
    cy: 120 - layout.y * 55,
    color: `var(${v.colorVar})`,
    outline: v.outline
  }
}))
const ariaLabel = computed(() => `引擎场：${props.engines.map(e => `${e.name || e.id} ${statusLabelMap[String(e.status || '').toUpperCase()] || e.status}`).join('，')}`)
const caption = computed(() => {
  const animated = props.engines.filter((e, i) => visuals.value[i]?.animated).length
  return animated
    ? `${animated} 条流水线有真实心跳在动；其余保持静止。呼吸越慢 = 距预期周期越近。`
    : '当前没有真实心跳驱动任何节点——引擎场保持静止，不模拟繁忙。'
})

let disposeScene = () => {}
let unsubscribe = () => {}

function resolveColor(cssVar, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim()
  if (!raw || raw.startsWith('var(')) return fallback
  try { return new Color(raw).getHex() } catch { return fallback }
}

onMounted(() => {
  try { reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { /* SSR */ }
  if (staticMode.value || !host.value) return
  let renderer
  try {
    renderer = new WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'low-power' })
  } catch { return }
  const element = host.value
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  element.appendChild(renderer.domElement)
  webglReady.value = true

  const scene = new Scene()
  const camera = new PerspectiveCamera(42, 1, 0.1, 100)
  camera.position.set(0, 0.6, 5.4)
  camera.lookAt(0, 0, 0)
  const root = new Group()
  scene.add(root)

  const ring = new LineLoop(
    new BufferGeometry().setAttribute('position', new BufferAttribute((() => {
      const pts = []
      for (let i = 0; i < 96; i += 1) {
        const a = (i / 96) * Math.PI * 2
        pts.push(Math.cos(a) * 1.7, Math.sin(a) * 0.94, 0)
      }
      return new Float32Array(pts)
    })(), 3)),
    new LineBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.16 })
  )
  root.add(ring)

  const nodes = new Map()
  const clock = { t: 0 }

  function syncNodes() {
    const layouts = engineNodeLayout(props.engines.map(e => e.id))
    const wanted = new Set(props.engines.map(e => e.id))
    for (const [id, entry] of nodes) {
      if (!wanted.has(id)) {
        root.remove(entry.group)
        entry.mesh.geometry.dispose(); entry.mesh.material.dispose()
        entry.halo.material.dispose(); entry.arc.geometry.dispose(); entry.arc.material.dispose()
        nodes.delete(id)
      }
    }
    props.engines.forEach((engine, index) => {
      const v = visuals.value[index] || engineVisualState(engine)
      const layout = layouts[index]
      let entry = nodes.get(engine.id)
      if (!entry) {
        const group = new Group()
        group.position.set(layout.x, layout.y, 0)
        const geometry = new CircleGeometry(0.15, 24)
        const material = new MeshBasicMaterial({ color: 0x888888, transparent: true, opacity: 0.9 })
        const mesh = new Mesh(geometry, material)
        const haloGeo = new CircleGeometry(0.27, 24)
        const haloMat = new MeshBasicMaterial({ color: 0x888888, transparent: true, opacity: 0.1, blending: AdditiveBlending, depthWrite: false })
        const halo = new Mesh(haloGeo, haloMat)
        halo.position.z = -0.01
        const arcGeo = new BufferGeometry().setAttribute('position', new BufferAttribute(new Float32Array(3 * 2), 3))
        const arc = new LineLoop(arcGeo, new LineBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.6 }))
        arc.position.z = 0.02
        group.add(halo, mesh, arc)
        root.add(group)
        entry = { group, mesh, halo, arc }
        nodes.set(engine.id, entry)
      }
      const color = resolveColor(v.colorVar, v.status === 'RUNNING' ? 0x5ad691 : v.status === 'STALLED' ? 0xe3a008 : v.status === 'ERROR' ? 0xe5484d : 0x8a8f98)
      entry.mesh.material.color.setHex(color)
      entry.mesh.material.opacity = v.outline ? 0.28 : 0.95
      entry.halo.material.color.setHex(color)
      entry.halo.material.opacity = v.animated ? 0.08 + v.glow * 0.16 : 0.02
      entry.arc.material.color.setHex(color)
      entry.arc.material.opacity = v.animated ? 0.7 : 0.1
      /* 进度弧：按比例画一段折线（两点+回到起点），到阈值封顶 */
      const a0 = layout.angle
      const span = Math.PI * 2 * v.progress
      const r = 0.24
      const arr = entry.arc.geometry.getAttribute('position')
      for (let i = 0; i < 3; i += 1) {
        const a = i === 2 ? a0 : a0 + (span * i) / 2
        arr.setXYZ(i, Math.cos(a) * r, Math.sin(a) * r, 0)
      }
      arr.needsUpdate = true
      entry.visual = v
      entry.selected = props.selectedId === engine.id
    })
  }

  function resize() {
    const w = Math.max(1, element.clientWidth)
    const h = Math.max(1, element.clientHeight)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
  ro?.observe(element)
  resize()
  syncNodes()
  syncNodesRef = syncNodes

  /* 呼吸只改变光晕透明度与半径——无事件节点 entry.visual.animated=false，永远保持静止。 */
  unsubscribe = subscribe((dt) => {
    if (staticMode.value) return
    clock.t += Math.min(dt || 0.016, 0.05)
    for (const entry of nodes.values()) {
      const v = entry.visual
      if (!v?.animated) continue
      const period = v.breathSec > 0 ? v.breathSec : 2.4
      const wave = 0.5 + 0.5 * Math.sin((clock.t / period) * Math.PI * 2)
      const base = 0.08 + v.glow * 0.12
      entry.halo.material.opacity = base + wave * 0.14
      const s = 1 + wave * 0.12
      entry.halo.scale.setScalar(s)
    }
    renderer.render(scene, camera)
  })

  disposeScene = () => {
    unsubscribe(); unsubscribe = () => {}
    ro?.disconnect()
    for (const entry of nodes.values()) {
      entry.mesh.geometry.dispose(); entry.mesh.material.dispose()
      entry.halo.geometry.dispose(); entry.halo.material.dispose()
      entry.arc.geometry.dispose(); entry.arc.material.dispose()
    }
    nodes.clear()
    ring.geometry.dispose(); ring.material.dispose()
    renderer.dispose()
    if (renderer.domElement.parentNode === element) element.removeChild(renderer.domElement)
  }
})

watch(() => [props.engines, props.selectedId], () => {
  if (webglReady.value) syncNodesRef()
}, { deep: true })

let syncNodesRef = () => {}
onBeforeUnmount(() => { disposeScene(); unsubscribe() })
</script>

<style scoped>
.ef3-wrap { border: 1px solid var(--ds-hairline, var(--smart-border)); border-radius: 12px; background: var(--ds-surface-raised, var(--smart-surface)); padding: 16px 18px; margin-bottom: 18px; }
.ef3-head { display: flex; justify-content: space-between; align-items: end; gap: 16px; flex-wrap: wrap; }
.ef3-eyebrow { margin: 0 0 5px; color: var(--ds-color-primary, var(--smart-primary)); font: 10px Consolas, monospace; letter-spacing: .14em; }
.ef3-head h2 { margin: 0; font-size: 15px; font-weight: 500; }
.ef3-note { margin: 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; }
.ef3-stage { position: relative; height: 250px; margin-top: 12px; overflow: hidden; }
.ef3-stage :deep(canvas) { display: block; width: 100%; height: 100%; }
.ef3-stage--static { display: grid; place-items: center; }
.ef3-static-svg { width: 100%; height: 100%; }
.ef3-node-label { position: absolute; transform: translate(-50%, -50%); color: var(--ds-color-muted, var(--smart-muted)); font-size: 10px; white-space: nowrap; pointer-events: none; }
.ef3-node-hit { position: absolute; width: 44px; height: 44px; transform: translate(-50%, -50%); border: 0; border-radius: 50%; background: transparent; cursor: pointer; z-index: 2; }
.ef3-node-hit[aria-pressed='true'] { box-shadow: 0 0 0 2px var(--ds-color-primary, var(--smart-primary)); }
.ef3-node-hit:focus-visible { outline: 2px solid var(--ds-color-primary, var(--smart-primary)); outline-offset: 2px; }
.ef3-center { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); display: grid; justify-items: center; gap: 2px; pointer-events: none; }
.ef3-center strong { font: 500 24px/1 Consolas, monospace; color: var(--ds-color-text, var(--smart-text)); }
.ef3-center span, .ef3-center small { color: var(--ds-color-muted, var(--smart-muted)); font-size: 10px; }
.ef3-caption { margin: 8px 0 0; color: var(--ds-color-muted, var(--smart-muted)); font-size: 11px; line-height: 1.6; }
@media (max-width: 760px) { .ef3-stage { height: 180px; } .ef3-note { display: none; } }
</style>
