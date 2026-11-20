<template>
  <section v-if="brief" class="sbc" :class="`sbc--${tone}`" aria-label="安全意识简报">
    <header class="sbc-head">
      <span class="sbc-badge">安全意识简报</span>
      <span class="sbc-risk">{{ riskLabel }}</span>
      <span class="sbc-conf">置信度 {{ confidenceText }}</span>
      <span v-if="brief.requires_human" class="sbc-human">需人工确认</span>
    </header>

    <p v-if="brief.narrative" class="sbc-narrative">{{ brief.narrative }}</p>

    <dl class="sbc-grid">
      <div>
        <dt>意图</dt>
        <dd>{{ brief.intent || '未识别' }}</dd>
      </div>
      <div>
        <dt>风险原因</dt>
        <dd>{{ reasonsText }}</dd>
      </div>
      <div>
        <dt>影响资产</dt>
        <dd>{{ assetsText }}</dd>
      </div>
      <div>
        <dt>影响服务</dt>
        <dd>{{ servicesText }}</dd>
      </div>
      <div>
        <dt>影响用户</dt>
        <dd>{{ usersText }}</dd>
      </div>
      <div v-if="approvalsText">
        <dt>前置审批</dt>
        <dd>{{ approvalsText }}</dd>
      </div>
    </dl>

    <div v-if="preconditions.length" class="sbc-block">
      <h4>前置条件</h4>
      <ul>
        <li v-for="item in preconditions" :key="item">{{ item }}</li>
      </ul>
    </div>

    <div class="sbc-block">
      <h4>回滚计划</h4>
      <p>{{ brief.rollback_plan || '无' }}</p>
    </div>

    <div v-if="verification.length" class="sbc-block">
      <h4>验证清单</h4>
      <ul>
        <li v-for="item in verification" :key="item">{{ item }}</li>
      </ul>
    </div>

    <details class="sbc-details">
      <summary>为什么这样判断</summary>
      <p><b>数据来源：</b>{{ sourcesText }}</p>
      <p><b>证据引用：</b>{{ evidenceText }}</p>
      <p v-if="brief.attack_report" class="sbc-attack">{{ brief.attack_report }}</p>
    </details>

    <p v-if="brief.honesty_note" class="sbc-honesty">{{ brief.honesty_note }}</p>
  </section>

  <p v-else class="sbc sbc--empty" role="status">
    本次未生成安全简报（规则降级或服务未返回），不展示推测结论。
  </p>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  brief: { type: Object, default: null },
})

const RISK_LABELS = {
  CRITICAL: '极高风险',
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
}

const tone = computed(() => {
  const level = String(props.brief?.risk_level || '').toUpperCase()
  if (level === 'CRITICAL' || level === 'HIGH') return 'danger'
  if (level === 'MEDIUM') return 'warning'
  return 'success'
})

const riskLabel = computed(() => RISK_LABELS[String(props.brief?.risk_level || '').toUpperCase()] || '未知风险')

const confidenceText = computed(() => {
  const value = Number(props.brief?.confidence)
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : '未提供'
})

const blast = computed(() => props.brief?.blast_radius || {})

function joinList(value, emptyText = '无') {
  const list = Array.isArray(value) ? value.filter(Boolean) : []
  return list.length ? list.join('、') : emptyText
}

const reasonsText = computed(() => joinList(props.brief?.risk_reasons))
const assetsText = computed(() => joinList(blast.value.assets, '未提供'))
const servicesText = computed(() => joinList(blast.value.services, '未提供'))
// 无真实资产数据时如实显示"未运行/无数据"，不编造估算值。
const usersText = computed(() => {
  const users = blast.value.estimated_users
  return typeof users === 'number' ? String(users) : '未运行/无数据'
})
const approvalsText = computed(() => joinList(props.brief?.required_approvals, ''))
const preconditions = computed(() => (Array.isArray(props.brief?.preconditions) ? props.brief.preconditions : []))
const verification = computed(() => (Array.isArray(props.brief?.verification_plan) ? props.brief.verification_plan : []))
const sourcesText = computed(() => joinList(props.brief?.data_sources))
const evidenceText = computed(() => joinList(props.brief?.evidence_refs))
</script>

<style scoped>
.sbc {
  --sbc-accent: var(--ds-semantic-neutral);
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--ds-hairline, rgba(255, 255, 255, .08));
  border-left: 3px solid var(--sbc-accent);
  border-radius: var(--ds-radius-md, 8px);
  background: var(--ds-surface-raised, #151a21);
  color: var(--ds-color-text, #e8f2f7);
  font-size: var(--ds-font-sm, 13px);
  line-height: var(--ds-line-base, 1.55);
}

.sbc--danger { --sbc-accent: var(--ds-semantic-danger); }
.sbc--warning { --sbc-accent: var(--ds-semantic-warning); }
.sbc--success { --sbc-accent: var(--ds-semantic-success); }

.sbc--empty {
  border-left-color: var(--ds-semantic-neutral);
  color: var(--ds-color-muted, #92a6b5);
  font-size: var(--ds-font-xs, 12px);
}

.sbc-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.sbc-badge {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--ds-color-muted, #92a6b5);
}

.sbc-risk {
  padding: 1px 8px;
  border-radius: var(--ds-radius-pill, 999px);
  border: 1px solid var(--sbc-accent);
  color: var(--sbc-accent);
  font-weight: 600;
}

.sbc-conf {
  color: var(--ds-color-muted, #92a6b5);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.sbc-human {
  margin-left: auto;
  padding: 1px 8px;
  border-radius: var(--ds-radius-pill, 999px);
  background: var(--ds-pill-warning-bg, rgba(210, 153, 34, .18));
  color: var(--ds-pill-warning-fg, #d29922);
  font-size: 12px;
}

.sbc-narrative {
  margin: 0;
  color: var(--ds-color-text, #e8f2f7);
}

.sbc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px 12px;
  margin: 0;
}

.sbc-grid dt {
  font-size: 11px;
  color: var(--ds-color-muted, #92a6b5);
}

.sbc-grid dd {
  margin: 2px 0 0;
  word-break: break-word;
}

.sbc-block h4 {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--ds-color-muted, #92a6b5);
  font-weight: 600;
}

.sbc-block p {
  margin: 0;
}

.sbc-block ul {
  margin: 0;
  padding-left: 18px;
}

.sbc-details {
  border-top: 1px solid var(--ds-hairline, rgba(255, 255, 255, .08));
  padding-top: 8px;
}

.sbc-details summary {
  cursor: pointer;
  color: var(--ds-semantic-info, #58a6ff);
  font-size: 12px;
}

.sbc-details p {
  margin: 6px 0 0;
  color: var(--ds-color-muted, #92a6b5);
  word-break: break-word;
}

.sbc-attack {
  color: var(--ds-semantic-warning, #d29922);
}

.sbc-honesty {
  margin: 0;
  color: var(--ds-color-muted, #92a6b5);
  font-size: 11px;
}
</style>
