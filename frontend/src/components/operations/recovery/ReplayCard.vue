<template>
  <section class="recovery-card replay-card" aria-label="决策回放卡">
    <header class="card-head">
      <div>
        <p class="eyebrow">DECISION REPLAY</p>
        <h2>回放卡</h2>
      </div>
      <span class="chip" :class="`tone-${state.tone}`">{{ state.label }}</span>
    </header>

    <div v-if="state.prominent" class="prominent" role="alert">
      <strong>{{ state.label }}</strong>
      <span>{{ state.notice }}</span>
    </div>
    <p v-else class="lede">{{ state.notice }}</p>

    <dl class="meta-grid">
      <div v-for="item in meta" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd :class="{ mono: item.mono }">{{ item.value }}</dd>
      </div>
    </dl>

    <section class="sub-block">
      <h3>差异码</h3>
      <p v-if="!diff.codes.length" class="muted">未记录差异码。</p>
      <ul v-else class="code-list">
        <li v-for="code in diff.codes" :key="code.code">
          <span>{{ code.label }}</span>
          <code>{{ code.code }}</code>
        </li>
      </ul>
    </section>

    <section class="sub-block">
      <h3>逐义务差异</h3>
      <div class="diff-head" aria-hidden="true">
        <span>义务</span><span>原包值</span><span>回放值</span><span>变化</span>
      </div>
      <div v-for="row in diff.rows" :key="row.obligationId" class="diff-row">
        <code>{{ row.obligationId }}</code>
        <span :class="`tone-${row.baselineTone}`">{{ row.baselineLabel }}</span>
        <span :class="`tone-${row.replayTone}`">{{ row.replayLabel }}</span>
        <span :class="{ changed: row.changed }">{{ row.changeLabel }}</span>
      </div>
      <p v-if="!diff.rows.length" class="muted">没有可比较的义务结果。</p>
    </section>

    <section class="sub-block">
      <h3>缺失探针</h3>
      <p v-if="!diff.missingProbes.length" class="muted">没有缺失的录制探针。</p>
      <ul v-else class="plain-list">
        <li v-for="probe in diff.missingProbes" :key="probe.id">
          <code>{{ probe.id }}</code>：{{ probe.label }}
        </li>
      </ul>
    </section>

    <footer class="card-foot">
      回放不访问网络、不重新调用模型、不使用当前运行时钟覆盖录制时间；缺项只披露，不补造结果。数据来源：{{ sourceLabel }}。
    </footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { formatUtc, replayDiffView, replayStateView, sourceView } from './recoveryCards.js'

const props = defineProps({
  bundle: { type: Object, default: null },
  replay: { type: Object, default: null },
  baselineResults: { type: Array, default: () => [] },
  source: { type: String, default: 'replay' }
})

const state = computed(() => replayStateView(props.replay?.replay_state))
const sourceLabel = computed(() => sourceView(props.source))
const diff = computed(() => replayDiffView({
  baselineResults: props.baselineResults,
  replayResults: props.replay?.obligation_results ?? [],
  replayState: props.replay?.replay_state ?? null,
  diffCodes: props.replay?.diff_codes ?? [],
  missingProbeIds: props.replay?.missing_probe_ids ?? []
}))

const meta = computed(() => {
  const bundle = props.bundle ?? {}
  const clock = bundle.decision_clock ?? {}
  return [
    { label: '回放包 ID', value: bundle.bundle_id ?? '未提供', mono: true },
    { label: '回放状态码', value: props.replay?.replay_state ?? '未提供', mono: true },
    { label: '包格式', value: bundle.schema_version ?? '未提供', mono: true },
    { label: '策略版本', value: `${bundle.policy_version ?? '未提供'} → ${props.replay?.policy_version ?? '未提供'}`, mono: true },
    { label: '判定时钟', value: clock.mode ? `${clock.mode} · ${formatUtc(clock.decision_time)}` : '未提供' },
    { label: '包性质', value: bundle.is_historical_fact === false ? '变形实验包（不是原历史事实）' : bundle.is_historical_fact === true ? '原历史事实' : '未提供' },
    { label: '父包', value: bundle.parent_bundle_id ?? '无（原始包）', mono: true },
    { label: '显式观测顺序', value: `${bundle.observation_order?.length ?? 0} 条` }
  ]
})
</script>

<style scoped>
.recovery-card {
  display: grid;
  gap: 14px;
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
  color: var(--smart-text);
  font: 12px/1.6 var(--font-cn);
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
h2 { margin: 0; font-size: 16px; font-weight: 560; }
h3 { margin: 0 0 8px; font-size: 12px; font-weight: 650; }
.chip {
  flex: none;
  padding: 3px 9px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}
.tone-success { color: var(--smart-success); }
.tone-danger { color: var(--smart-danger); }
.tone-warning { color: var(--smart-warning); }
.tone-unknown { color: var(--smart-muted); }
.tone-neutral { color: var(--smart-primary-strong); }
.prominent {
  display: grid;
  gap: 5px;
  padding: 12px 14px;
  border: 1px solid var(--smart-danger);
  border-left-width: 3px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--smart-danger) 8%, var(--smart-surface));
}
.prominent strong { color: var(--smart-danger); font-size: 13px; }
.prominent span { color: var(--smart-text); }
.lede { margin: 0; color: var(--smart-muted); }
.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--smart-border);
}
.meta-grid > div { min-width: 0; padding: 9px 11px; background: var(--smart-bg); }
dt { color: var(--smart-muted); font-size: 10px; }
dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.mono { font-family: var(--font-mono); font-size: 11px; }
.sub-block { padding-top: 12px; border-top: 1px solid var(--smart-border); }
.code-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.code-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 10px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  background: var(--smart-bg);
}
.code-list code { color: var(--smart-muted); font: 10px var(--font-mono); }
.diff-head, .diff-row {
  display: grid;
  grid-template-columns: minmax(140px, 1.2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid var(--smart-border);
}
.diff-head { color: var(--smart-muted); font-size: 10px; }
.diff-row { overflow-wrap: anywhere; }
.diff-row code { font: 11px var(--font-mono); }
.changed { color: var(--smart-danger); font-weight: 650; }
.plain-list { margin: 0; padding-left: 18px; color: var(--smart-muted); }
.plain-list code { font: 11px var(--font-mono); }
.muted { margin: 4px 0 0; color: var(--smart-muted); }
.card-foot {
  padding-top: 10px;
  border-top: 1px solid var(--smart-border);
  color: var(--smart-muted);
  font-size: 10px;
}
@media (max-width: 1180px) {
  .meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .recovery-card { padding: 14px; }
  .card-head { flex-direction: column; }
  .meta-grid { grid-template-columns: minmax(0, 1fr); }
  .diff-head, .diff-row { grid-template-columns: minmax(0, 1fr); }
}
</style>
