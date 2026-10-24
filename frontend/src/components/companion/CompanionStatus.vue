<template>
  <section class="companion-status" aria-label="Companion status">
    <span class="status-dot" :class="`status-dot--${overallStatus}`"></span>
    <details>
      <summary class="status-copy">COMPANION · 本地模式</summary>
      <div class="status-details">
        <p>SEE {{ store.states.spider }} · THINK {{ store.states.jellyfish }} · KNOW {{ store.states.whale }}</p>
        <label>提醒模式 <select aria-label="提醒模式" :value="store.states.interaction" @change="store.setInteractionMode($event.target.value)"><option>NORMAL</option><option>FOCUS</option><option>QUIET</option></select></label>
        <p v-for="(capability, name) in store.capabilities" :key="name">{{ name }} · {{ capability.status }}<br><small>{{ capability.detail }}</small></p>
        <p v-if="store.lastError" role="status">{{ store.lastError }}</p>
        <button v-if="store.context.faultEvent" type="button" @click="store.openInvestigation()">继续调查</button>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useCompanionStore } from '../../stores/companion.js'

const store = useCompanionStore()
const degradedCount = computed(() => Object.values(store.capabilities).filter(value => (value?.status || value) !== 'available').length)
const overallStatus = computed(() => degradedCount.value ? 'degraded' : 'ready')
</script>

<style scoped>
.companion-status{position:relative}summary{cursor:pointer}.status-details{position:absolute;right:0;top:26px;z-index:40;width:min(320px,85vw);padding:16px;border:1px solid var(--smart-border-strong);background:#071018;color:var(--smart-text);font:12px/1.6 var(--font-cn);letter-spacing:0;white-space:normal}.status-details select,.status-details button{background:#071018;color:var(--smart-text);border:1px solid var(--smart-border-strong);padding:6px}.status-details small{color:var(--smart-muted)}
.companion-status{display:flex;align-items:center;gap:7px;color:var(--smart-muted);font:9px var(--font-mono);letter-spacing:.08em}.status-dot{width:6px;height:6px;border-radius:50%;background:#8bc8a7;box-shadow:0 0 8px currentColor}.status-dot--degraded{background:#d9b96d}.status-copy{color:var(--smart-primary-strong)}.status-detail{color:var(--smart-muted)}
</style>
