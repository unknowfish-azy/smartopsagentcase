<template>
  <section class="terminal-workspace" aria-label="终端工作区">
    <div class="workspace-toolbar">
      <div class="workspace-name">
        <span>终端工作区</span>
        <strong>{{ selectedSession?.name || '未选择会话' }}</strong>
      </div>
      <div class="toolbar-actions">
        <button type="button" class="primary-action" :disabled="!selectedSession || connecting || runtimeOnline || Boolean(hostKey)" @click="connectSelected()">
          {{ connecting ? '正在连接…' : runtimeOnline ? '已连接' : runtimeId ? '重新连接' : '连接' }}
        </button>
        <button type="button" :disabled="openTabs.length < 2" @click="layout = layout === 'SINGLE' ? 'SPLIT_VERTICAL' : layout === 'SPLIT_VERTICAL' ? 'SPLIT_HORIZONTAL' : 'SINGLE'">{{ layout === 'SINGLE' ? '左右分屏' : layout === 'SPLIT_VERTICAL' ? '上下分屏' : '单屏' }}</button>
        <button type="button" :disabled="!runtimeId" @click="activeWorkspace = activeWorkspace === 'FILES' ? 'TERMINAL' : 'FILES'">远程文件</button>
        <button type="button" :disabled="!runtimeId" @click="openMultiExec">批量命令</button>
        <button type="button" :class="{ active: activeWorkspace === 'TUNNELS' }" @click="activeWorkspace = activeWorkspace === 'TUNNELS' ? 'TERMINAL' : 'TUNNELS'">隧道</button>
      </div>
    </div>

    <div v-if="openTabs.length" class="runtime-tabs" aria-label="运行会话">
      <div v-for="tab in openTabs" :key="tab.runtimeId">
        <button :aria-pressed="tab.runtimeId === runtimeId" @click="selectSession(tab.session, tab.runtimeId)">{{ tab.session.name }} · {{ tab.status }}</button>
        <button :aria-label="`关闭 ${tab.session.name}`" @click="closeRuntimeTab(tab)">×</button>
      </div>
    </div>
    <div v-show="runtimeId && activeWorkspace === 'TERMINAL'" class="runtime-panes" :class="layout.toLowerCase()">
      <OperationsTerminal v-for="tab in openTabs" v-show="visibleRuntimes.includes(tab.runtimeId)" :key="tab.runtimeId" :runtime-id="tab.runtimeId" :session-name="tab.session.name" @status="tab.status = $event" />
    </div>
    <RemoteFiles v-if="runtimeId && activeWorkspace === 'FILES'" :key="runtimeId" :runtime-id="runtimeId" :session-name="selectedSession?.name" />
    <TunnelWorkspace
      v-if="activeWorkspace === 'TUNNELS'"
      :tunnels="tunnels.filter(tunnel => tunnel.runtimeId === runtimeId)"
      :runtime-online="runtimeOnline"
      :selected-tunnel="selectedTunnel"
      @create="createTunnel"
      @start="startTunnel"
      @stop="stopTunnel"
      @edit="editTunnel"
      @remove="removeTunnel"
      @logs="showTunnelLogs"
    />
    <div v-if="!runtimeId && activeWorkspace === 'TERMINAL'" class="workspace-idle">
      <div class="remote-welcome">
        <div class="remote-logo"><span>&gt;_</span></div>
        <h2>SmartOps Remote</h2>
        <div class="welcome-actions"><button type="button" class="primary-action" @click="showCreate = true"><span class="action-plus">+</span> 新建远程会话</button><button type="button" @click="query = ''; document.querySelector('.session-search input')?.focus()">↻ 恢复最近会话</button></div>
        <label class="welcome-search"><input v-model="query" placeholder="查找现有会话或服务器名…" aria-label="查找现有会话或服务器名" /></label>
      </div>
      <div class="idle-heading">
        <div>
          <span class="section-kicker">已保存目标</span>
          <h2>{{ recentSessions.length ? '最近连接' : '连接资源' }}</h2>
        </div>
        <button v-if="!sessions.length" type="button" class="text-action" @click="showCreate = true">添加 SSH 连接</button>
      </div>
      <div v-if="recentSessions.length" class="recent-sessions">
        <article v-for="session in recentSessions" :key="session.id" class="recent-session">
          <div class="recent-session-copy">
            <strong>{{ session.name }}</strong>
            <span>{{ session.host }}:{{ session.port }} · {{ session.protocol }}</span>
            <small>{{ session.lastConnectedAt ? `上次连接 ${formatLastConnected(session.lastConnectedAt)}` : '尚未连接' }}</small>
          </div>
          <button type="button" :disabled="connecting" @click="selectSession(session); connectSelected()">连接</button>
        </article>
      </div>
      <div v-else class="workspace-empty">
        <h3>{{ selectedSession ? '会话已选中' : '选择一个连接开始工作' }}</h3>
        <p>{{ selectedSession ? `${selectedSession.username}@${selectedSession.host}:${selectedSession.port}` : '连接后将在此显示真实终端输出。当前不会自动执行远程命令。' }}</p>
        <button v-if="selectedSession" type="button" class="primary-action" :disabled="connecting" @click="connectSelected()">{{ connecting ? '正在连接…' : '连接所选会话' }}</button>
        <button v-else type="button" class="text-action" @click="showCreate = true">新建 SSH 会话</button>
      </div>
    </div>
    <p v-if="connectionError" class="connection-error" role="alert">{{ connectionError }}</p>
  </section>
