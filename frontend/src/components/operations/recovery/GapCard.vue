<template>
  <section class="recovery-card gap-card" aria-label="证据缺口卡">
    <header class="card-head">
      <div>
        <p class="eyebrow">EVIDENCE GAP</p>
        <h2>缺口卡</h2>
      </div>
      <span class="chip" :class="`tone-${verdictTone}`">{{ verdictLabel }}</span>
    </header>
    <p class="lede">
      {{ summary.headline }}
      <template v-if="!summary.empty">（{{ summary.satisfied }} / {{ summary.total }} 项义务已支持）</template>
    </p>

    <div v-if="summary.empty" class="empty-state" role="status">
      <strong>{{ summary.headline }}</strong>
      <span>{{ summary.note }}</span>
    </div>

    <template v-else>
      <ul class="obligation-list">
        <li v-for="row in summary.rows" :key="row.obligationId">
          <div class="obligation-head">
            <code>{{ row.obligationId }}</code>
            <span class="chip" :class="`tone-${row.tone}`">{{ row.valueLabel }}</span>
          </div>
          <p class="predicate">{{ row.predicateId }} · v{{ row.predicateVersion }} · {{ row.requiredLabel }}</p>
          <p v-if="row.reasonLabels.length" class="reasons">
            原因码：
            <span v-for="reason in row.reasonLabels" :key="reason.code" class="reason" :title="reason.note">{{ reason.label }}（{{ reason.code }}）</span>
          </p>
          <p v-else-if="row.value !== 'TRUE'" class="reasons">原因码：未提供</p>
          <p v-if="row.rejected.length" class="reasons">
            被拒证据：
            <span v-for="item in row.rejected" :key="item.evidence_id">{{ item.evidence_id }}（{{ reasonCodeLabel(item.reason_code) }}）</span>
          </p>
        </li>
      </ul>

      <section class="sub-block">
        <h3>缺失证据</h3>
        <p v-if="!summary.missingEvidence.length" class="muted">当前没有证据不足的义务，但仍须由核验服务确认窗口是否满足。</p>
        <ul v-else class="plain-list">
          <li v-for="row in summary.missingEvidence" :key="row.obligationId">
            {{ row.obligationId }}：{{ row.valueLabel }}
            <template v-if="row.reasonLabels.length">（{{ row.reasonLabels.map(reason => reason.label).join('、') }}）</template>
          </li>
        </ul>
      </section>

      <section class="sub-block">
        <h3>下一探针建议</h3>
        <p class="probe" :class="`tone-${summary.nextProbe.tone}`">{{ summary.nextProbe.label }}</p>
        <p class="muted">{{ summary.nextProbe.detail }}</p>
      </section>

      <section class="sub-block">
        <h3>预算</h3>
        <p class="muted">{{ summary.budget.text }}</p>
      </section>
    </template>

    <footer class="card-foot">仅展示服务端状态：HTTP 200、passed、审批通过都不能替代恢复判定。数据来源：{{ sourceLabel }}。</footer>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { gapSummary, reasonCodeLabel, sourceView, verdictText, verdictView } from './recoveryCards.js'

const props = defineProps({
  obligations: { type: Array, default: () => [] },
  obligationResults: { type: Array, default: () => [] },
  probeDecision: { type: Object, default: null },
  budget: { type: Object, default: null },
  verdict: { type: String, default: null },
  source: { type: String, default: 'fixture' }
})

const summary = computed(() => gapSummary({
  obligations: props.obligations,
  obligationResults: props.obligationResults,
  probeDecision: props.probeDecision,
  budget: props.budget
}))
const sourceLabel = computed(() => sourceView(props.source))
const verdictLabel = computed(() => verdictView(props.verdict)?.text ?? verdictText(props.verdict))
const verdictTone = computed(() => verdictView(props.verdict)?.tone ?? 'unknown')
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
h3 { margin: 0 0 6px; font-size: 12px; font-weight: 650; color: var(--smart-text); }
.lede { margin: 0; color: var(--smart-muted); }
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
.empty-state {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px dashed var(--smart-danger);
  border-radius: 10px;
  background: color-mix(in srgb, var(--smart-danger) 7%, var(--smart-surface));
}
.empty-state strong { color: var(--smart-danger); }
.empty-state span { color: var(--smart-muted); }
.obligation-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.obligation-list li {
  display: grid;
  gap: 4px;
  padding: 11px 12px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  background: var(--smart-bg);
  overflow-wrap: anywhere;
}
.obligation-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.obligation-head code { font: 11px var(--font-mono); }
.predicate { margin: 0; color: var(--smart-muted); font-size: 11px; }
.reasons { margin: 2px 0 0; color: var(--smart-muted); font-size: 11px; }
.reason { display: inline-block; margin-right: 8px; }
.sub-block {
  padding-top: 12px;
  border-top: 1px solid var(--smart-border);
}
.plain-list { margin: 0; padding-left: 18px; color: var(--smart-muted); }
.plain-list li { overflow-wrap: anywhere; }
.probe { margin: 0; font-weight: 650; }
.muted { margin: 4px 0 0; color: var(--smart-muted); }
.card-foot {
  padding-top: 10px;
  border-top: 1px solid var(--smart-border);
  color: var(--smart-muted);
  font-size: 10px;
}
@media (max-width: 520px) {
  .recovery-card { padding: 14px; }
  .card-head { flex-direction: column; }
}
</style>
