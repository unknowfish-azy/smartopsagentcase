<template>
  <svg ref="svgEl" :viewBox="`0 0 ${box.w} ${box.h}`" role="img" aria-label="eNSP 拓扑图">
    <line v-for="(l, i) in graph.links" :key="'l' + i"
          :x1="center(l.srcDeviceId).x" :y1="center(l.srcDeviceId).y"
          :x2="center(l.dstDeviceId).x" :y2="center(l.dstDeviceId).y"
          class="link" />
    <text v-for="(l, i) in graph.links" :key="'lt' + i"
          :x="(center(l.srcDeviceId).x + center(l.dstDeviceId).x) / 2"
          :y="(center(l.srcDeviceId).y + center(l.dstDeviceId).y) / 2 - 6"
          class="link-label">{{ l.lineName || `${l.srcPort} ↔ ${l.dstPort}` }}</text>
    <g v-for="d in graph.devices" :key="d.id" :transform="`translate(${d.x},${d.y})`">
      <rect x="-42" y="-22" width="84" height="44" rx="7" class="device" />
      <text y="-3" class="device-name">{{ d.name }}</text>
      <text y="13" class="device-model">{{ d.model }}</text>
    </g>
    <text v-for="(t, i) in graph.tips" :key="'t' + i"
          :x="Number(t.left)" :y="Number(t.top)" class="tip">{{ t.content }}</text>
  </svg>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  graph: { type: Object, required: true }
})
const svgEl = ref(null)

const box = computed(() => {
  const devices = props.graph.devices || []
  const tips = props.graph.tips || []
  const xs = devices.map(d => Number(d.x) || 0)
  const ys = devices.map(d => Number(d.y) || 0)
  const tx = tips.map(t => Number(t.left) || 0)
  const ty = tips.map(t => Number(t.top) || 0)
  const w = Math.max(400, ...xs, ...tx) + 140
  const h = Math.max(300, ...ys, ...ty) + 140
  return { w, h }
})

function center(deviceId) {
  const d = (props.graph.devices || []).find(x => x.id === deviceId)
  if (!d) return { x: 0, y: 0 }
  return { x: Number(d.x) || 0, y: Number(d.y) || 0 }
}
</script>

<style scoped>
.link{stroke:var(--smart-primary-strong);stroke-width:2;opacity:.55}
.link-label{font-size:11px;fill:var(--smart-muted);text-anchor:middle}
.device{fill:var(--smart-surface);stroke:var(--smart-primary-strong);stroke-width:1.5}
.device-name{font-size:13px;font-weight:700;fill:var(--smart-text);text-anchor:middle}
.device-model{font-size:10px;fill:var(--smart-muted);text-anchor:middle}
.tip{font-size:11px;fill:var(--smart-muted)}
</style>
