<template>
  <article class="analytics-panel quality-panel">
    <div class="panel-title"><div><p class="eyebrow">USAGE &amp; QUALITY / 用量与质量</p><h2>用量构成与调用质量</h2></div><span class="unit-label">{{ periodLabel }}</span></div>
    <div class="quality-grid">
      <section class="quality-block">
        <h3>Token 用量构成</h3>
        <div v-if="compositionTotal > 0" class="quality-bar" role="img" :aria-label="compositionLabel">
          <i :style="{ width: inputShare + '%', background: 'var(--smart-primary-strong)' }" />
          <i :style="{ width: outputShare + '%', background: 'var(--smart-success)' }" />
        </div>
        <p v-else class="quality-empty">{{ periodLabel }}暂无已上报用量。</p>
        <div class="quality-legend">
          <span><i class="dot" style="background: var(--smart-primary-strong)" />输入 <b>{{ fmt(inputTokens) }}</b><em v-if="inputShare">（{{ inputShare.toFixed(1) }}%）</em></span>
          <span><i class="dot" style="background: var(--smart-success)" />输出 <b>{{ fmt(outputTokens) }}</b><em v-if="outputShare">（{{ outputShare.toFixed(1) }}%）</em></span>
          <span><i class="dot" style="background: var(--smart-muted)" />用量未知 <b>{{ fmt(unknownUsageCalls) }}</b> 次</span>
        </div>
        <p class="source-note">仅统计服务商已上报的输入 / 输出；两者之和与已知总量的差为未知或待确认用量，不按零补齐。</p>
      </section>
      <section class="quality-block">
        <h3>调用质量</h3>
        <div v-if="calls > 0" class="quality-bar" role="img" :aria-label="qualityLabel">
          <i :style="{ width: successShare + '%', background: 'var(--smart-success)' }" />
          <i :style="{ width: failureShare + '%', background: 'var(--smart-danger)' }" />
          <i :style="{ width: pendingShare + '%', background: 'var(--smart-warning)' }" />
        </div>
        <p v-else class="quality-empty">{{ periodLabel }}暂无调用记录。</p>
        <div class="quality-legend">
          <span><i class="dot" style="background: var(--smart-success)" />成功 <b>{{ fmt(successes) }}</b></span>
          <span><i class="dot" style="background: var(--smart-danger)" />失败 <b>{{ fmt(failures) }}</b></span>
          <span><i class="dot" style="background: var(--smart-warning)" />待确认 <b>{{ fmt(pendingCalls) }}</b></span>
        </div>
        <p class="source-note">成功率 = 成功 /（成功 + 失败），待确认调用不计入分母，与月度口径一致；失败与待确认分别计数，不互相掩盖。</p>
      </section>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { formatMetric } from './modelAnalytics.js'

/* 用量统计 + 调用质量并排的双栏叙事（sniffly 的 dual-column 版式）。
    消费 periodAggregate() 的结果，本身不做数据加工；比例只在分母 > 0 时给出。 */
const props = defineProps({
  aggregate: { type: Object, default: () => ({}) },
  periodLabel: { type: String, default: '本月' }
})
const fmt = value => formatMetric(value)
const calls = computed(() => Number(props.aggregate.calls) || 0)
const successes = computed(() => Number(props.aggregate.successes) || 0)
const failures = computed(() => Number(props.aggregate.failures) || 0)
const pendingCalls = computed(() => Number(props.aggregate.pendingCalls) || 0)
const unknownUsageCalls = computed(() => Number(props.aggregate.unknownUsageCalls) || 0)
const inputTokens = computed(() => props.aggregate.inputTokens ?? null)
const outputTokens = computed(() => props.aggregate.outputTokens ?? null)
const compositionTotal = computed(() => (inputTokens.value ?? 0) + (outputTokens.value ?? 0))
const inputShare = computed(() => compositionTotal.value > 0 ? (inputTokens.value ?? 0) / compositionTotal.value * 100 : 0)
const outputShare = computed(() => compositionTotal.value > 0 ? (outputTokens.value ?? 0) / compositionTotal.value * 100 : 0)
const successShare = computed(() => calls.value > 0 ? successes.value / calls.value * 100 : 0)
const failureShare = computed(() => calls.value > 0 ? failures.value / calls.value * 100 : 0)
const pendingShare = computed(() => calls.value > 0 ? pendingCalls.value / calls.value * 100 : 0)
const compositionLabel = computed(() => `用量构成：输入 ${fmt(inputTokens.value)}，输出 ${fmt(outputTokens.value)}，用量未知 ${fmt(unknownUsageCalls.value)} 次`)
const qualityLabel = computed(() => `调用质量：成功 ${fmt(successes.value)}，失败 ${fmt(failures.value)}，待确认 ${fmt(pendingCalls.value)}`)
</script>

<style scoped>
.quality-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; }
.quality-block { min-width: 0; }
.quality-block h3 { margin: 0 0 16px; font-size: 13px; font-weight: 550; color: var(--smart-text); }
.quality-bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--smart-border); }
.quality-bar i { display: block; height: 100%; }
.quality-bar i:first-child { border-radius: 5px 0 0 5px; }
.quality-bar i:last-child { border-radius: 0 5px 5px 0; }
.quality-empty { margin: 0; padding: 18px 0; color: var(--smart-muted); font-size: 12px; }
.quality-legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 14px; font-size: 11px; color: var(--smart-muted); }
.quality-legend span { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.quality-legend b { color: var(--smart-text); font-weight: 550; font-variant-numeric: tabular-nums; }
.quality-legend em { font-style: normal; }
.dot { width: 8px; height: 8px; border-radius: 2px; flex: none; }
@media (max-width: 767px) { .quality-grid { grid-template-columns: minmax(0, 1fr); gap: 22px; } }
</style>
