<template>
  <svg
    class="rg-lanes"
    :width="padLeft"
    :height="height"
    aria-hidden="true"
    focusable="false"
  >
    <path
      v-for="segment in segments"
      :key="segment.key"
      :d="segment.path"
      :stroke="segment.color"
      :stroke-dasharray="segment.dashed ? '4 3' : undefined"
      stroke-width="1.5"
      fill="none"
      stroke-linecap="round"
    />
    <template v-for="node in nodes" :key="node.key">
      <rect
        v-if="node.shape === 'entry'"
        :x="node.x - 6"
        :y="node.y - 6"
        width="12"
        height="12"
        rx="3"
        :fill="node.fill"
        :stroke="node.color"
        stroke-width="1.6"
      />
      <circle
        v-else-if="node.shape === 'event'"
        :cx="node.x"
        :cy="node.y"
        :r="node.hollow ? 5 : 4.5"
        :fill="node.hollow ? 'var(--ds-surface-base)' : node.color"
        :stroke="node.hollow ? node.color : 'none'"
        :stroke-width="node.hollow ? 2 : 0"
      />
      <circle
        v-else-if="node.shape === 'dot'"
        :cx="node.x"
        :cy="node.y"
        r="3"
        :fill="node.color"
      />
    </template>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { QUIET_LANE_COLOR, laneCenter, laneSegments } from './useReviewGraph.js'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  lanes: { type: Array, default: () => [] },
  padLeft: { type: Number, default: 0 },
  height: { type: Number, default: 0 }
})

const colorByLane = computed(() => new Map(props.lanes.map(lane => [lane.index, lane.color])))

/* 泳道线：分段由行模型的 laneSegments 给出（待审段虚线、已决策段实线），
   宽度不写 viewBox，1 用户单位 = 1 CSS 像素。 */
const segments = computed(() => props.lanes.flatMap(lane => {
  const x = laneCenter(lane.index)
  return laneSegments(props.rows, lane.index).map((segment, index) => ({
    key: `seg-${lane.index}-${index}`,
    dashed: segment.dashed,
    path: segment.top === segment.bottom
      ? `M${x},${segment.top - 6} L${x},${segment.top + 6}`
      : `M${x},${segment.top} L${x},${segment.bottom}`,
    color: colorByLane.value.get(lane.index) || QUIET_LANE_COLOR
  }))
}))

const nodes = computed(() => props.rows.flatMap(row => {
  if (row.lane == null || row.kind === 'gap') return []
  const x = laneCenter(row.lane)
  const y = row.y + row.h / 2
  const color = colorByLane.value.get(row.lane) || QUIET_LANE_COLOR
  if (row.kind === 'entry') {
    return [{ key: `node-${row.id}`, shape: 'entry', x, y, color, fill: 'var(--ds-surface-raised)' }]
  }
  if (row.kind === 'commit') {
    const adopt = row.event?.kind === 'adopt'
    return [{
      key: `node-${row.id}`,
      shape: 'event',
      x,
      y,
      hollow: adopt,
      color: adopt ? color : 'var(--ds-semantic-neutral)'
    }]
  }
  return []
}))
</script>
