<template>
  <section class="alerts" :class="{ compact }" aria-labelledby="alerts-title">
    <header class="alerts-head">
      <div>
        <p class="alerts-eyebrow">ALERT CENTER · 异常聚合</p>
        <h3 id="alerts-title">预警中心</h3>
      </div>
      <div class="alerts-tools">
        <span v-if="pendingCount" class="pending-badge">{{ pendingCount }} 未确认</span>
        <button type="button" class="refresh-btn" title="立即刷新" @click="emit('refresh')">刷新</button>
      </div>
    </header>

    <div v-if="!compact" class="alerts-summary">
      <span v-for="item in severitySummary" :key="item.key" class="summary-chip" :class="item.key.toLowerCase()">
        <b>{{ item.count }}</b> {{ item.label }}
      </span>
    </div>

    <div v-if="!compact" class="alerts-filters">
      <button
        v-for="filter in FILTERS"
        :key="filter.key"
        type="button"
        class="filter-btn"
        :class="{ active: activeFilter === filter.key }"
        @click="activeFilter = filter.key"
      >{{ filter.label }}</button>
    </div>

    <ul v-if="visible.length" class="alert-list">
      <li v-for="alert in visible" :key="alert.id" class="alert-item" :class="[alert.severity.toLowerCase(), { acked: alert.acked }]">
        <span class="severity-tag" :class="alert.severity.toLowerCase()">{{ severityLabel(alert.severity) }}</span>
        <div class="alert-body">
          <div class="alert-title">
            <strong>{{ alert.title }}</strong>
            <span class="source-tag">{{ sourceLabel(alert.source) }}</span>
            <span v-if="alert.acked" class="acked-tag">已确认</span>
          </div>
          <p class="alert-detail">{{ alert.detail }}</p>
          <div class="alert-meta">
            <span>{{ alert.timeText }}</span>
            <button
              v-if="alert.deviceKey"
              type="button"
              class="device-link"
              @click="emit('select-device', alert.deviceKey)"
            >定位 {{ alert.deviceKey }}</button>
            <router-link v-if="alert.link" :to="alert.link" class="detail-link">前往复核 →</router-link>
          </div>
        </div>
        <button
          type="button"
          class="ack-btn"
          :class="{ restore: alert.acked }"
          @click="alert.acked ? emit('restore', alert.id) : emit('acknowledge', alert.id)"
        >{{ alert.acked ? '恢复' : '确认' }}</button>
      </li>
    </ul>

    <div v-else class="alerts-empty">
      <template v-if="alerts.length">当前筛选下没有预警</template>
      <template v-else>暂无预警。设备电量、心跳、障碍与视觉异常都会自动汇聚到这里。</template>
    </div>

    <p v-if="compact && alerts.length > visible.length" class="more-hint">
      还有 {{ alerts.length - visible.length }} 条，切换「预警」页查看全部
    </p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  alerts: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  limit: { type: Number, default: 0 }
})

const emit = defineEmits(['acknowledge', 'restore', 'refresh', 'select-device'])

const FILTERS = [
  { key: 'pending', label: '未确认' },
  { key: 'all', label: '全部' },
  { key: 'CRITICAL', label: '严重' },
  { key: 'HIGH', label: '高' },
  { key: 'WARN', label: '警告' }
]

const activeFilter = ref('pending')

const SEVERITY_TEXT = { CRITICAL: '严重', HIGH: '高', WARN: '警告', INFO: '提示' }
const SOURCE_TEXT = { VISUAL: '视觉', DEVICE: '设备', TASK: '任务' }

function severityLabel(value) {
  return SEVERITY_TEXT[value] || value
}

function sourceLabel(value) {
  return SOURCE_TEXT[value] || value
}

const pendingCount = computed(() => props.alerts.filter(alert => !alert.acked).length)

