<template>
  <div class="aet-host">
    <ol v-if="timeline.length" class="aet-list">
      <li
        v-for="step in timeline"
        :key="step.kind"
        class="aet-step"
        :class="{ 'aet-step--active': step.kind === active, 'aet-step--done': step.done }"
      >
        <i class="aet-dot" :class="{ 'aet-dot--active': step.kind === active }"></i>
        <span class="aet-body">
          <b>{{ step.label }}</b>
          <small class="aet-at">{{ formatTimelineAt(step.at) }}</small>
          <small class="aet-detail">{{ step.detail }}</small>
        </span>
      </li>
    </ol>
    <p v-else class="aet-empty">—</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { buildAlertTimeline, formatTimelineAt, activeKind } from '../../domain/sentinel/alertTimeline.js'

const props = defineProps({
  alert: { type: Object, default: null }
})

const timeline = computed(() => buildAlertTimeline(props.alert))
const active = computed(() => activeKind(timeline.value))
</script>

<style scoped>
.aet-host {
  padding: 14px 16px;
}

.aet-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.aet-step {
  position: relative;
  display: flex;
  gap: 10px;
  padding-left: 18px;
  padding-bottom: 6px;
  border-left: 2px solid var(--ds-hairline, rgba(159, 190, 207, .18));
}

.aet-step:last-child { border-left-color: transparent; }

.aet-dot {
  position: absolute;
  left: -5px;
  top: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ds-color-muted, #92A6B5);
  opacity: .5;
}

.aet-step--done .aet-dot {
  background: var(--ds-semantic-success, var(--smart-success, #3FB68B));
  opacity: 1;
}

.aet-step--active .aet-dot {
  background: var(--ds-semantic-warning, #D29922);
  opacity: 1;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ds-semantic-warning, #D29922) 18%, transparent);
}

.aet-body {
  display: grid;
  grid-template-columns: 72px 130px minmax(0, 1fr);
  gap: 4px 12px;
  align-items: baseline;
  line-height: 1.5;
}

.aet-body b {
  font-size: 12px;
  color: var(--ds-color-text, var(--smart-text, #E8F2F7));
}

.aet-step--active .aet-body b { color: var(--ds-semantic-warning, #D29922); }

.aet-at,
.aet-detail {
  font: 10.5px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  color: var(--ds-color-muted, var(--smart-muted, #92A6B5));
}

.aet-detail { letter-spacing: .02em; }

.aet-empty {
  margin: 0;
  color: var(--ds-color-muted, var(--smart-muted, #92A6B5));
  font: 11px Consolas, 'Cascadia Mono', ui-monospace, monospace;
  text-align: center;
}

@media (max-width: 760px) {
  .aet-body { grid-template-columns: 72px minmax(0, 1fr); }
  .aet-detail { grid-column: 1 / -1; }
}

@media (prefers-reduced-motion: reduce) {
  .aet-host * { transition: none !important; animation: none !important; }
}
</style>