</template>

<script setup>
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'
import OperationsTerminal from './OperationsTerminal.vue'
import RemoteFiles from './RemoteFiles.vue'
import TunnelWorkspace from './TunnelWorkspace.vue'

const {
  query,
  openTabs,
  sessions,
  showCreate,
  selectedSession,
  runtimeId,
  connecting,
  connectionError,
  hostKey,
  layout,
  visibleRuntimes,
  activeWorkspace,
  tunnels,
  selectedTunnel,
  runtimeOnline,
  recentSessions,
  formatLastConnected,
  selectSession,
  closeRuntimeTab,
  createTunnel,
  startTunnel,
  stopTunnel,
  editTunnel,
  removeTunnel,
  showTunnelLogs,
  connectSelected,
  openMultiExec
} = inject(CONNECTIONS_WORKSPACE_KEY)
</script>

<style scoped>
.terminal-workspace {
  display: flex;
  flex-direction: column;
  min-width: 0;
  grid-template-rows: auto 1fr auto;
  background: var(--smart-bg);
}

.runtime-tabs { display:flex; flex-wrap:wrap; gap:4px; padding:8px; border-bottom:1px solid var(--smart-border-strong); }
.runtime-tabs > div { display:flex; max-width:100%; }
.runtime-tabs button { color:var(--smart-muted); background:var(--smart-surface); border:1px solid var(--smart-border-strong); padding:8px; overflow-wrap:anywhere; cursor:pointer; }
.runtime-tabs button[aria-pressed="true"] { color:var(--smart-primary-strong); border-color:color-mix(in srgb, var(--smart-primary-strong) 60%, var(--smart-border-strong)); }
.runtime-panes { display:grid; grid-template-columns:minmax(0,1fr); min-width:0; }
.runtime-panes.split_vertical { grid-template-columns:repeat(2,minmax(0,1fr)); }
@media (max-width:1024px) { .runtime-panes.split_vertical { grid-template-columns:minmax(0,1fr); } }

.workspace-toolbar {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--smart-border);
}

.workspace-name span,
.workspace-name strong {
  display: block;
}

.workspace-name span {
  color: var(--smart-muted);
  font-size: 10px;
}

.workspace-name strong {
  margin-top: 4px;
  color: var(--smart-text);
  font-size: 12px;
  font-weight: 550;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.toolbar-actions button,
.recent-session button {
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--smart-border-strong);
  border-radius: 3px;
  background: var(--smart-surface-raised);
  color: var(--smart-muted);
  font: 11px var(--font-cn);
  cursor: pointer;
}

.toolbar-actions button.active,
.toolbar-actions button.primary-action,
.primary-action {
  border-color: color-mix(in srgb, var(--smart-success) 50%, var(--smart-border-strong));
  background: color-mix(in srgb, var(--smart-success) 20%, var(--smart-surface));
  color: color-mix(in srgb, var(--smart-success) 55%, var(--smart-text));
}