const filtered = computed(() => {
  if (props.compact) return props.alerts.filter(alert => !alert.acked)
  if (activeFilter.value === 'pending') return props.alerts.filter(alert => !alert.acked)
  if (activeFilter.value === 'all') return props.alerts
  return props.alerts.filter(alert => alert.severity === activeFilter.value)
})

const visible = computed(() => {
  const limit = props.compact ? (props.limit || 6) : 60
  return filtered.value.slice(0, limit)
})

const severitySummary = computed(() => ['CRITICAL', 'HIGH', 'WARN', 'INFO'].map(key => ({
  key,
  label: SEVERITY_TEXT[key],
  count: props.alerts.filter(alert => alert.severity === key && !alert.acked).length
})))
</script>

<style scoped>
.alerts {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
  min-width: 0;
}

.alerts-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.alerts-eyebrow {
  margin: 0 0 2px;
  color: var(--ds-color-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
}

.alerts-head h3 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.alerts-tools {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pending-badge {
  padding: 2px 8px;
  border-radius: var(--ds-radius-pill);
  background: rgba(227, 160, 8, 0.16);
  color: #f0c260;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.refresh-btn {
  padding: 3px 9px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 10px;
  cursor: pointer;
}

.refresh-btn:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.alerts-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.summary-chip {
  padding: 3px 9px;
  border-radius: var(--ds-radius-pill);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  font-size: 10px;
}

.summary-chip b {
  color: var(--ds-color-text);
  font-variant-numeric: tabular-nums;
}

.summary-chip.critical b { color: #ff9aa4; }
.summary-chip.high b { color: #f0c260; }
.summary-chip.warn b { color: #d9b96d; }

.alerts-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.filter-btn {
  padding: 3px 9px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 10px;
  cursor: pointer;
}

.filter-btn.active {
  border-color: var(--ds-color-primary);
  background: rgba(36, 150, 237, 0.14);
  color: var(--ds-color-text);
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: v-bind("compact ? '260px' : '520px'");
  overflow-y: auto;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--ds-color-border);
  border-left-width: 3px;
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.alert-item.critical { border-left-color: #e0646e; }
.alert-item.high { border-left-color: #e3a008; }
.alert-item.warn { border-left-color: #d9b96d; }
.alert-item.info { border-left-color: #4c8fbe; }

.alert-item.acked {
  opacity: 0.55;
}

.severity-tag {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  white-space: nowrap;
}

.severity-tag.critical { background: rgba(224, 100, 110, 0.18); color: #ff9aa4; }
.severity-tag.high { background: rgba(227, 160, 8, 0.18); color: #f0c260; }
.severity-tag.warn { background: rgba(217, 185, 109, 0.14); color: #e2cc8d; }
.severity-tag.info { background: rgba(76, 143, 190, 0.16); color: #8fc3e2; }

.alert-body {
  flex: 1;
  min-width: 0;
}

.alert-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: var(--ds-font-xs);
}

.alert-title strong {
  font-size: var(--ds-font-sm);
  font-weight: 600;
}

.source-tag,
.acked-tag {
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(120, 140, 160, 0.14);
  color: var(--ds-color-muted);
  font-size: 9px;
}

.acked-tag {
  background: rgba(58, 190, 132, 0.14);
  color: #6ddcab;
}

.alert-detail {
  margin: 3px 0 2px;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.alert-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--ds-color-muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.device-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ds-color-primary);
  font-size: 10px;
  cursor: pointer;
}

.detail-link {
  color: var(--ds-color-primary);
  font-size: 10px;
  text-decoration: none;
}

.ack-btn {
  flex-shrink: 0;
  padding: 3px 8px;
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 10px;
  cursor: pointer;
}

.ack-btn:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-text);
}

.ack-btn.restore:hover {
  border-color: rgba(227, 160, 8, 0.5);
}

.alerts-empty {
  padding: var(--ds-space-4);
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: 1.6;
  text-align: center;
}

.more-hint {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: 10px;
  text-align: right;
}
</style>
