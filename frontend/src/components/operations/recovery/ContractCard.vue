<template>
  <section class="recovery-card contract-card" aria-label="恢复契约卡">
    <header class="card-head">
      <div>
        <p class="eyebrow">RECOVERY CONTRACT</p>
        <h2>契约卡</h2>
      </div>
      <span class="chip" :class="`tone-${receiptState.tone}`">{{ receiptState.label }}</span>
    </header>

    <dl class="meta-grid">
      <div v-for="item in meta" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd :class="{ mono: item.mono }">{{ item.value }}</dd>
      </div>
    </dl>

    <section class="sub-block">
      <h3>四轴状态（互不替代）</h3>
      <ul class="axis-list">
        <li v-for="axis in axes" :key="axis.key">
          <span class="axis-title">{{ axis.title }}</span>
          <span class="axis-value" :class="`tone-${axis.tone}`">{{ axis.label }}</span>
          <p class="axis-note">{{ axis.note }}</p>
        </li>
      </ul>
    </section>

    <section class="sub-block">
      <h3>回执</h3>
      <dl class="kv">
        <div>
          <dt>回执编号</dt>
          <dd class="mono">{{ receipt?.id ?? '未提供回执' }}</dd>
        </div>
        <div>
          <dt>回执状态</dt>
          <dd>{{ receiptState.label }}（{{ receipt?.receipt_state ?? '未提供' }}）</dd>
        </div>
        <div>
          <dt>签发时间</dt>
          <dd>{{ receiptTime.issuedAt }}</dd>
        </div>
        <div>
          <dt>有效期至</dt>
          <dd>{{ receiptTime.validUntil }}</dd>
        </div>
        <div>
          <dt>失效事件</dt>
          <dd>{{ receipt?.invalidation_event_ids?.length ?? 0 }} 条</dd>
        </div>
      </dl>
      <p class="muted">{{ receiptState.note }}</p>
    </section>

    <section class="sub-block">
      <h3>证据组与采样窗口</h3>
      <p class="muted">登记来源组：<span v-for="group in sourceGroups" :key="group" class="tag mono">{{ group }}</span></p>
      <p class="muted">受信采集器：<span v-for="collector in collectors" :key="collector" class="tag mono">{{ collector }}</span></p>
      <dl class="window-grid">
        <div v-for="item in windowItems" :key="item.label">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
      <p class="muted">契约预算：{{ budgetText }}</p>
    </section>

    <footer class="card-foot">
      passed 只作为纠察轴字段展示，不进入恢复徽标；动作、传输与审批结论都不能替代恢复判定。数据来源：{{ sourceLabel }}。
    </footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { axisRows, receiptStateView, receiptTimeView, sourceView, windowSummary } from './recoveryCards.js'

const props = defineProps({
  contract: { type: Object, default: null },
  claim: { type: Object, default: null },
  receipt: { type: Object, default: null },
  action: { type: String, default: 'NOT_PERFORMED' },
  inspectionPassed: { type: Boolean, default: null },
  authorization: { type: String, default: null },
  source: { type: String, default: 'fixture' }
})

const contract = computed(() => props.contract ?? {})
const target = computed(() => contract.value.target ?? {})
const receiptState = computed(() => receiptStateView(props.receipt?.receipt_state))
const receiptTime = computed(() => receiptTimeView(props.receipt))
const sourceLabel = computed(() => sourceView(props.source))

const expiresText = computed(() => {
  const value = contract.value.expires_after
  if (!Number.isFinite(value)) return '未提供'
  return `${Math.round(value / 60000)} 分钟（${value} 毫秒）`
})

const meta = computed(() => [
  { label: '目标', value: target.value.target_id ?? '未提供', mono: true },
  { label: '目标类型', value: target.value.target_kind ?? '未提供' },
  { label: '只读探针入口', value: target.value.endpoint ?? '未提供', mono: true },
  { label: '可见范围', value: contract.value.scope ?? props.claim?.scope ?? '未提供' },
  { label: '契约 ID / 版本', value: `${contract.value.id ?? '未提供'} · v${contract.value.version ?? '—'}`, mono: true },
  { label: '期望目标版本', value: contract.value.expected_revision ?? '未提供' },
  { label: '模板', value: `${contract.value.template_id ?? '未提供'} · v${contract.value.template_version ?? '—'}` },
  { label: '契约有效期', value: expiresText.value }
])

const axes = computed(() => axisRows({
  action: props.action,
  inspectionPassed: props.inspectionPassed,
  verdict: props.receipt?.verdict,
  authorization: props.authorization
}))

const sourceGroups = computed(() => contract.value.source_groups ?? [])
const collectors = computed(() => [...new Set((contract.value.obligations ?? []).flatMap(item => item.collector_ids ?? []))])
const windowItems = computed(() => windowSummary(contract.value.window).items)
const budgetText = computed(() => {
  const budgets = contract.value.budgets
  if (!budgets) return '未提供'
  return `探针 ${budgets.max_probe_calls} 次，单探针 ${budgets.per_probe_timeout_ms} 毫秒，运行截止 ${budgets.run_deadline_ms} 毫秒，证据时效 ${budgets.evidence_ttl_ms} 毫秒，回执有效期 ${budgets.receipt_ttl_ms} 毫秒`
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
.meta-grid > div {
  min-width: 0;
  padding: 9px 11px;
  background: var(--smart-bg);
}
dt { color: var(--smart-muted); font-size: 10px; }
dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.mono { font-family: var(--font-mono); font-size: 11px; }
.sub-block { padding-top: 12px; border-top: 1px solid var(--smart-border); }
.axis-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.axis-list li {
  display: grid;
  align-content: start;
  gap: 4px;
  padding: 10px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  background: var(--smart-bg);
}
.axis-title { color: var(--smart-muted); font-size: 10px; letter-spacing: .08em; }
.axis-value { font-weight: 650; overflow-wrap: anywhere; }
.axis-note { margin: 0; color: var(--smart-muted); font-size: 10px; line-height: 1.5; }
.kv {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 16px;
  margin: 0 0 8px;
}
.kv > div { min-width: 0; }
.window-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 0;
}
.window-grid > div {
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  background: var(--smart-bg);
}
.tag {
  display: inline-block;
  margin: 0 6px 4px 0;
  padding: 1px 7px;
  border: 1px solid var(--smart-border);
  border-radius: 999px;
  color: var(--smart-text);
  font-size: 10px;
}
.muted { margin: 4px 0 0; color: var(--smart-muted); }
.card-foot {
  padding-top: 10px;
  border-top: 1px solid var(--smart-border);
  color: var(--smart-muted);
  font-size: 10px;
}
@media (max-width: 1180px) {
  .meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .axis-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .window-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 520px) {
  .recovery-card { padding: 14px; }
  .card-head { flex-direction: column; }
  .meta-grid, .axis-list, .kv, .window-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
