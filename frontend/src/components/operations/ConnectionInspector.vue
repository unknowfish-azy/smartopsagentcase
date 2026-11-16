<template>
  <aside class="server-inspector" aria-label="会话检查器">
    <div class="panel-heading inspector-heading">
      <div>
        <h2>会话检查器</h2>
        <small>连接状态与目标信息</small>
      </div>
      <span class="inspector-state" :class="{ online: runtimeOnline }">{{ activeTab?.status || '空闲' }}</span>
    </div>

    <div v-if="selectedSession" class="inspector-content">
      <dl class="session-details">
        <div><dt>目标</dt><dd>{{ selectedSession.name }}</dd></div>
        <div><dt>主机</dt><dd>{{ selectedSession.host }}:{{ selectedSession.port }}</dd></div>
        <div><dt>协议</dt><dd>{{ selectedSession.protocol }}</dd></div>
        <div><dt>用户</dt><dd>{{ selectedSession.username }}</dd></div>
        <div><dt>最近连接</dt><dd>{{ formatLastConnected(selectedSession.lastConnectedAt) }}</dd></div>
        <div><dt>桥接</dt><dd>{{ bridgeStatus }}</dd></div>
      </dl>

      <section class="monitor-panel" aria-label="实时监控">
        <div class="subsection-heading">
          <h3>实时监控</h3>
          <span v-if="monitorActive" class="monitor-intervals">
            <button v-for="option in [3000, 5000, 10000]" :key="option" type="button" :class="{ active: monitor.intervalMs.value === option }" @click="monitor.setIntervalValue(option)">{{ option / 1000 }}s</button>
          </span>
        </div>
        <p v-if="!runtimeId">连接后每 {{ monitor.intervalMs.value / 1000 }} 秒对目标做一次真实采样（/proc + df），不会自动执行其他命令。</p>
        <p v-else-if="!runtimeOnline">会话在线后开始采样。</p>
        <template v-else>
          <p v-if="monitor.error.value" class="monitor-error" role="status">{{ monitor.error.value }}</p>
          <p v-else-if="monitor.sampling.value && !monitor.latest.value" class="monitor-hint">正在采样…</p>
          <template v-if="monitor.latest.value">
            <template v-if="monitor.latest.value.supported">
              <div class="monitor-grid">
                <div class="monitor-row">
                  <span class="monitor-label">CPU</span>
                  <span class="monitor-bar"><i :style="{ width: cpuWidth }" /></span>
                  <span class="monitor-value">{{ cpuText }}</span>
                </div>
                <div class="monitor-row">
                  <span class="monitor-label">内存</span>
                  <span class="monitor-bar"><i :style="{ width: memWidth }" /></span>
                  <span class="monitor-value">{{ memText }}</span>
                </div>
                <div class="monitor-row">
                  <span class="monitor-label">负载</span>
                  <span class="monitor-bar"><i :style="{ width: loadWidth }" /></span>
                  <span class="monitor-value">{{ loadText }}</span>
                </div>
                <div class="monitor-row">
                  <span class="monitor-label">网络</span>
                  <span class="monitor-bar dim"><i :style="{ width: '100%' }" /></span>
                  <span class="monitor-value">↓{{ rateText.rx }} ↑{{ rateText.tx }}</span>
                </div>
                <div class="monitor-row">
                  <span class="monitor-label">磁盘 /</span>
                  <span class="monitor-bar"><i :style="{ width: diskWidth }" /></span>
                  <span class="monitor-value">{{ diskText }}</span>
                </div>
              </div>
              <canvas ref="spark" class="monitor-spark" width="216" height="54" aria-hidden="true"></canvas>
              <p class="monitor-hint">趋势线：青=CPU 绿=内存（最近 {{ monitor.history.value.length }} 次采样）</p>
            </template>
            <p v-else class="monitor-error">该目标不支持采样：{{ monitor.latest.value.reason }}（Windows/受限 shell 无 /proc）</p>
          </template>
        </template>
      </section>

      <section class="agent-context" aria-label="Agent 只读上下文">
        <div class="subsection-heading">
          <h3>Agent 上下文</h3>
          <span>只读</span>
        </div>
        <p v-if="!runtimeId">连接后读取允许的分析动作，不会自动执行命令。</p>
        <p v-else-if="agentContextLoading">正在读取会话上下文…</p>
        <p v-else-if="agentContextError" class="context-error">{{ agentContextError }}</p>
        <template v-else-if="agentContext">
          <ul class="allowed-actions">
            <li v-for="action in agentContext.allowedActions" :key="action">{{ agentActionLabel(action) }}</li>
          </ul>
          <p class="approval-boundary">{{ executionBoundaryLabel(agentContext.executionBoundary) }}</p>
        </template>
      </section>
    </div>
    <div v-else class="inspector-empty">选择一个已保存会话查看目标和连接信息。</div>

    <section class="capability-list">
      <div class="subsection-heading"><h3>桥接能力</h3><small>{{ capabilities.length }} 项</small></div>
      <div v-for="capability in capabilities" :key="capability.protocol" class="capability-row">
        <span>{{ capability.protocol }}</span>
        <small :class="{ supported: capability.status === 'SUPPORTED' }">{{ capabilityLabelZh(capability) }}</small>
      </div>
    </section>
  </aside>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'
