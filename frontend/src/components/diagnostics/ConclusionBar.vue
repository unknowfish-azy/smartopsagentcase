<template>
  <section
    class="hc-verdict"
    :class="{ 'is-good': allPass, 'is-stale': stale, 'is-empty': !totalChecks }"
    role="status"
    aria-live="polite"
    :aria-label="verdictText"
  >
    <div class="hc-v-main">
      <span class="hc-v-dot" :style="{ background: dotColor }" aria-hidden="true"></span>
      <span class="hc-v-title">{{ verdictText }}</span>
    </div>

    <div class="hc-v-counts">
      <button
        v-for="c in countItems"
        :key="c.key"
        class="hc-v-count"
        :class="{ zero: counts[c.key] === 0 }"
        type="button"
        :title="`跳到「${c.label}」`"
        @click="$emit('jump-group', c.key)"
      >
        <i :style="{ background: c.color }" aria-hidden="true"></i>
        <b>{{ counts[c.key] }}</b> {{ c.label }}
      </button>
    </div>

    <span class="hc-v-grow" aria-hidden="true"></span>

    <div class="hc-fresh" :title="freshTooltip">
      <span
        class="hc-ring"
        :style="{ '--deg': ringDeg + 'deg', background: ringStyle }"
        aria-hidden="true"
      >
        <span class="hc-ring-text">{{ ringText }}</span>
      </span>
      <span class="hc-fresh-text">{{ freshText }}</span>
    </div>

    <button
      class="hc-btn hc-btn-primary"
      type="button"
      :disabled="loading"
      @click="$emit('recheck')"
    >
      {{ loading ? `检查中… ${loadingProgress || ''}` : '重新检查' }}
    </button>
  </section>

  <div v-if="stale" class="hc-stale-bar" role="alert">
    <b>结果可能已过期</b>
    <span>正在显示 {{ checkedAtText }} 的快照，请重新检查确认当前状态。</span>
    <span class="hc-v-grow" aria-hidden="true"></span>
    <button class="hc-btn hc-btn-small" type="button" @click="$emit('recheck')">重新检查</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { verdictText as verdictTextOf, verdictLevel, freshInfo } from './conclusionState.js'

const props = defineProps({
  counts: { type: Object, default: () => ({ action: 0, config: 0, unknown: 0, pass: 0, forbidden: 0 }) },
  checkedAt: { type: [Number, String, Date], default: null },
  now: { type: Number, default: () => Date.now() },
  stale: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  loadingProgress: { type: String, default: '' }
})

defineEmits(['recheck', 'jump-group'])

const totalChecks = computed(() =>
  props.counts.action + props.counts.config + props.counts.unknown + props.counts.pass
)

const allPass = computed(() => verdictLevel(props.counts) === 'pass')

const verdictText = computed(() => verdictTextOf(props.counts))

const countItems = [
  { key: 'action', label: '需要处理', color: 'var(--ds-semantic-danger)' },
  { key: 'config', label: '需要配置', color: 'var(--ds-semantic-warning)' },
  { key: 'unknown', label: '缺证据',   color: 'var(--ds-semantic-neutral)' },
  { key: 'pass', label: '通过',       color: 'var(--ds-semantic-success)' }
]

const dotColor = computed(() => {
  if (props.counts.action) return 'var(--ds-semantic-danger)'
  if (props.counts.config) return 'var(--ds-semantic-warning)'
  if (props.counts.unknown) return 'var(--ds-semantic-neutral)'
  if (totalChecks.value) return 'var(--ds-semantic-success)'
  return 'var(--ds-semantic-neutral)'
})

const checkedAtMs = computed(() => {
  if (props.checkedAt == null) return 0
  return typeof props.checkedAt === 'number'
    ? props.checkedAt
    : Date.parse(props.checkedAt) || 0
})

const fmtTime = iso => iso ? new Date(iso).toLocaleTimeString('zh-CN', { hour12: false }) : null
const checkedAtText = computed(() => fmtTime(checkedAtMs.value) || '—')

const _fresh = computed(() => freshInfo({ checkedAt: props.checkedAt, now: props.now, stale: props.stale }))