button:disabled {
  opacity: .42;
  cursor: not-allowed;
}

.workspace-idle {
  display: grid;
  align-content: start;
  gap: 16px;
  min-height: 0;
  padding: 20px;
}

.section-kicker {
  display: block;
  margin-bottom: 6px;
  color: var(--smart-muted);
  font: 10px var(--font-mono);
  letter-spacing: .08em;
}

.idle-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.idle-heading h2 {
  margin: 0;
  color: var(--smart-text);
  font-weight: 550;
  font-size: 15px;
}

.recent-sessions {
  display: grid;
  border-top: 1px solid var(--smart-border);
}

.recent-session {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 2px;
  border-bottom: 1px solid var(--smart-border);
}

.recent-session-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.recent-session-copy strong,
.recent-session-copy span,
.recent-session-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-session-copy strong {
  color: var(--smart-text);
  font-size: 12px;
}

.recent-session-copy span {
  color: var(--smart-muted);
  font: 11px var(--font-mono);
}

.recent-session-copy small {
  color: var(--smart-muted);
  font-size: 10px;
}

.recent-session button {
  min-width: 58px;
  color: color-mix(in srgb, var(--smart-success) 55%, var(--smart-text));
}

.workspace-empty {
  align-self: center;
  padding: 28px 0;
  border-top: 1px solid var(--smart-border);
}

.workspace-empty h3 {
  margin: 0;
  color: var(--smart-text);
  font-size: 14px;
  font-weight: 550;
}

.workspace-empty p {
  max-width: 500px;
  margin: 8px 0 14px;
  color: var(--smart-muted);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.connection-error {
  color: var(--smart-danger);
  font-size: 12px;
}

.text-action {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid var(--smart-border-strong);
  background: transparent;
  color: var(--smart-text);
  font: 12px var(--font-cn);
  cursor: pointer;
}

.text-action:hover {
  border-color: color-mix(in srgb, var(--smart-primary) 25%, var(--smart-border-strong));
  background: color-mix(in srgb, var(--smart-text) 5%, var(--smart-surface));
}

.remote-welcome{display:grid;justify-items:center;gap:12px;padding:28px 18px 24px;text-align:center}.remote-logo{display:grid;place-items:center;width:72px;height:62px;border:4px solid color-mix(in srgb, var(--smart-muted) 80%, var(--smart-bg));background:color-mix(in srgb, var(--smart-muted) 15%, var(--smart-surface-raised));box-shadow:6px 6px 0 var(--ds-semantic-danger),12px 12px 0 color-mix(in srgb, var(--smart-primary) 75%, var(--smart-primary-strong)),18px 18px 0 color-mix(in srgb, var(--ds-semantic-success) 55%, var(--smart-warning));transform:skew(-8deg)}.remote-logo span{color:var(--smart-text);font:700 22px var(--font-mono);transform:skew(8deg)}.remote-welcome h2{margin:5px 0 8px;color:var(--smart-text);font:400 38px var(--font-cn);letter-spacing:.01em}.welcome-actions{display:flex;gap:18px}.welcome-actions button{min-width:220px;padding:12px 20px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font:16px var(--font-cn);cursor:pointer}.welcome-actions button:hover{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong)}.welcome-actions .primary-action{border-color:color-mix(in srgb, var(--smart-primary) 65%, var(--smart-text));background:color-mix(in srgb, color-mix(in srgb, var(--smart-primary) 65%, var(--smart-text)) 8%, var(--smart-surface));color:var(--smart-text)}.action-plus{display:inline-grid;place-items:center;width:20px;height:20px;margin-right:5px;border-radius:50%;background:var(--ds-semantic-success);color:var(--smart-text)}.welcome-search{width:min(620px,90%);margin-top:6px}.welcome-search input{width:100%;padding:10px 14px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font:15px var(--font-cn);outline:none}.welcome-search input:focus{border-color:var(--smart-primary-strong)}

@media (max-width: 700px) {
  .terminal-workspace {
    min-height: 380px;
  }

  .workspace-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media(max-width:760px){.remote-welcome h2{font-size:30px}.welcome-actions{flex-direction:column;gap:8px}.welcome-actions button{min-width:240px}}
</style>