import { useServerMonitor } from '../../composables/useServerMonitor.js'
import { drawSparkline, formatKb, formatRate, readSparklinePalette } from './serverMonitor.js'

const {
  activeTab,
  runtimeOnline,
  selectedSession,
  bridgeStatus,
  runtimeId,
  agentContext,
  agentContextLoading,
  agentContextError,
  capabilities,
  capabilityLabelZh,
  agentActionLabel,
  executionBoundaryLabel,
  formatLastConnected
} = inject(CONNECTIONS_WORKSPACE_KEY)

const monitor = useServerMonitor(runtimeId, runtimeOnline)
const monitorActive = computed(() => Boolean(runtimeId.value && runtimeOnline.value))
const spark = ref(null)

watch(() => monitor.history.value.length, () => {
  drawSparkline(spark.value, monitor.history.value, readSparklinePalette())
})

const cpuWidth = computed(() => pctWidth(monitor.latest.value?.cpuPercent))
const cpuText = computed(() => {
  const value = monitor.latest.value?.cpuPercent
  return Number.isFinite(value) ? `${value.toFixed(0)}%` : '采样不足'
})
const memWidth = computed(() => pctWidth(memPercent(monitor.latest.value)))
const memText = computed(() => {
  const sample = monitor.latest.value
  if (!Number.isFinite(sample?.memTotalKb) || !Number.isFinite(sample?.memAvailableKb)) return '—'
  const used = sample.memTotalKb - sample.memAvailableKb
  return `${pctText(memPercent(sample))} · ${formatKb(used)}/${formatKb(sample.memTotalKb)}`
})
const loadWidth = computed(() => {
  const load = monitor.latest.value?.load1
  return Number.isFinite(load) ? `${Math.min(100, load * 25)}%` : '0%'
})
const loadText = computed(() => {
  const sample = monitor.latest.value
  return Number.isFinite(sample?.load1) ? `${sample.load1.toFixed(2)} / ${Number.isFinite(sample?.load5) ? sample.load5.toFixed(2) : '—'} / ${Number.isFinite(sample?.load15) ? sample.load15.toFixed(2) : '—'}` : '—'
})
const rateText = computed(() => ({
  rx: formatRate(monitor.rate.value?.rxPerSec),
  tx: formatRate(monitor.rate.value?.txPerSec)
}))
const diskWidth = computed(() => pctWidth(monitor.latest.value?.diskUsagePercent))
const diskText = computed(() => {
  const sample = monitor.latest.value
  if (!Number.isFinite(sample?.diskUsagePercent)) return '—'
  return `${sample.diskUsagePercent}% · 余 ${formatKb(sample.diskAvailKb)}`
})

function memPercent(sample) {
  if (!Number.isFinite(sample?.memTotalKb) || !Number.isFinite(sample?.memAvailableKb) || sample.memTotalKb <= 0) return null
  return Math.max(0, Math.min(100, ((sample.memTotalKb - sample.memAvailableKb) * 100) / sample.memTotalKb))
}
function pctWidth(value) {
  return Number.isFinite(value) ? `${Math.max(2, Math.min(100, value))}%` : '0%'
}
function pctText(value) {
  return Number.isFinite(value) ? `${value.toFixed(0)}%` : '—'
}
</script>

<style scoped>
.server-inspector {
  min-width: 0;
  padding: 16px;
  background: var(--smart-surface);
  border-left: 1px solid var(--smart-border);
}

