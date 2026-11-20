<!--
  FieldPlane.vue — 单个世界平面（照片墙风格）。

  结构：外层 .field-plane 负责 3D 定位（translate3d），内层 .fp-card 负责视觉与 hover。
  这样 hover 的 scale/translateZ 不会覆盖定位 transform。

  照片墙式正方形卡片（112×112）：
    - 顶部 4px 域色彩条（照片基调色）
    - 类型 chip（居中）
    - 标题（居中，2 行截断）
    - 底部风险点 + 1 个标签
    - 过期灰化
    - hover：scale(1.12) 浮起 + 发光边框

  LOD：far → 仅色条；mid/near/focus → 完整卡片
-->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  plane:   { type: Object, required: true },
  lod:     { type: String, default: 'mid' },
  isFocus: { type: Boolean, default: false },
  hit:     { type: Boolean, default: false },
})

const emit = defineEmits(['click', 'keydown'])

const showTypeChip = computed(() => ['mid', 'near', 'focus'].includes(props.lod))
const showTitle    = computed(() => ['mid', 'near', 'focus'].includes(props.lod))
const showFooter   = computed(() => ['near', 'focus'].includes(props.lod))
const interactive  = computed(() => ['near', 'focus'].includes(props.lod))

// 外层：仅 3D 定位
const planeStyle = computed(() => ({
  transform: `translate3d(${props.plane.x}px, ${-props.plane.y}px, ${props.plane.z}px)`,
  width: `${props.plane.w}px`,
  height: `${props.plane.h}px`,
}))

const isInsight = computed(() => props.plane.kind === 'insight')
const isStale = computed(() => props.plane.staleness && props.plane.staleness !== 'FRESH' && props.plane.staleness !== 'UNKNOWN')

/* —— 类型 → 颜色 —— */
const TYPE_COLORS = {
  RUNBOOK: '#4a9eff', INCIDENT: '#ff6b6b', 'DIAGNOSIS RUNBOOK': '#22d3ee',
  DIAGNOSIS_RUNBOOK: '#22d3ee', ENGINEERING: '#51cf66',
  'ENGINEERING KNOWLEDGE': '#51cf66', QUESTION: '#9775fa',
  WRONG_ANSWER: '#ff922b', ANTI_PATTERN: '#e03131',
}
function typeColor (t) {
  const key = String(t || '').toUpperCase()
  for (const [k, c] of Object.entries(TYPE_COLORS)) if (key.includes(k)) return c
  return '#868e96'
}
const typeColorValue = computed(() => typeColor(props.plane.type))

/* —— 域 → 渐变（照片基调色条）—— */
const DOMAIN_GRADIENTS = {
  linux: 'linear-gradient(135deg,#1e3a5f 0%,#0f766e 100%)',
  'cloud-operations': 'linear-gradient(135deg,#3b1d6e 0%,#6d28d9 100%)',
  docker: 'linear-gradient(135deg,#0c4a6e 0%,#2563eb 100%)',
  mysql: 'linear-gradient(135deg,#7c2d12 0%,#ea580c 100%)',
  nginx: 'linear-gradient(135deg,#14532d 0%,#16a34a 100%)',
  ubuntu: 'linear-gradient(135deg,#7f1d1d 0%,#dc2626 100%)',
  centos: 'linear-gradient(135deg,#581c87 0%,#9333ea 100%)',
  network: 'linear-gradient(135deg,#134e4a 0%,#0d9488 100%)',
  'web-lamp': 'linear-gradient(135deg,#7f1d1d 0%,#f97316 100%)',
  'linux-services': 'linear-gradient(135deg,#0c4a6e 0%,#0891b2 100%)',
}
const headerGradient = computed(() => DOMAIN_GRADIENTS[props.plane.domainId] || 'linear-gradient(135deg,#1e293b 0%,#475569 100%)')

/* —— 风险 —— */
function riskColor (r) {
  const k = String(r || '').toUpperCase()
  if (k.includes('HIGH') || k.includes('CRITICAL')) return '#ef4444'
  if (k.includes('MEDIUM')) return '#f59e0b'
  if (k.includes('LOW') || k.includes('READ')) return '#22c55e'
  return '#64748b'
}
const riskColorValue = computed(() => riskColor(props.plane.risk))
const hasRisk = computed(() => {
  const k = String(props.plane.risk || '').toUpperCase()
  return k.includes('HIGH') || k.includes('CRITICAL') || k.includes('MEDIUM') || k.includes('LOW') || k.includes('READ')
})

/* —— 类型短名 —— */
const typeShort = computed(() => {
  const t = String(props.plane.type || '').toUpperCase()
  if (t.includes('RUNBOOK')) return 'RUNBOOK'
  if (t.includes('INCIDENT')) return 'INCIDENT'
  if (t.includes('DIAGNOSIS')) return 'DIAG'
  if (t.includes('ENGINEERING')) return 'ENG'
  if (t.includes('QUESTION')) return 'Q&A'
  if (t.includes('WRONG')) return 'WRONG'
  if (t.includes('ANTI')) return 'ANTI'
  return t.slice(0, 6) || 'KNOW'
})

/* —— 第一个标签 —— */
const firstTag = computed(() => Array.isArray(props.plane.tags) && props.plane.tags.length ? props.plane.tags[0] : '')
</script>

