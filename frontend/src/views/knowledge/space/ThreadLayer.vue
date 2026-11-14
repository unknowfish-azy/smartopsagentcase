<!--
  ThreadLayer.vue — P5 论证链（DESIGN §3.2）。

  SVG 屏幕空间叠加层（position: absolute 覆盖 FieldStage），与世界坐标同步换算。
  每条线 = 洞察平面底边中点 → 知识平面顶边中点。

  视觉配方（DESIGN §3.2）：
    普通 derived/corroborates：accent-soft → accent 渐变，1px
    contradicts：虚线 + 端点菱形，status 警示色
    operational：短横线 + 空心端点（无知识依赖）
  hover：2px + 浮出 relation 标签（derived/corroborates/contradicts）

  本组件不持有世界坐标 → 屏幕空间的换算逻辑，由父组件 FieldStage
  或 KnowledgeSpaceView 传入屏幕空间的 from/to 对（通过 computed）。
-->
<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  // 每条 thread 已经是屏幕空间坐标（由父组件从世界坐标换算好）
  threads: {
    type: Array,
    default: () => [],
    /*
      [{
        insightId, atomId, relation, weight, stale,
        from: {x, y},    // 屏幕空间
        to:   {x, y},    // 屏幕空间
        operational: false
      }]
    */
  },
  // operational 洞察的锚点（屏幕空间）
  operationalAnchors: {
    type: Array,
    default: () => [],
    /* [{ insightId, x, y }] */
  },
})

const emit = defineEmits(['hover'])

const hoverThreadId = ref(null)

function strokeColor (thread) {
  if (thread.relation === 'contradicts') return 'var(--ds-semantic-danger, #f56c6c)'
  // 普通 derived/corroborates 用 accent
  if (thread.stale) return 'rgba(159,190,207,.28)'  // stale → 虚化
  return 'var(--ds-accent, #7ad7f5)'
}

function strokeDash (thread) {
  if (thread.relation === 'contradicts') return '6 4'
  return undefined  // 实线
}

function strokeWidth (thread, isHover) {
  return isHover ? 2 : 1
}

const sortedThreads = computed(() =>
  [...props.threads].sort((a, b) =>
    a.insightId !== b.insightId ? a.insightId.localeCompare(b.insightId)
    : a.atomId.localeCompare(b.atomId)
  )
)

function onMouseEnter (thread) {
  hoverThreadId.value = `${thread.insightId}:${thread.atomId}`
  emit('hover', thread)
}
function onMouseLeave () { hoverThreadId.value = null }
</script>

<template>
  <svg class="thread-layer" aria-hidden="true" role="presentation">
    <defs>
      <!-- 渐变：accent-soft → accent（洞察→知识方向） -->
      <linearGradient id="grad-thread" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%"   stop-color="var(--ds-accent-soft, rgba(122,215,245,.35))" />
        <stop offset="100%" stop-color="var(--ds-accent, #7ad7f5)" />
      </linearGradient>
    </defs>

    <!-- 普通 threads -->
    <g v-for="t in sortedThreads" :key="`${t.insightId}-${t.atomId}`"
       :data-thread="`${t.insightId}:${t.atomId}`"
       class="thread"
       :class="{ 'thread--contradicts': t.relation === 'contradicts',
                 'thread--stale': t.stale,
                 'thread--hover': hoverThreadId === `${t.insightId}:${t.atomId}` }"
       @mouseenter="onMouseEnter(t)"
       @mouseleave="onMouseLeave">

      <line
        :x1="t.from?.x ?? 0" :y1="t.from?.y ?? 0"
        :x2="t.to?.x ?? 0"   :y2="t.to?.y ?? 0"
        :stroke="strokeColor(t)"
        :stroke-width="strokeWidth(t, hoverThreadId === `${t.insightId}:${t.atomId}`)"
        :stroke-dasharray="strokeDash(t)"
        stroke-linecap="round"
        fill="none"
      />
      <!-- contradicts 菱形端点 -->
      <polygon
        v-if="t.relation === 'contradicts'"
        :points="`${t.to?.x ?? 0},${(t.to?.y ?? 0) - 4} ${(t.to?.x ?? 0) + 4},${t.to?.y ?? 0} ${t.to?.x ?? 0},${(t.to?.y ?? 0) + 4} ${(t.to?.x ?? 0) - 4},${t.to?.y ?? 0}`"
        :fill="strokeColor(t)"
      />
    </g>

    <!-- operational 洞察：短横线 + 空心端点 -->
    <g v-for="a in operationalAnchors" :key="`op-${a.insightId}`"
       :data-thread="a.insightId"
       class="thread thread--operational">
      <line
        :x1="a.x - 8" :y1="a.y"
        :x2="a.x + 8" :y2="a.y"
        stroke="var(--ds-text-secondary, rgba(159,190,207,.45))"
        stroke-width="1"
        stroke-linecap="round"
      />
      <circle :cx="a.x" :cy="a.y" r="3.5"
        fill="none"
        stroke="var(--ds-text-secondary, rgba(159,190,207,.45))"
        stroke-width="1"
      />
    </g>
  </svg>
</template>

<style scoped>
.thread-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
  z-index: 20;
}
.thread { pointer-events: stroke; }  /* 允许 hover */
.thread--stale line { opacity: .35; }
.thread--hover line { filter: drop-shadow(0 0 3px var(--ds-accent, #7ad7f5)); }
</style>
