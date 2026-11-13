<template>
  <section class="bento-dashboard" aria-label="工作仪表盘">
    <!-- AI 情境简报层（T21，§3.5 差异化招牌） -->
    <header class="bento-briefing" v-if="briefing">
      <div class="briefing-avatar" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 2a5 5 0 0 0-5 5v4H5a1 1 0 0 0 0 2h2v2a5 5 0 0 0 10 0v-2h2a1 1 0 1 0 0-2h-2V7a5 5 0 0 0-5-5Z"/><circle cx="10" cy="7" r=".8" fill="currentColor"/><circle cx="14" cy="7" r=".8" fill="currentColor"/></svg>
      </div>
      <div class="briefing-content">
        <span class="briefing-label">Agent 巡检简报 · {{ briefing.generatedAt }}</span>
        <p class="briefing-text">{{ briefing.summary }}</p>
      </div>
    </header>

    <!-- KPI 带（4 张，12 栅格 = 3+3+3+3） -->
    <div class="bento-kpi">
      <article v-for="kpi in kpis" :key="kpi.key" class="kpi-card" :class="`kpi-card--${kpi.tone}`">
        <header class="kpi-head">
          <span class="kpi-label">{{ kpi.label }}</span>
          <span class="kpi-pill" v-if="kpi.pill" :class="`kpi-pill--${kpi.tone}`">{{ kpi.pill }}</span>
        </header>
        <strong class="kpi-value">{{ kpi.value }}</strong>
        <small class="kpi-sub">{{ kpi.sub }}</small>
      </article>
    </div>

    <!-- 态势 + 活动（左右 6/6） -->
    <div class="bento-main">
      <article class="bento-card bento-status">
        <header class="bento-card-head">
          <h3>系统态势</h3>
          <span class="bento-card-eyebrow">SYSTEM · STATUS</span>
        </header>
        <ul class="status-list">
          <li v-for="item in statuses" :key="item.key" class="status-row">
            <span class="status-dot" :class="`status-dot--${item.state}`" aria-hidden="true"></span>
            <span class="status-name">{{ item.name }}</span>
            <span class="status-value">{{ item.value }}</span>
          </li>
        </ul>
      </article>

      <article class="bento-card bento-activity">
        <header class="bento-card-head">
          <h3>近期活动</h3>
          <span class="bento-card-eyebrow">RECENT · ACTIVITY</span>
        </header>
        <ol class="activity-list">
          <li v-for="(item, idx) in activities" :key="idx" class="activity-row">
            <time class="activity-time">{{ item.time }}</time>
            <span class="activity-type" :class="`activity-type--${item.type}`">{{ item.typeLabel }}</span>
            <span class="activity-text">{{ item.text }}</span>
          </li>
        </ol>
      </article>
    </div>

    <!-- 知识 / Agent 双列（3/3 紧凑） -->
    <div class="bento-compact">
      <article class="bento-card bento-mini">
        <header class="bento-card-head">
          <h3>知识条目</h3>
        </header>
        <strong class="bento-mini-value">18</strong>
        <small class="bento-mini-sub">已入库 · 3 待完善</small>
      </article>
      <article class="bento-card bento-mini">
        <header class="bento-card-head">
          <h3>Agent 运行</h3>
        </header>
        <strong class="bento-mini-value">3</strong>
        <small class="bento-mini-sub">今日 · 全部成功</small>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

/* 所有数据用静态占位 + 令牌驱动样式；T21 接入时从 Agent store 替换 briefing 内容 */
const briefing = computed(() => ({
  generatedAt: '2 分钟前',
  summary: '自上次会话以来，Sentinel 发现 1 个磁盘使用率告警（/var 分区 89%），未触发高危动作。知识库新增 3 条。Agent 今日 3 次运行全部成功，无假成功。'
}))

const kpis = [
  { key: 'servers', label: '服务器', value: '4', sub: '2 在线 · 1 维护中', tone: 'neutral', pill: 'READY' },
  { key: 'alerts', label: '活跃告警', value: '1', sub: '磁盘使用率 89%', tone: 'warning', pill: 'ATTENTION' },
  { key: 'knowledge', label: '知识条目', value: '18', sub: 'BM25 + 向量双路', tone: 'neutral' },
  { key: 'agent', label: 'Agent 运行', value: '3', sub: '今日 · 全部成功', tone: 'success' }
]

const statuses = [
  { key: 'backend', name: '后端', state: 'healthy', value: ':8080 /actuator/health OK' },
  { key: 'ai', name: 'AI 服务', state: 'healthy', value: 'Ollama qwen3:1.7b 本地' },
  { key: 'knowledge', name: '知识服务', state: 'healthy', value: ':8002 ready' },
  { key: 'redis', name: 'Redis', state: 'healthy', value: ':6379 连接数 3' },
  { key: 'mysql', name: 'MySQL', state: 'healthy', value: ':3306 连接正常' },
  { key: 'disk', name: '磁盘告警', state: 'warning', value: '/var 分区 89%' }
]

