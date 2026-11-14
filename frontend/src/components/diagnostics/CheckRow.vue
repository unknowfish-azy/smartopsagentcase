<template>
  <button
    class="hc-row"
    :class="[`hc-row--${statusVisual.cls}`, { 'hc-row--open': open, 'hc-row--stale': stale }]"
    type="button"
    :aria-expanded="open"
    :aria-controls="`hc-row-raw-${check.id}`"
    @click="open = !open"
  >
    <span class="hc-row-main">
      <span class="hc-st" :class="[`hc-st--${statusVisual.cls}`, `hc-st-${statusVisual.shape}`]" aria-hidden="true">
        {{ statusVisual.icon }}
      </span>
      <span class="hc-row-name">{{ check.label }}</span>
      <span class="hc-row-meta">
        <span class="hc-kind" :title="kind.tip">
          <svg v-if="kind.icon === 'probe'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M1 6h2.2l1.3-3 1.6 6 1.4-3H11"/>
          </svg>
          <svg v-else-if="kind.icon === 'shield'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M6 1.2 10 2.6v3.1c0 2.4-1.7 4.2-4 5.1-2.3-.9-4-2.7-4-5.1V2.6z"/>
          </svg>
          <svg v-else viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M2.5 1.5h5l2 2v7h-7z"/>
            <path d="M7.5 1.5v2h2"/>
          </svg>
          {{ kind.label }}
        </span>
        <span v-if="check.durationMs != null">{{ check.durationMs }}ms</span>
        <span class="hc-row-time">{{ timeText }}</span>
      </span>
    </span>
    <span class="hc-row-sum">{{ check.summary || '—' }}</span>
    <span class="hc-row-next">
      <span>下一步：{{ check.nextAction || '—' }}</span>
      <span v-if="showAction" class="hc-row-act" @click.stop="$emit('go-tool', check)">去处理 →</span>
    </span>
    <pre
      v-if="open"
      :id="`hc-row-raw-${check.id}`"
      class="hc-row-raw"
    >id={{ check.id }} · scope={{ check.scope }} · checkKind={{ check.checkKind }}
status={{ check.status }} · checkedAt={{ check.checkedAt ?? 'null' }} · durationMs={{ check.durationMs ?? 'null' }}</pre>
  </button>
</template>

<script setup>
import { computed, ref } from 'vue'
import { statusVisual as resolveStatusVisual, kindLabel } from './healthGroups.js'

const props = defineProps({
  check: { type: Object, required: true },
  stale: { type: Boolean, default: false }
})
const _emit = defineEmits(['go-tool'])

const open = ref(false)

const statusVisual = computed(() => resolveStatusVisual(props.check.status))
const kind = computed(() => kindLabel(props.check.checkKind))

const timeText = computed(() => {
  if (props.check.checkedAt == null) return '—'
  const t = typeof props.check.checkedAt === 'number'
    ? props.check.checkedAt
    : Date.parse(props.check.checkedAt)
  if (!Number.isFinite(t)) return '—'
  return new Date(t).toLocaleTimeString('zh-CN', { hour12: false })
})

// 设计规则：UNHEALTHY / UNCONFIGURED / NOT_CHECKED 给「去处理」入口
const showAction = computed(() =>
  ['UNHEALTHY', 'UNCONFIGURED', 'NOT_CHECKED'].includes(props.check.status)
)
</script>

<style scoped>
.hc-row {
  display: block;
  width: 100%;
  text-align: left;
  padding: 12px 16px;
  border: none;
  border-top: 1px solid var(--ds-hairline);
  color: var(--ds-color-text);
  background: transparent;
  cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-row:first-child { border-top: none; }
.hc-row:hover { background: color-mix(in srgb, var(--smart-text) 4%, transparent); }
.hc-row--stale { filter: saturate(.35); opacity: .85; }

.hc-row-main {
  display: flex; align-items: center; gap: 10px; min-width: 0;
}
.hc-row-name {
  font-size: 14px; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.hc-row-meta {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px;
  color: var(--ds-semantic-neutral); font-size: 11.5px;
  white-space: nowrap; font-variant-numeric: tabular-nums;
}
.hc-row-time { color: var(--ds-semantic-neutral); }

.hc-st {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; flex: 0 0 auto;
  border-radius: 50%;
  font: 700 10px/1 var(--ds-font-mono);
  box-sizing: border-box;
}
.hc-st.hc-st-unhealthy { background: var(--ds-semantic-danger); color: color-mix(in srgb, var(--smart-bg) 92%, var(--ds-semantic-danger)); }
.hc-st.hc-st-unconfigured { background: var(--ds-semantic-warning); color: color-mix(in srgb, var(--smart-bg) 92%, var(--ds-semantic-warning)); }
.hc-st.hc-st-healthy { background: var(--ds-semantic-success); color: color-mix(in srgb, var(--smart-bg) 92%, var(--ds-semantic-success)); }
.hc-st.hc-st-not_checked { background: transparent; border: 1.5px dashed var(--ds-semantic-neutral); color: var(--ds-semantic-neutral); }
.hc-st.hc-st-forbidden { background: transparent; border: 1.5px solid var(--ds-semantic-neutral); color: var(--ds-semantic-neutral); font-size: 9px; }

/* shape-specific overrides */
.hc-st-solid { /* nothing extra needed */ }
.hc-st-dashed { border-style: dashed; }
.hc-st-outline { border-style: solid; background: transparent; }

.hc-kind {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 7px; border-radius: var(--ds-radius-sm);
  border: 1px solid var(--ds-hairline);
  color: var(--ds-color-muted); font-size: 11px;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-kind:hover { border-color: var(--ds-color-border-strong); }
.hc-kind svg { width: 11px; height: 11px; flex-shrink: 0; }

.hc-row-sum {
  display: block;
  margin: 7px 0 0 28px;
  color: var(--ds-color-muted); font-size: 12.5px;
  line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.hc-row--open .hc-row-sum { -webkit-line-clamp: unset; display: block; }

.hc-row-next {
  display: flex; align-items: center; gap: 10px;
  margin: 7px 0 0 28px;
  font-size: 12px; color: var(--ds-semantic-neutral);
}
.hc-row-act {
  margin-left: auto;
  color: var(--ds-color-primary-strong);
  white-space: nowrap;
}
.hc-row-act:hover { text-decoration: underline; }

.hc-row-raw {
  margin: 9px 0 0 28px;
  padding: 9px 11px;
  border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--smart-bg) 28%, transparent);
  color: var(--ds-semantic-neutral);
  font: 11px/1.6 var(--ds-font-mono);
  white-space: pre-wrap;
  word-break: break-all;
}

/* ---- 移动端 ---- */
@media (max-width: 767px) {
  .hc-row { padding: 10px 14px; }
  .hc-row-sum, .hc-row-next, .hc-row-raw { margin-left: 0; }
  .hc-row-meta { flex-wrap: wrap; justify-content: flex-end; gap: 4px; }
  .hc-row-next { flex-wrap: wrap; }
  .hc-row-act { margin-left: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .hc-row { transition: none; }
}
</style>
