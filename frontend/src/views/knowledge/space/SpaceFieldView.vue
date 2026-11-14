<!--
  SpaceFieldView.vue — 三层空间场主视图（DESIGN §3 / SP-07 挂载点）。

  负责：FieldStage（CSS 3D perspective 容器）+ FieldPlane（知识/洞察平面 DOM）
       + EvidenceBed（Canvas2D 证据层）+ ThreadLayer（SVG 论证线程）
       + InsightCanopy（L2 洞察带）的拼装与相机驱动。

  只渲染知识层 + 证据层（Phase A 无后端洞察）。洞察层和绑定线程保留接口，
  待 NaturalLanguageInsightsView 有真实洞察输入后接进 computeField。

  硬约束（DESIGN §6.2 / §7）：
  - 全量平面挂载 ≤ 480，越界触发视锥裁剪
  - 不引入 WebGL / three / 新增 rAF
  - 文字全部屏幕空间 DOM
-->
<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { knowledgeDomains, knowledgeEntries } from '../knowledgeCatalog.js'
import { computeField, FIELD } from './useFieldLayout.js'
import { buildBindingIndex } from './bindingIndex.js'
import { useFieldCamera, ORBIT, PRESET_NAMES } from './useFieldCamera.js'
import FieldStage from './FieldStage.vue'
import FieldPlane from './FieldPlane.vue'
import EvidenceBed from './EvidenceBed.vue'
import ThreadLayer from './ThreadLayer.vue'
import InsightCanopy from './InsightCanopy.vue'

// —— 空间场初始计算（Phase A 无洞察，先跑知识层 + 证据层）——
const SP_NOW = Date.parse('2026-11-14T00:00:00Z')

// field 改为 ref：evidence-refs 到达后重新计算，让 EvidenceBed 渲染真实证据带
const field = ref(computeField(knowledgeEntries, knowledgeDomains, [], { now: SP_NOW }))

// bindingIndex（无洞察 → 全 operational → 无 threads，但接口先预留）
const bindingIndex = buildBindingIndex(knowledgeEntries, [])

// —— 相机（受限轨道 + 三机位预设）——
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const cam = useFieldCamera({ reducedMotion })

// evidence enrich 状态
const enrichStatus = ref('idle') // idle | loading | ready | error
const enrichError = ref('')
const enrichedCount = ref(0)
const enrichStatusClass = computed(() => ({
  'sf-stat--bound': enrichStatus.value === 'ready',
  'sf-stat--stale': enrichStatus.value === 'error',
}))

/**
 * M2：挂载后批量拉取所有已 ingest 条目的 evidence-refs，
 * 合并到 knowledgeEntries 后重算 field，让 EvidenceBed / ThreadLayer / InsightCanopy 有真实内容。
 *
 * 后端批量端点：GET /api/knowledge/evidence-refs → { refsByEntry, ingestedAt, count }
 * 开发环境通过 vite 代理 /ks → 知识服务（8002）。
 */
async function enrichEvidenceRefs() {
  enrichStatus.value = 'loading'
  enrichError.value = ''
  try {
    const res = await fetch('/ks/api/knowledge/evidence-refs')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const refsByEntry = data?.refsByEntry || {}
    const enriched = knowledgeEntries.map(e => {
      const refs = refsByEntry[e.id]
      if (!Array.isArray(refs) || refs.length === 0) return e
      return { ...e, evidenceRefs: refs }
    })
    enrichedCount.value = Object.keys(refsByEntry).length
    field.value = computeField(enriched, knowledgeDomains, [], { now: SP_NOW })
    enrichStatus.value = 'ready'
  } catch (err) {
    enrichStatus.value = 'error'
    enrichError.value = err.message || '证据加载失败'
    // 失败不阻塞：field 保持初始计算（无证据带）
  }
}

// LOD 判断（DESIGN §6.1：按相机 dist）
function computeLod (dist) {
  if (cam.focusPlaneId.value) return 'focus'
  if (dist <= 620) return 'near'
  if (dist <= 1200) return 'mid'
  return 'far'
}
const currentLod = computed(() => computeLod(cam.dist.value))

// —— 性能闸门（DESIGN §6.2）——
const MAX_MOUNT = 480
const MAX_VISIBLE = 180

// 可见平面：按距相机 target 的距离升序排，取前 MAX_MOUNT
const mountedPlanes = computed(() => {
  const planes = field.value.planes
  if (planes.length <= MAX_MOUNT) return planes
  const tx = cam.target.x, ty = cam.target.y, tz = cam.target.z
  const sorted = [...planes].sort((a, b) =>
    Math.hypot(a.x - tx, a.y - ty, a.z - tz) -
    Math.hypot(b.x - tx, b.y - ty, b.z - tz)
  )
  console.warn('[field] plane budget exceeded', planes.length, 'capping at', MAX_MOUNT)
  return sorted.slice(0, MAX_MOUNT)
})