<template>
  <div
    v-if="plane"
    class="field-plane"
    :class="{ 'field-plane--far': lod === 'far' }"
    :style="planeStyle"
    :data-kind="plane.kind"
    :data-lod="lod"
    :aria-hidden="!interactive"
    :tabindex="interactive ? 0 : -1"
    :aria-label="interactive
      ? (isInsight ? `洞察层 · ${plane.insightId || ''}` : `知识层 · ${plane.domainId || ''} · ${plane.title || plane.atomId || ''}`)
      : ''"
    role="button"
    @click="emit('click', plane)"
    @keydown.enter.prevent="emit('keydown', plane)"
  >
    <!-- 内层：视觉卡片 + hover 效果 -->
    <div
      class="fp-card"
      :class="{
        'fp-card--insight': isInsight,
        'fp-card--knowledge': !isInsight,
        'fp-card--hit': hit,
        'fp-card--focus': isFocus,
        'fp-card--stale': isStale,
      }"
    >
      <template v-if="lod !== 'far'">
        <!-- 顶部 4px 域色彩条（照片基调） -->
        <span class="fp-color-bar" :style="{ background: headerGradient }"></span>

        <div class="fp-body">
          <!-- 类型 chip 居中 -->
          <span v-if="showTypeChip" class="fp-type-chip" :style="{ borderColor: typeColorValue, color: typeColorValue }">
            {{ typeShort }}
          </span>

          <!-- 标题居中，2 行截断 -->
          <span v-if="showTitle" class="fp-title">{{ plane.title || plane.atomId || plane.insightId }}</span>

          <!-- 底部：风险点 + 1 个标签 -->
          <div v-if="showFooter" class="fp-footer">
            <span v-if="hasRisk" class="fp-risk-dot" :style="{ background: riskColorValue }"></span>
            <span v-if="firstTag" class="fp-tag">{{ firstTag }}</span>
          </div>
        </div>
      </template>

      <!-- far：仅彩色色条 -->
      <span v-else class="fp-far-bar" :style="{ background: headerGradient }"></span>
    </div>
  </div>
</template>

<style scoped>
/* 外层：仅 3D 定位，不做视觉 */
.field-plane {
  position: absolute;
  transform-style: preserve-3d;
  min-height: 44px;
  min-width: 44px;
}

/* 内层：视觉卡片 */
.fp-card {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: stretch;
  border-radius: 6px;
  box-sizing: border-box;
  overflow: hidden;
  cursor: pointer;
  transform: translateZ(0);
  transition: transform 120ms var(--ds-ease-out, ease),
              box-shadow 120ms var(--ds-ease-out, ease),
              border-color 120ms var(--ds-ease-out, ease),
              filter 200ms ease;
  will-change: transform;
}

.fp-card--knowledge {
  background: var(--ds-surface, #0a0f14);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: 0 2px 8px rgba(0,0,0,.4);
}
/* hover：照片浮起 + 发光边框 */
.fp-card--knowledge:hover {
  transform: translateZ(16px) scale(1.12);
  border-color: rgba(122,215,245,.6);
  box-shadow: 0 10px 28px rgba(0,0,0,.65), 0 0 0 1px rgba(122,215,245,.4),
              0 0 16px rgba(122,215,245,.15);
  z-index: 10;
}

/* 顶部域色彩条 */
.fp-color-bar {
  height: 4px;
  flex-shrink: 0;
}

.fp-body {
  padding: 6px 5px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
  overflow: hidden;
}

/* 类型 chip 居中 */
.fp-type-chip {
  font-size: 7px;
  letter-spacing: .04em;
  font-family: var(--ds-font-mono, monospace);
  font-weight: 600;
  padding: 0 4px;
  border: 1px solid;
  border-radius: 2px;
  background: rgba(0,0,0,.4);
  line-height: 1.4;
  white-space: nowrap;
}

/* 标题居中，2 行截断 */
.fp-title {
  font-size: 10px;
  font-weight: 600;
  line-height: 1.25;
  color: var(--ds-color-text, #e2e8f0);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* 底部：风险点 + 标签 */
.fp-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.fp-tag {
  font-size: 7px;
  padding: 0 4px;
  border-radius: 2px;
  background: rgba(122,215,245,.12);
  color: var(--ds-accent, #7ad7f5);
  font-family: var(--ds-font-mono, monospace);
  white-space: nowrap;
  max-width: 52px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fp-risk-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  box-shadow: 0 0 4px currentColor;
  flex-shrink: 0;
}

/* 命中 / 聚焦态 */
.fp-card--hit {
  border-color: var(--ds-focus-ring-color, #7ad7f5);
  box-shadow: 0 0 0 2px rgba(122,215,245,.35), 0 6px 20px rgba(0,0,0,.55);
}
.fp-card--focus {
  border-color: var(--ds-focus-ring-color, #7ad7f5);
  box-shadow: 0 0 0 2px var(--ds-focus-ring-color, #7ad7f5), 0 8px 24px rgba(0,0,0,.6);
  z-index: 5;
  transform: translateZ(24px) scale(1.1);
}

/* 过期：降饱和 + 灰罩 */
.fp-card--stale {
  filter: saturate(0.4) brightness(0.85);
}
.fp-card--stale::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(30,41,59,.25);
  pointer-events: none;
  border-radius: 6px;
}

/* far：仅色条 */
.fp-far-bar {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 4px;
  border-radius: 6px 6px 0 0;
}
.field-plane--far .fp-card {
  background: rgba(10,15,20,.6);
  border: 1px solid rgba(255,255,255,.05);
}

/* 洞察平面 */
.fp-card--insight {
  background: transparent;
  border: 1px dashed rgba(159,190,207,.2);
}
</style>
