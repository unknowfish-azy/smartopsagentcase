<template>
  <!-- 缆线：轨道中心 → 工位的下沉二次贝塞尔；脉冲光点 = E2（一次事件一颗，不常驻） -->
  <g class="ws-cable" :data-tone="tone">
    <path class="ws-cable-line" :d="pathD" />
    <circle
      v-if="progress != null"
      class="ws-cable-pulse"
      :cx="pulsePoint.x"
      :cy="pulsePoint.y"
      r="2.6"
    />
  </g>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  from: { type: Object, required: true }, // {sx, sy}
  to: { type: Object, required: true }, // {sx, sy}
  tone: { type: String, default: 'gaze' },
  /** 0..1；null = 无脉冲（静默） */
  progress: { type: Number, default: null }
})

const SAG = 14

const ctrl = computed(() => ({
  x: (props.from.sx + props.to.sx) / 2,
  y: (props.from.sy + props.to.sy) / 2 + SAG
}))

const pathD = computed(
  () => `M${props.from.sx} ${props.from.sy} Q${ctrl.value.x} ${ctrl.value.y} ${props.to.sx} ${props.to.sy}`
)

/** 二次贝塞尔取点（纯计算，无 DOM 测量）。 */
const pulsePoint = computed(() => {
  const t = Math.max(0, Math.min(1, Number(props.progress) || 0))
  const u = 1 - t
  return {
    x: u * u * props.from.sx + 2 * u * t * ctrl.value.x + t * t * props.to.sx,
    y: u * u * props.from.sy + 2 * u * t * ctrl.value.y + t * t * props.to.sy
  }
})
</script>

<style scoped>
.ws-cable-line {
  fill: none;
  stroke: var(--fab-paper-26, rgba(232, 242, 247, 0.26));
  stroke-width: 0.8;
  stroke-dasharray: 2 4;
}

.ws-cable[data-tone='sage'] { --ws-tone: var(--fab-sage, #8bcfb4); }
.ws-cable[data-tone='clay'] { --ws-tone: var(--fab-clay, #2496ed); }
.ws-cable[data-tone='butter'] { --ws-tone: var(--fab-butter, #d9b96d); }
.ws-cable[data-tone='apricot'] { --ws-tone: var(--fab-apricot, #7ad7f5); }
.ws-cable[data-tone='gaze'] { --ws-tone: var(--fab-gaze, #7ad7f5); }
.ws-cable[data-tone='plum'] { --ws-tone: var(--fab-plum, #9b8cf0); }

.ws-cable-pulse {
  fill: var(--ws-tone, var(--fab-gaze, #7ad7f5));
  opacity: 0.9;
}
</style>
