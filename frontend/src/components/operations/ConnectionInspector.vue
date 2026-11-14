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
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'

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

.context-error {
  color: #fca5a5;
  font-size: 12px;
}

.inspector-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #aab8be;
  font-size: 11px;
}

.inspector-state::before {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #64717a;
  content: '';
}

.inspector-state.online::before {
  background: #22c55e;
}

.inspector-state.online {
  color: #86d6a7;
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
  border-top: 1px solid #18222d;
}

.session-details dt {
  color: var(--smart-muted);
  font-size: 11px;
}

.session-details dd {
  min-width: 0;
  margin: 0;
  color: #c9d5da;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.agent-context,
.capability-list {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #263541;
}

.subsection-heading h3 {
  font-size: 12px;
}

.subsection-heading span {
  color: #86d6a7;
  font-size: 10px;
}

.agent-context > p {
  margin: 10px 0 0;
  color: #91a0a8;
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
  border: 1px solid #263541;
  color: #b9c7cd;
  font-size: 10px;
}

.agent-context .approval-boundary {
  color: #f4c879;
}

.capability-list {
  margin-top: 18px;
}

.capability-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #18222d;
  color: #c9d5da;
  font: 10px var(--font-mono);
}

.capability-row small {
  color: #b6a06b;
  font: 10px var(--font-cn);
  text-align: right;
}

.capability-row small.supported {
  color: #86d6a7;
}

@media (max-width: 1180px) {
  .server-inspector {
    grid-column: 1 / -1;
    border-top: 1px solid #18222d;
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
    border-bottom: 1px solid #18222d;
  }

  .inspector-content {
    display: block;
  }

  .agent-context {
    margin-top: 16px;
  }
}
</style>