// —— 线程屏幕空间坐标换算（简化版：先用世界坐标占位，ThreadLayer 后续接）——
// 线程从 field.threads 里取，ScreenThread 是 ThreadLayer 需要的格式
const screenThreads = computed(() =>
  field.value.threads.map(t => ({
    ...t,
    from: { x: t.from.x, y: t.from.y },
    to:   { x: t.to.x,   y: t.to.y },
  }))
)

// —— 轨道拖拽 & 滚轮 ——
function onWheel (e) {
  e.preventDefault()
  cam.zoom(Math.exp(-e.deltaY * 0.0015))
}
function onPointerDown (e) {
  if (e.target.closest('.field-hud')) return
  dragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartYaw = cam.yaw.value
  dragStartPitch = cam.pitch.value
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}
function onPointerMove (e) {
  if (!dragging.value) return
  const dx = e.clientX - dragStartX
  const dy = e.clientY - dragStartY
  // 指针移 1px ≈ 0.3° 旋转
  cam.orbitTo({
    yaw:   dragStartYaw   + dx * 0.35,
    pitch: dragStartPitch - dy * 0.25,  // 上拖 = 视角上看 = pitch 减小（更俯视）
  })
}
function onPointerUp () {
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}

const dragging = ref(false)
let dragStartX = 0, dragStartY = 0, dragStartYaw = 0, dragStartPitch = 0

// —— 键盘（DESIGN §5.3）——
function onKeyDown (e) {
  // 1/2/3 机位切换
  if (e.key === '1') { cam.setPreset('overlook'); return }
  if (e.key === '2') { cam.setPreset('shelf'); return }
  if (e.key === '3') { /* trace 需选中链条，暂留 */ return }
  // Esc 回退
  if (e.key === 'Escape') {
    const result = cam.back()
    if (result === 'domain' && cam.focusDomainId.value) {
      // 跳回域中心（简化：用域锚点 x 作为 target.x）
      const anchor = field.value.axes.domains.find(d => d.id === cam.focusDomainId.value)
      if (anchor) cam.orbitTo({ tx: anchor.x, ty: FIELD.knowledge.y0 + 80 })
    }
    return
  }
  // Ctrl+K 检索（占位）
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); return }
}

// —— plane 点击 → focus 下钻 ——
function onPlaneClick (plane) {
  cam.focusOn(plane)
}
function onPlaneKeydown (plane) {
  cam.focusOn(plane)
}

function onFieldClick (insight) {
  // insight 点击 → trace 机位
  cam.setPreset('trace', { cx: insight.x ?? cam.target.x })
}

// —— 状态（HUD 用）——
const fieldStats = computed(() => ({
  planes: field.value.planes.length,
  evidenceBands: field.value.evidenceBands.length,
  threads: bindingIndex.threads.length,
  bound: bindingIndex.stats.bound,
  operational: bindingIndex.stats.operational,
  staleAtoms: bindingIndex.stats.staleAtoms,
  lod: currentLod.value,
  yaw: cam.yaw.value,
  pitch: cam.pitch.value,
  dist: cam.dist.value,
}))

onMounted(() => {
  cam.setPreset('overlook')
  window.addEventListener('keydown', onKeyDown)
  enrichEvidenceRefs()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
})

// 导出 camera + planes 给外部 slot 扩展
defineExpose({ cam, field })
</script>