const ringDeg = computed(() => _fresh.value.ringDeg)
const ringStyle = computed(() => {
  const token = _fresh.value.ringColorToken.startsWith('--')
    ? `var(${_fresh.value.ringColorToken})`
    : _fresh.value.ringColorToken
  return `conic-gradient(${token} ${_fresh.value.ringDeg}deg, rgba(255,255,255,.08) 0)`
})
const ringText = computed(() => _fresh.value.ringText)
const freshText = computed(() => _fresh.value.label)
const freshTooltip = computed(() => _fresh.value.tooltip)
</script>

<style scoped>
.hc-verdict {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 72px;
  padding: 12px 16px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-surface-raised);
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-verdict.is-good { border-color: color-mix(in srgb, var(--ds-semantic-success) 32%, transparent); }
.hc-verdict.is-stale { border-color: color-mix(in srgb, var(--ds-semantic-warning) 32%, transparent); }

.hc-v-main { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.hc-v-dot {
  width: 10px; height: 10px; border-radius: 50%;
  flex: 0 0 auto; align-self: center;
}
.hc-v-title {
  font-size: var(--ds-type-h3-size);
  font-weight: var(--ds-type-h3-weight);
  white-space: nowrap;
}
.hc-verdict.is-empty .hc-v-title { color: var(--ds-semantic-neutral); }

.hc-v-counts { display: flex; align-items: center; gap: 2px; margin-left: 2px; flex-wrap: wrap; }
.hc-v-count {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  border-radius: var(--ds-radius-md);
  font-size: 12.5px;
  color: var(--ds-color-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-v-count b { font-weight: 500; color: var(--ds-color-text); }
.hc-v-count.zero { opacity: .55; }
.hc-v-count:hover { background: rgba(232, 242, 247, .05); }
.hc-v-count i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }

.hc-v-grow { flex: 1; }

.hc-fresh {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--ds-color-muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.hc-ring {
  width: 34px; height: 34px; border-radius: 50%;
  flex: 0 0 auto;
  display: grid; place-items: center;
}
.hc-ring-text {
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--ds-surface-raised);
  display: grid; place-items: center;
  font: 10px/1 var(--ds-font-mono);
  color: var(--ds-color-muted);
}

.hc-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  height: 40px; padding: 0 14px; flex: 0 0 auto; white-space: nowrap;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  font-size: 13px; color: var(--ds-color-text);
  background: var(--ds-surface-base);
  cursor: pointer;
  transition: background var(--ds-duration-micro) var(--ds-ease-out),
              border-color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-btn:hover:not(:disabled) { background: rgba(232, 242, 247, .05); border-color: var(--ds-color-border-strong); }
.hc-btn.primary {
  background: color-mix(in srgb, var(--ds-color-primary-strong) 10%, transparent);
  border-color: color-mix(in srgb, var(--ds-color-primary-strong) 45%, transparent);
  color: #cdefff;
}
.hc-btn.primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--ds-color-primary-strong) 16%, transparent);
}
.hc-btn.small { height: 28px; padding: 0 10px; font-size: 12px; }
.hc-btn[disabled] { opacity: .5; cursor: not-allowed; }

.hc-stale-bar {
  display: flex; align-items: center; gap: 10px;
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: var(--ds-radius-md);
  border: 1px solid color-mix(in srgb, var(--ds-semantic-warning) 34%, transparent);
  background: color-mix(in srgb, var(--ds-semantic-warning) 8%, transparent);
  color: var(--ds-color-muted);
  font-size: 12.5px;
}
.hc-stale-bar b { color: var(--ds-semantic-warning); font-weight: 500; }

/* ---- 响应式 ---- */
@media (max-width: 1023px) {
  .hc-v-counts { gap: 0; }
  .hc-v-count { padding: 0 8px; font-size: 12px; }
}
@media (max-width: 879px) {
  .hc-verdict { flex-wrap: wrap; gap: 10px; min-height: auto; padding: 10px 14px; }
  .hc-verdict .hc-v-grow { display: none; }
  .hc-v-main { order: 1; flex: 1 1 auto; }
  .hc-btn { order: 2; }
  .hc-v-counts { order: 3; width: 100%; flex-wrap: wrap; margin-left: 0; }
  .hc-fresh { order: 4; }
}
@media (max-width: 767px) {
  .hc-fresh-text { display: none; }
}
</style>
