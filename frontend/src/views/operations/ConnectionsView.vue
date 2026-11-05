<template>
  <article class="connections-page">
    <ConnectionsHeaderBar :bridge-ready="bridgeReady" :bridge-status="bridgeStatus" />

    <RemoteMenuBar @open-dialog="openRemoteDialog" />

    <RemoteToolbar @open-dialog="openRemoteDialog" />

    <p v-if="initialLoading" role="status">正在加载连接资源…</p>
    <div v-if="initialError" role="alert">连接资源加载失败：{{ initialError }} <button @click="loadResources">重试</button></div>

    <section class="operations-workspace" :class="{ 'session-tree-hidden': !showSessionTree, 'server-inspector-hidden': !showServerInspector }" aria-label="远程运维工作区">
      <ConnectionSessionTree />

      <ConnectionTerminalWorkspace />

      <ConnectionInspector />
    </section>

    <RemoteToolDialog />

    <HostKeyDialog />

    <MultiExecDialog />

    <CreateSessionDialog />
  </article>
</template>

<script setup>
import { provide } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY, useConnectionsWorkspace } from '../../composables/useConnectionsWorkspace.js'
import ConnectionsHeaderBar from '../../components/operations/ConnectionsHeaderBar.vue'
import RemoteMenuBar from '../../components/operations/RemoteMenuBar.vue'
import RemoteToolbar from '../../components/operations/RemoteToolbar.vue'
import ConnectionSessionTree from '../../components/operations/ConnectionSessionTree.vue'
import ConnectionTerminalWorkspace from '../../components/operations/ConnectionTerminalWorkspace.vue'
import ConnectionInspector from '../../components/operations/ConnectionInspector.vue'
import RemoteToolDialog from '../../components/operations/RemoteToolDialog.vue'
import HostKeyDialog from '../../components/operations/HostKeyDialog.vue'
import MultiExecDialog from '../../components/operations/MultiExecDialog.vue'
import CreateSessionDialog from '../../components/operations/CreateSessionDialog.vue'

const workspace = useConnectionsWorkspace()
provide(CONNECTIONS_WORKSPACE_KEY, workspace)

const {
  bridgeReady,
  bridgeStatus,
  initialLoading,
  initialError,
  showSessionTree,
  showServerInspector,
  openRemoteDialog,
  loadResources
} = workspace
</script>

<style scoped>
:global([data-theme='light'] .connections-page) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page .capability-row > span) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page .capability-row small.supported),
:global([data-theme='light'] .connections-page .remote-state.online) { color: var(--smart-success); }
:global([data-theme='light'] .connections-page .remote-state.offline),
:global([data-theme='light'] .connections-page .capability-warning) { color: var(--smart-warning); }
:global([data-theme='light'] .connections-page :is(.session-tree, .server-inspector, .terminal-workspace, .connection-status)) { background: var(--smart-surface); border-color: var(--smart-border-strong); }
:global([data-theme='light'] .connections-page :is(h1, h2, h3, strong, label, [role='alert'])) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page :is(.section-kicker, .eyebrow, small, .workspace-name span, .workspace-empty p, .inspector-empty, .session-empty p)) { color: var(--smart-muted); }
:global([data-theme='light'] .connections-page :is(.icon-action, .new-session, .session-search input, .create-session input, .create-session select, .create-session textarea, .runtime-tabs button, .toolbar-actions button, .form-actions button)) { background: var(--smart-surface); color: var(--smart-text); border-color: var(--smart-border-strong); }
:global([data-theme='light'] .connections-page :is(.panel-heading, .subsection-heading, .workspace-toolbar, .connections-header, .workspace-empty, .inspector-section)) { border-color: var(--smart-border); }
:global([data-theme='light'] .connections-page .session-row.selected) { background: var(--smart-primary-soft); border-color: var(--smart-primary-strong); }
.connections-page {
  display: grid;
  gap: 18px;
  padding-bottom: 28px;
  color: #dce5e9;
}

.operations-workspace {
  display: grid;
  min-height: min(660px, calc(100vh - 190px));
  grid-template-columns: 236px minmax(0, 1fr) 250px;
  border: 1px solid #18222d;
  background: #080e14;
}
.operations-workspace.session-tree-hidden { grid-template-columns: minmax(0, 1fr) 250px; }
.operations-workspace.server-inspector-hidden { grid-template-columns: 236px minmax(0, 1fr); }
.operations-workspace.session-tree-hidden.server-inspector-hidden { grid-template-columns: minmax(0, 1fr); }
.operations-workspace.session-tree-hidden .session-tree { display: none; }
.operations-workspace.server-inspector-hidden .server-inspector { display: none; }

@media (max-width: 1180px) {
  .operations-workspace {
    grid-template-columns: 210px minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .operations-workspace {
    display: flex;
    min-height: 0;
    flex-direction: column;
  }
}
</style>