const activities = [
  { time: '14:32', type: 'agent', typeLabel: 'Agent', text: 'Agent 巡检完成，判定 1 条磁盘告警' },
  { time: '14:18', type: 'chat', typeLabel: '对话', text: '询问 MySQL 连接数排查方案' },
  { time: '13:55', type: 'knowledge', typeLabel: '知识', text: '新增 Ubuntu 22.04 Nginx 安装条目' },
  { time: '13:40', type: 'run', typeLabel: '执行', text: '执行磁盘清理脚本，成功释放 2.1GB' },
  { time: '12:05', type: 'approval', typeLabel: '审批', text: '批准重启 Nginx（Agent 申请）' },
  { time: '11:22', type: 'chat', typeLabel: '对话', text: '附一张 502 截图，AI 给出重启建议' }
]
</script>

<style scoped>
.bento-dashboard {
  display: grid;
  gap: var(--ds-grid-gutter, 24px);
  padding: var(--ds-space-6, 24px);
  background: var(--ds-surface-base, var(--ds-color-canvas));
  min-height: calc(100dvh - 112px);
  grid-template-columns: repeat(12, 1fr);
  grid-auto-rows: minmax(var(--ds-row-min, 180px), auto);
}

/* AI 简报层（跨全宽） */
.bento-briefing {
  grid-column: 1 / -1;
  display: flex; gap: 14px; align-items: flex-start;
  padding: var(--ds-space-4, 16px) var(--ds-space-5, 20px);
  background: var(--ds-surface-overlay);
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
  border-radius: var(--ds-radius-md, 8px);
  box-shadow: var(--ds-elevation-1);
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out);
}
.bento-briefing:hover { border-color: color-mix(in srgb, var(--ds-color-primary, #2496ed) 40%, var(--ds-hairline, transparent)); }
.briefing-avatar {
  flex-shrink: 0; width: 32px; height: 32px; display: grid; place-content: center;
  color: var(--ds-color-primary, #2496ed);
  background: var(--ds-pill-info-bg, rgba(88,166,255,.14));
  border-radius: 8px;
}
.briefing-content { min-width: 0; }
.briefing-label {
  display: block; font: 10px var(--ds-font-mono, ui-monospace, monospace);
  color: var(--ds-color-muted, #92a6b5); letter-spacing: .1em;
}
.briefing-text {
  margin: var(--ds-space-1, 4px) 0 0; font-size: var(--ds-type-body-caption-size, 13px);
  line-height: var(--ds-line-height-base, 1.5); color: var(--ds-color-text, #e8f2f7);
}

/* KPI 带（每卡 3 栅格，4 卡 = 12） */
.bento-kpi { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--ds-grid-gutter, 24px); }
.kpi-card {
  grid-column: span 3;
  padding: var(--ds-space-5, 20px);
  background: var(--ds-surface-raised);
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
  border-radius: var(--ds-radius-md, 8px);
  box-shadow: var(--ds-elevation-1);
  transition: box-shadow var(--ds-duration-micro) var(--ds-ease-out), transform var(--ds-duration-micro) var(--ds-ease-out);
}
.kpi-card:hover { box-shadow: var(--ds-elevation-2); transform: translateY(-1px); }
.kpi-head { display: flex; justify-content: space-between; align-items: center; }
.kpi-label {
  font: var(--ds-type-overline-weight, 600) var(--ds-type-overline-size, 11px) var(--ds-font-cn);
  letter-spacing: .08em; color: var(--ds-color-muted, #92a6b5);
}
.kpi-value {
  display: block; margin-top: var(--ds-space-2, 8px);
  font-weight: var(--ds-type-display-weight, 300);
  font-size: var(--ds-type-display-size, 36px);
  font-variant-numeric: var(--ds-type-num, tabular-nums);
  color: var(--ds-color-text, #e8f2f7);
  line-height: 1;
}
.kpi-sub { display: block; margin-top: var(--ds-space-2, 8px); font-size: var(--ds-type-caption-size, 12px); color: var(--ds-color-muted, #92a6b5); }
.kpi-pill {
  font: 10px var(--ds-font-mono, monospace); letter-spacing: .1em; padding: 3px 8px;
  border-radius: var(--ds-radius-pill, 999px); background: var(--ds-pill-info-bg, rgba(88,166,255,.14));
}
.kpi-pill--warning { background: var(--ds-pill-warning-bg, rgba(210,153,34,.18)); color: var(--ds-semantic-warning, #d29922); }
.kpi-pill--success { background: var(--ds-pill-success-bg, rgba(63,185,80,.15)); color: var(--ds-semantic-success, #3fb950); }
.kpi-pill--neutral { background: var(--ds-pill-info-bg, rgba(88,166,255,.14)); color: var(--ds-color-primary, #2496ed); }

/* 主区（态势 + 活动 6/6） */
.bento-main { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--ds-grid-gutter, 24px); }
.bento-card {
  padding: var(--ds-space-5, 20px);
  background: var(--ds-surface-raised);
  border: 1px solid var(--ds-hairline, rgba(255,255,255,.06));
  border-radius: var(--ds-radius-md, 8px);
  box-shadow: var(--ds-elevation-1);
}
.bento-card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--ds-space-4, 16px); }
.bento-card-head h3 { margin: 0; font-weight: var(--ds-type-section-weight, 600); font-size: var(--ds-type-section-size, 16px); color: var(--ds-color-text, #e8f2f7); }
.bento-card-eyebrow { font: 10px var(--ds-font-mono, monospace); color: var(--ds-color-muted, #92a6b5); letter-spacing: .1em; }
.bento-status { grid-column: span 6; }
.bento-activity { grid-column: span 6; }

.status-list { list-style: none; padding: 0; margin: 0; display: grid; gap: var(--ds-space-2, 8px); }
.status-row {
  display: grid; grid-template-columns: 10px 1fr auto; align-items: center; gap: var(--ds-space-3, 12px);
  padding: var(--ds-space-2, 8px) var(--ds-space-3, 12px); border-radius: var(--ds-radius-sm, 4px);
  background: color-mix(in srgb, var(--ds-color-text) 2%, var(--ds-surface-base));
  transition: background var(--ds-duration-micro) var(--ds-ease-out);
}
.status-row:hover { background: color-mix(in srgb, var(--ds-color-primary) 6%, var(--ds-surface-base)); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ds-semantic-success, #3fb950); }
.status-dot--healthy { background: var(--ds-semantic-success, #3fb950); }
.status-dot--warning { background: var(--ds-semantic-warning, #d29922); }
.status-dot--critical { background: var(--ds-semantic-danger, #f85149); }
.status-name { font-size: var(--ds-type-body-caption-size, 13px); color: var(--ds-color-text, #e8f2f7); }
.status-value { font-size: var(--ds-type-caption-size, 12px); color: var(--ds-color-muted, #92a6b5); font-variant-numeric: tabular-nums; }

.activity-list { list-style: none; padding: 0; margin: 0; display: grid; gap: var(--ds-space-2, 8px); }
.activity-row {
  display: grid; grid-template-columns: 64px auto 1fr; align-items: baseline; gap: var(--ds-space-3, 12px);
  padding: var(--ds-space-2, 8px) var(--ds-space-3, 12px); border-radius: var(--ds-radius-sm, 4px);
  background: color-mix(in srgb, var(--ds-color-text) 2%, var(--ds-surface-base));
  font-size: var(--ds-type-body-caption-size, 13px);
}
.activity-time { font: 11px var(--ds-font-mono, monospace); color: var(--ds-color-muted, #92a6b5); }
.activity-type {
  font: 10px var(--ds-font-mono, monospace); letter-spacing: .06em; padding: 2px 6px; border-radius: 4px;
  background: var(--ds-pill-info-bg, rgba(88,166,255,.14)); color: var(--ds-color-primary, #2496ed);
}
.activity-type--agent { background: var(--ds-pill-success-bg, rgba(63,185,80,.15)); color: var(--ds-semantic-success, #3fb950); }
.activity-type--warning { background: var(--ds-pill-warning-bg, rgba(210,153,34,.18)); color: var(--ds-semantic-warning, #d29922); }
.activity-type--danger { background: var(--ds-pill-danger-bg, rgba(248,81,73,.15)); color: var(--ds-semantic-danger, #f85149); }
.activity-text { color: var(--ds-color-text, #e8f2f7); }

/* 紧凑双列 */
.bento-compact { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--ds-grid-gutter, 24px); }
.bento-mini { grid-column: span 6; display: grid; gap: var(--ds-space-2, 8px); }
.bento-mini-value {
  font-weight: var(--ds-type-display-weight, 300); font-size: var(--ds-type-h1-size, 28px);
  font-variant-numeric: tabular-nums; color: var(--ds-color-text, #e8f2f7);
}
.bento-mini-sub { font-size: var(--ds-type-caption-size, 12px); color: var(--ds-color-muted, #92a6b5); }

/* 响应式：≤ 1024 KPI 每卡 6 栅格，≤ 640 每卡 12 栅格 */
@media (max-width: 1024px) {
  .kpi-card { grid-column: span 6; }
}
@media (max-width: 640px) {
  .bento-dashboard { padding: var(--ds-space-4, 16px); gap: var(--ds-space-4, 16px); }
  .kpi-card, .bento-status, .bento-activity, .bento-mini { grid-column: span 12; }
  .status-row { grid-template-columns: 8px 1fr; }
  .status-value { grid-column: 2; justify-self: end; }
}

/* 减少动态 */
@media (prefers-reduced-motion: reduce) {
  .bento-briefing, .kpi-card, .bento-card { transition: none; }
  .kpi-card:hover { transform: none; }
}
</style>