.panel-heading,
.inspector-heading,
.subsection-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading h2,
.subsection-heading h3 {
  margin: 0;
  color: var(--smart-text);
  font-size: 13px;
  font-weight: 550;
}

.panel-heading small,
.subsection-heading small {
  display: block;
  margin-top: 4px;
  color: var(--smart-muted);
  font-size: 11px;
}

.inspector-empty {
  padding: 14px 0;
  color: var(--smart-muted);
  font-size: 12px;
}

.monitor-panel { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--smart-border); }
.monitor-panel > p { margin: 8px 0; color: var(--smart-muted); font-size: 11px; line-height: 1.6; }
.monitor-intervals { display: flex; gap: 4px; }
.monitor-intervals button { min-width: 30px; padding: 2px 6px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-muted); font: 10px var(--font-mono); cursor: pointer; }
.monitor-intervals button.active { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }
.monitor-error { color: var(--smart-warning); font-size: 11px; }
.monitor-hint { color: var(--smart-muted); font-size: 10px; }
.monitor-grid { display: grid; gap: 7px; margin-top: 10px; }
.monitor-row { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.monitor-label { color: var(--smart-muted); font-size: 10px; }
.monitor-bar { position: relative; height: 8px; overflow: hidden; border-radius: 4px; background: color-mix(in srgb, var(--smart-text) 8%, var(--smart-surface)); }
.monitor-bar i { position: absolute; inset: 0 auto 0 0; display: block; border-radius: 4px; background: linear-gradient(90deg, color-mix(in srgb, var(--smart-primary) 70%, transparent), var(--smart-primary-strong)); transition: width .25s ease; }
.monitor-bar.dim i { background: color-mix(in srgb, var(--smart-muted) 35%, transparent); }
.monitor-value { color: var(--smart-text); font: 10px var(--font-mono); white-space: nowrap; }
.monitor-spark { display: block; width: 100%; height: 54px; margin-top: 10px; border: 1px solid var(--smart-border); background: color-mix(in srgb, var(--smart-text) 3%, var(--smart-surface)); }

.context-error {
  color: var(--smart-danger);
  font-size: 12px;
}

.inspector-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--smart-muted);
  font-size: 11px;
}

.inspector-state::before {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--smart-muted);
  content: '';
}

.inspector-state.online::before {
  background: var(--smart-success);
}

.inspector-state.online {
  color: var(--ds-semantic-success);
}

.inspector-content {
  margin-top: 16px;
}

.session-details {
  margin: 0;
}

.session-details div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 0;
  border-top: 1px solid var(--smart-border);
}

.session-details dt {
  color: var(--smart-muted);
  font-size: 11px;
}

.session-details dd {
  min-width: 0;
  margin: 0;
  color: var(--smart-text);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.agent-context,
.capability-list {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--smart-border-strong);
}

.subsection-heading h3 {
  font-size: 12px;
}

.subsection-heading span {
  color: var(--ds-semantic-success);
  font-size: 10px;
}

.agent-context > p {
  margin: 10px 0 0;
  color: var(--smart-muted);
  font-size: 11px;
  line-height: 1.55;
}

.allowed-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 10px 0;
  padding: 0;
  list-style: none;
}

.allowed-actions li {
  padding: 4px 6px;
  border: 1px solid var(--smart-border-strong);
  color: var(--smart-muted);
  font-size: 10px;
}

.agent-context .approval-boundary {
  color: var(--smart-warning);
}

.capability-list {
  margin-top: 18px;
}

.capability-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--smart-border);
  color: var(--smart-text);
  font: 10px var(--font-mono);
}

.capability-row small {
  color: var(--smart-warning);
  font: 10px var(--font-cn);
  text-align: right;
}

.capability-row small.supported {
  color: var(--ds-semantic-success);
}

@media (max-width: 1180px) {
  .server-inspector {
    grid-column: 1 / -1;
    border-top: 1px solid var(--smart-border);
    border-left: 0;
  }

  .inspector-content {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 18px;
  }

  .agent-context {
    margin-top: 0;
  }

  .capability-list {
    grid-column: 1 / -1;
  }
}

@media (max-width: 700px) {
  .server-inspector {
    border-bottom: 1px solid var(--smart-border);
  }

  .inspector-content {
    display: block;
  }

  .agent-context {
    margin-top: 16px;
  }
}
</style>
