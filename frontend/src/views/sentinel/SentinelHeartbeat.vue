<template>
  <div class="heartbeat">
    <div class="heartbeat__strip" role="list" aria-label="最近采样，从旧到新">
      <span v-for="(sample, index) in cells" :key="index" role="listitem" :class="['heartbeat__cell', `heartbeat__cell--${sample.status}`]" :title="sample.label" :aria-label="sample.label"></span>
    </div>
    <small>{{ samples.length ? '较早 ← 最近采样 → 最新' : '暂无采样' }}</small>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { heartbeatCells } from './heartbeat.js'
const props = defineProps({ samples: { type: Array, default: () => [] } })
const cells = computed(() => heartbeatCells(props.samples))
</script>
<style scoped>
.heartbeat { min-width:180px; max-width:300px; }
.heartbeat__strip { display:grid; grid-template-columns:repeat(30,minmax(0,1fr)); gap:3px; padding-block:8px; }
.heartbeat__cell { height:22px; border-radius:1px; background:var(--smart-muted); }
.heartbeat__cell--unknown { background:transparent; border:1px solid var(--smart-border); }
.heartbeat__cell--up { background:var(--smart-success); }
.heartbeat__cell--down { background:var(--smart-danger); }
.heartbeat__cell--degraded { background:var(--smart-warning); }
.heartbeat__cell--maintenance { background:var(--smart-primary-strong); }
.heartbeat small { color:var(--smart-text); font-size:11px; }
</style>