<template>
  <section class="space-field">
    <!-- HUD（DESIGN §5.2 / B6：显示 bindingIndex.stats 五计数） -->
    <header class="sf-hud field-hud">
      <div class="sf-hud-group">
        <b>知识空间场</b>
        <span class="sf-sep">·</span>
        <span>{{ fieldStats.planes }} 平面</span>
        <span>{{ fieldStats.evidenceBands }} 证据带</span>
        <span class="sf-sep">·</span>
        <span class="sf-stat" :class="enrichStatusClass">
          <template v-if="enrichStatus === 'loading'">证据加载中…</template>
          <template v-else-if="enrichStatus === 'ready'">证据已载入 {{ enrichedCount }} 条</template>
          <template v-else-if="enrichStatus === 'error'">证据加载失败</template>
          <template v-else>证据待载入</template>
        </span>
        <span class="sf-sep">·</span>
        <span class="sf-stat sf-stat--bound">已绑定 {{ fieldStats.bound }}</span>
        <span class="sf-stat sf-stat--op">纯运行态 {{ fieldStats.operational }}</span>
        <span class="sf-stat sf-stat--stale" v-if="fieldStats.staleAtoms">过期 {{ fieldStats.staleAtoms }}</span>
      </div>
      <div class="sf-hud-group sf-hud-group--right">
        <kbd class="sf-kbd sf-kbd--on">1</kbd><span>总览</span>
        <kbd class="sf-kbd">2</kbd><span>平视</span>
        <kbd class="sf-kbd">3</kbd><span>沿链</span>
        <kbd class="sf-kbd">Esc</kbd><span>回退</span>
        <span class="sf-sep">·</span>
        <span>Yaw {{ Math.round(fieldStats.yaw) }}°</span>
        <span>Pitch {{ Math.round(fieldStats.pitch) }}°</span>
        <span>Dist {{ fieldStats.dist }}</span>
        <span class="sf-sep">·</span>
        <span>LOD {{ fieldStats.lod }}</span>
      </div>
    </header>

    <!-- FieldStage（CSS 3D 空间场容器） -->
    <FieldStage
      class="sf-stage"
      :camera="cam"
      :world-size="{ w: 7200, h: 660, d: 2000 }"
      @wheel.passive="onWheel"
      @pointerdown="onPointerDown"
    >
      <!-- EvidenceBed（Canvas2D L0 证据层，translateZ 最底层） -->
      <EvidenceBed
        :bands="field.evidenceBands"
        :world-transform="''"
        :world-size="{ w: 7200, h: 2000 }"
      />

      <!-- FieldPlane × N（知识/洞察平面，translate3d 3D 定位） -->
      <template v-for="plane in mountedPlanes" :key="plane.id">
        <FieldPlane
          :plane="plane"
          :lod="currentLod"
          :is-focus="cam.focusPlaneId === plane.id"
          @click="onPlaneClick(plane)"
          @keydown="onPlaneKeydown(plane)"
        />
      </template>
    </FieldStage>

    <!-- ThreadLayer（SVG 屏幕空间叠加，覆盖 FieldStage） -->
    <ThreadLayer
      class="sf-threads"
      :threads="screenThreads"
      :operational-anchors="[]"
    />

    <!-- InsightCanopy（L2 洞察带，Phase A 无真实洞察 → 先不渲染） -->
    <template v-for="ip in field.planes.filter(p => p.kind === 'insight')" :key="ip.id">
      <InsightCanopy
        :insight="{ id: ip.insightId, binding: { mode: 'operational', atoms: [], explanation: 'Phase A 无后端洞察' } }"
        :position="{ x: ip.x, y: ip.y }"
        :lod="currentLod"
        @click="onFieldClick"
      />
    </template>

    <!-- 轴图例（DESIGN A2：三轴语义 UI 可见） -->
    <div class="sf-axis-legend" aria-hidden="true">
      <div><b>X</b> 领域轴：{{ field.axes.domains.length }} 域</div>
      <div><b>Y</b> 抽象层级：证据 0–140 / 知识 240–420 / 洞察 520–660</div>
      <div><b>Z</b> 版本时序：历史 ← 0 → 未来</div>
    </div>
  </section>
</template>

<style scoped>
.space-field {
  position: relative;
  flex: 1 1 auto;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: radial-gradient(120% 90% at 50% 0%, rgba(16,22,29,1) 0%, rgba(10,14,19,1) 60%, rgba(7,10,14,1) 100%);
  isolation: isolate;
}

.sf-hud {
  position: absolute;
  top: 56px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  padding: 0 16px;
  z-index: 30;
  pointer-events: none;
}
.sf-hud-group {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: rgba(14,17,22,.92);
  color: var(--ds-color-muted);
  font: 11px var(--ds-font-mono);
  font-variant-numeric: tabular-nums;
  pointer-events: auto;
}
.sf-hud-group b { color: var(--ds-color-text); font-weight: 500; font-size: 12px; font-family: var(--ds-font-cn); }
.sf-sep { color: var(--ds-semantic-neutral); }
.sf-stat--bound  { color: var(--ds-accent, #7ad7f5); }
.sf-stat--op     { color: var(--ds-semantic-neutral); font-style: italic; }
.sf-stat--stale  { color: var(--ds-pill-warning-fg, #f5a623); }

.sf-kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border: 1px solid var(--ds-hairline);
  border-radius: 3px;
  background: rgba(0,0,0,.25);
  color: var(--ds-color-text);
  font: 10px var(--ds-font-mono);
}
.sf-kbd--on { border-color: var(--ds-accent, #7ad7f5); color: var(--ds-accent, #7ad7f5); }

.sf-stage {
  position: absolute;
  inset: 0;
  padding-top: 0;
  cursor: grab;
}
.sf-stage:active { cursor: grabbing; }

.sf-threads {
  position: absolute;
  inset: 0;
  z-index: 25;
  pointer-events: stroke;
}

.sf-axis-legend {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 30;
  max-width: 320px;
  padding: 10px 12px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: rgba(14,17,22,.92);
  font-size: 11px;
  line-height: 1.7;
  color: var(--ds-color-muted);
}
.sf-axis-legend b { color: var(--ds-accent, #7ad7f5); font-weight: 500; }

/* 断点 375：禁自由轨道（DESIGN §8） */
@media (max-width: 375px) {
  .sf-stage { cursor: default; }
  .sf-threads { display: none; }
  .sf-axis-legend { display: none; }
}
</style>
