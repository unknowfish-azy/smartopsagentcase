<template>
  <article class="analytics-panel leaderboard-panel">
    <div class="panel-title"><div><p class="eyebrow">MODEL LEADERBOARD / 消耗榜</p><h2>模型消耗榜</h2></div><span class="unit-label">{{ unitLabel }}</span></div>
    <ol v-if="rows.length" class="leader-list">
      <li v-for="row in rows" :key="`${row.connectionId}-${row.modelName}`" class="leader-row">
        <span class="leader-rank" :data-rank="row.badge || 'plain'">{{ String(row.rank).padStart(2, '0') }}</span>
        <div class="leader-main">
          <b>{{ row.modelName }}</b>
          <small>{{ row.connection || `连接 #${row.connectionId}` }}</small>
          <div class="leader-bar"><i :style="{ width: barWidth(row) }" /></div>
        </div>
        <div class="leader-num">
          <strong>{{ fmt(row.knownTokens) }}</strong>
          <small v-if="row.share != null">占比 {{ (row.share * 100).toFixed(1) }}% · {{ fmt(row.calls) }} 次调用</small>
          <small v-else>用量未知 · {{ fmt(row.calls) }} 次调用</small>
        </div>
      </li>
    </ol>
    <p v-else class="empty-table">暂无模型调用数据</p>
    <p class="source-note">{{ note }}</p>
  </article>
</template>

<script setup>
import { formatMetric } from './modelAnalytics.js'

/* 模型消耗榜（tokscale 的等宽表格 + 徽章观感，搬成 Web 卡片；codeburn 的按工具分布）。
   只消费 modelLeaderboard() 的纯结果：排名、占比、徽章语义都在那里算定，这里不做二次逻辑。 */
defineProps({
  rows: { type: Array, default: () => [] },
  unitLabel: { type: String, default: '' },
  note: { type: String, default: '' }
})
const fmt = value => formatMetric(value)
const barWidth = row => row.share == null ? '0%' : `${Math.max(row.share * 100, 1.5).toFixed(1)}%`
</script>

<style scoped>
.leader-list { list-style: none; margin: 0; padding: 0; }
.leader-row { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--smart-border); }
.leader-row:last-child { border-bottom: 0; }
.leader-rank { font: 11px/1 var(--font-mono); letter-spacing: .06em; color: var(--smart-muted); padding: 5px 0; text-align: center; border: 1px solid transparent; border-radius: 5px; }
.leader-rank[data-rank=gold] { color: var(--smart-primary-strong); border-color: currentColor; font-weight: 600; }
.leader-rank[data-rank=silver], .leader-rank[data-rank=bronze] { color: var(--smart-text); border-color: var(--smart-border); }
.leader-main { min-width: 0; }
.leader-main b { display: block; font-size: 13px; font-weight: 500; overflow-wrap: anywhere; }
.leader-main small { display: block; margin-top: 4px; font-size: 11px; color: var(--smart-muted); }
.leader-bar { height: 4px; margin-top: 9px; border-radius: 2px; background: var(--smart-border); overflow: hidden; }
.leader-bar i { display: block; height: 100%; border-radius: inherit; background: var(--smart-primary-strong); }
.leader-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.leader-num strong { display: block; font-size: 14px; font-weight: 550; }
.leader-num small { display: block; margin-top: 5px; font-size: 10px; color: var(--smart-muted); }
.empty-table { text-align: center; color: var(--smart-muted); padding: 30px; font-size: 12px; }
@media (max-width: 767px) {
  .leader-row { grid-template-columns: 30px minmax(0, 1fr); gap: 10px; }
  .leader-num { grid-column: 2; text-align: left; }
}
</style>
