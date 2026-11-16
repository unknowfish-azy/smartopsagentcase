<template>
  <section class="tunnel-workspace" aria-labelledby="tunnel-title">
    <header class="tunnel-header">
      <div>
        <p class="eyebrow">NETWORK / TUNNELS</p>
        <h2 id="tunnel-title">SSH TUNNEL CONTROL</h2>
        <p class="subline">Explicit forwarding routes for the selected online SSH runtime.</p>
      </div>
      <div class="tunnel-runtime" :class="{ online: runtimeOnline }">
        <span class="status-dot" aria-hidden="true"></span>
        <span>{{ runtimeOnline ? 'RUNTIME ONLINE' : 'NO RUNTIME' }}</span>
      </div>
    </header>

    <div class="tunnel-table-wrap">
      <table class="tunnel-table">
        <thead>
          <tr>
            <th>NAME</th><th>TYPE</th><th>LISTEN</th><th>TARGET</th><th>SSH SESSION</th><th>STATUS</th><th>SETTINGS</th><th>ACTION</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!tunnels.length">
            <td colspan="8" class="empty-row">No forwarding routes configured. Create a route only after an SSH runtime is online.</td>
          </tr>
          <tr v-for="tunnel in tunnels" :key="tunnel.id">
            <td><strong>{{ tunnel.name }}</strong></td>
            <td><span class="type-label">{{ tunnelTypeLabel(tunnel.type) }}</span></td>
            <td class="mono">{{ tunnel.listenAddress }}:{{ tunnel.listenPort }}</td>
            <td class="mono">{{ tunnel.targetHost }}:{{ tunnel.targetPort }}</td>
            <td>{{ tunnel.sessionName }}</td>
            <td><span class="state" :class="tunnel.status.toLowerCase()">{{ tunnelStatusLabel(tunnel.status) }}</span></td>
            <td><span class="settings">{{ tunnel.autoReconnect ? 'AUTO RECONNECT' : 'MANUAL' }}</span></td>
            <td class="row-actions"><button class="table-action" type="button" @click="$emit(tunnel.status === 'RUNNING' ? 'stop' : 'start', tunnel)">{{ tunnel.status === 'RUNNING' ? 'STOP' : 'START' }}</button><button class="table-action" type="button" @click="$emit('edit', tunnel)">EDIT</button><button class="table-action danger" type="button" @click="$emit('remove', tunnel)">DELETE</button><button class="table-action" type="button" @click="$emit('logs', tunnel)">LOG</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="tunnel-actions">
      <button class="primary-action" type="button" :disabled="!runtimeOnline" @click="$emit('create')">NEW TUNNEL</button>
      <button type="button" :disabled="!selectedTunnel || !canStartTunnel(selectedTunnel)" @click="$emit('start', selectedTunnel)">START SELECTED</button>
      <button type="button" :disabled="!selectedTunnel || selectedTunnel.status !== 'RUNNING'" @click="$emit('stop', selectedTunnel)">STOP SELECTED</button>
      <span class="capability-note">SSH LOCAL FORWARD · OTHER MODES REQUIRE BRIDGE SUPPORT</span>
    </footer>

    <div v-if="tunnelForm" class="tunnel-overlay" @click.self="$emit('cancel-tunnel')">
      <form class="tunnel-form" role="dialog" aria-modal="true" aria-label="隧道配置" @submit.prevent="$emit('submit-tunnel', { ...formDraft })">        <h3>{{ tunnelForm.mode === 'edit' ? '编辑隧道' : '新建隧道' }}</h3>
        <label>名称<input v-model="formDraft.name" type="text" required /></label>
        <label>目标主机<input v-model="formDraft.targetHost" type="text" required placeholder="从 SSH 服务器侧访问" /></label>
        <label>目标端口<input v-model.number="formDraft.targetPort" type="number" min="1" max="65535" required /></label>
        <label>本地监听端口<input v-model.number="formDraft.listenPort" type="number" min="1" max="65535" required /></label>
        <p class="form-note">本地转发：访问 127.0.0.1:{{ formDraft.listenPort }} 的流量将经当前 SSH 会话转发到 {{ formDraft.targetHost || '?' }}:{{ formDraft.targetPort }}。</p>
        <div class="form-actions">
          <button type="submit" class="primary-action">{{ tunnelForm.mode === 'edit' ? '保存' : '创建' }}</button>
          <button type="button" @click="$emit('cancel-tunnel')">取消</button>
        </div>
      </form>
    </div>

    <div v-if="logsFor" class="tunnel-overlay" @click.self="$emit('close-logs')">
      <div class="logs-drawer" role="dialog" aria-modal="true" :aria-label="`${logsFor.name} 日志`">
        <header><strong>{{ logsFor.name }} · 日志</strong><button type="button" @click="$emit('close-logs')">关闭</button></header>
        <pre>{{ (logsFor.logs || []).join('\n') || '暂无日志' }}</pre>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { canStartTunnel, tunnelStatusLabel, tunnelTypeLabel } from './tunnelWorkspace.js'

