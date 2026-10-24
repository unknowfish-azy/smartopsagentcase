<template>
  <span
    class="nav-health-badge"
    :class="`nav-health-badge--${level}`"
    role="img"
    :aria-label="title"
    :title="title"
  >
    <span class="nav-health-badge__dot" aria-hidden="true"></span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { NAV_HEALTH_LABELS } from '../../navigation/navigationHealth.js'

const props = defineProps({
  // ready / degraded / alert / offline，取值见 navigationHealth.js 的 NAV_HEALTH_LEVELS
  level: { type: String, default: 'ready', validator: value => Object.hasOwn(NAV_HEALTH_LABELS, value) },
  // 宿主名称（如「哨兵与自动化 / SENTINEL」），用于拼装读屏文案
  label: { type: String, default: '' }
})

const title = computed(() => (props.label ? `${props.label} · ${NAV_HEALTH_LABELS[props.level]}` : NAV_HEALTH_LABELS[props.level]))
</script>

<style scoped>
.nav-health-badge { display: inline-flex; align-items: center; flex-shrink: 0; }
.nav-health-badge__dot { width: 7px; height: 7px; border-radius: 50%; background: var(--smart-muted); color: var(--smart-muted); box-shadow: 0 0 8px currentColor; }
.nav-health-badge--ready .nav-health-badge__dot { background: var(--smart-success); color: var(--smart-success); }
.nav-health-badge--degraded .nav-health-badge__dot { background: var(--smart-warning); color: var(--smart-warning); }
.nav-health-badge--offline .nav-health-badge__dot { background: var(--smart-muted); color: var(--smart-muted); }
.nav-health-badge--alert .nav-health-badge__dot { background: var(--smart-danger); color: var(--smart-danger); animation: nav-health-pulse 1.6s ease-in-out infinite; }
@keyframes nav-health-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
@media (prefers-reduced-motion: reduce) { .nav-health-badge__dot { animation: none; } }
</style>