const props = defineProps({
  tunnels: { type: Array, default: () => [] },
  runtimeOnline: { type: Boolean, default: false },
  selectedTunnel: { type: Object, default: null },
  tunnelForm: { type: Object, default: null },
  logsFor: { type: Object, default: null },
})
defineEmits(['create', 'start', 'stop', 'edit', 'remove', 'logs', 'submit-tunnel', 'cancel-tunnel', 'close-logs'])

// 表单草稿：对话框打开时复制一份，避免未保存修改污染原状态
const formDraft = ref({ name: '', targetHost: '', targetPort: 5432, listenPort: 15432 })
watch(() => props.tunnelForm, form => { formDraft.value = { ...(form?.draft || {}) } }, { immediate: true })
</script>

<style scoped>
.tunnel-workspace { background: var(--smart-surface); border: 1px solid var(--smart-border); }
.tunnel-header { display: flex; justify-content: space-between; gap: 24px; padding: 22px 24px; border-bottom: 1px solid var(--smart-border); }
.eyebrow { margin: 0 0 9px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .14em; }
h2 { margin: 0; color: var(--smart-text); font: 400 22px var(--font-display); letter-spacing: .02em; }
.subline { margin: 8px 0 0; color: var(--smart-muted); font: 12px var(--font-mono); }
.tunnel-runtime { display: flex; align-items: center; gap: 8px; align-self: start; color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .08em; white-space: nowrap; }
.tunnel-runtime.online { color: var(--smart-primary-strong); }.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 12px currentColor; }
.tunnel-table-wrap { overflow-x: auto; }.tunnel-table { width: 100%; min-width: 780px; border-collapse: collapse; }
th, td { padding: 14px 15px; border-bottom: 1px solid var(--smart-border); text-align: left; white-space: nowrap; }
th { color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .11em; }.tunnel-table td { color: var(--smart-text); font: 12px var(--font-mono); }.tunnel-table td strong { color: var(--smart-text); font-weight: 500; }
.type-label { color: var(--smart-muted); font-size: 10px; }.mono { color: var(--smart-primary-strong) !important; }.empty-row { padding: 48px 20px; color: var(--smart-muted) !important; text-align: center !important; white-space: normal !important; }
.settings { color: var(--smart-muted); font-size: 9px; letter-spacing: .08em; }.row-actions { display: flex; gap: 5px; }.danger { color: var(--ds-semantic-danger); }
.state { font-size: 10px; letter-spacing: .08em; }.state.running { color: var(--smart-primary-strong); }.state.stopped { color: var(--smart-muted); }.state.error { color: var(--ds-semantic-danger); }.state.starting { color: var(--ds-semantic-warning); }
button { min-height: 40px; padding: 0 12px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-text); font: 10px var(--font-mono); letter-spacing: .08em; cursor: pointer; } button:hover:not(:disabled), button:focus-visible { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); outline: 2px solid color-mix(in srgb, var(--smart-primary-strong) 32%, transparent); outline-offset: 2px; } button:disabled { cursor: not-allowed; opacity: .38; }
.table-action { min-height: 30px; padding: 0 9px; }.primary-action { border-color: var(--smart-primary); color: var(--smart-primary-strong); }.tunnel-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 16px 24px; }.capability-note { margin-left: auto; color: var(--smart-muted); font: 9px var(--font-mono); letter-spacing: .08em; }
@media (max-width: 720px) { .tunnel-header { display: block; }.tunnel-runtime { margin-top: 16px; }.capability-note { width: 100%; margin-left: 0; line-height: 1.5; } }

.tunnel-overlay { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; background: rgba(2,6,10,.62); }
.tunnel-form { display: grid; gap: 10px; width: min(420px, calc(100vw - 40px)); padding: 20px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface-raised); }
.tunnel-form h3 { margin: 0; color: var(--smart-text); font-size: 14px; font-weight: 550; }
.tunnel-form label { display: grid; gap: 4px; color: var(--smart-muted); font-size: 11px; }
.tunnel-form input { padding: 7px 9px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); color: var(--smart-text); font: 12px var(--font-mono); outline: none; }
.tunnel-form input:focus { border-color: var(--smart-primary-strong); }
.form-note { margin: 0; color: var(--smart-muted); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; }
.form-actions { display: flex; gap: 8px; }
.form-actions button { min-height: 32px; padding: 0 14px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-text); font: 12px var(--font-cn); cursor: pointer; }
.logs-drawer { display: grid; gap: 10px; width: min(560px, calc(100vw - 40px)); max-height: 70vh; padding: 16px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface-raised); }
.logs-drawer header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.logs-drawer strong { color: var(--smart-text); font-size: 13px; }
.logs-drawer button { min-height: 28px; padding: 0 12px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-muted); font: 11px var(--font-cn); cursor: pointer; }
.logs-drawer pre { max-height: 48vh; margin: 0; padding: 10px; overflow: auto; border: 1px solid var(--smart-border); background: var(--smart-surface); color: var(--smart-muted); font: 11px var(--font-mono); white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
