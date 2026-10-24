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
  </section>
</template>

<script setup>
import { canStartTunnel, tunnelStatusLabel, tunnelTypeLabel } from './tunnelWorkspace.js'

defineProps({
  tunnels: { type: Array, default: () => [] },
  runtimeOnline: { type: Boolean, default: false },
  selectedTunnel: { type: Object, default: null },
})
defineEmits(['create', 'start', 'stop', 'edit', 'remove', 'logs'])
</script>

<style scoped>
.tunnel-workspace { background: #071018; border: 1px solid rgba(159, 190, 207, .18); }
.tunnel-header { display: flex; justify-content: space-between; gap: 24px; padding: 22px 24px; border-bottom: 1px solid rgba(159, 190, 207, .18); }
.eyebrow { margin: 0 0 9px; color: #7ad7f5; font: 10px var(--font-mono); letter-spacing: .14em; }
h2 { margin: 0; color: #e8f2f7; font: 400 22px var(--font-display); letter-spacing: .02em; }
.subline { margin: 8px 0 0; color: #92a6b5; font: 12px var(--font-mono); }
.tunnel-runtime { display: flex; align-items: center; gap: 8px; align-self: start; color: #b98c96; font: 10px var(--font-mono); letter-spacing: .08em; white-space: nowrap; }
.tunnel-runtime.online { color: #7ad7f5; }.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 12px currentColor; }
.tunnel-table-wrap { overflow-x: auto; }.tunnel-table { width: 100%; min-width: 780px; border-collapse: collapse; }
th, td { padding: 14px 15px; border-bottom: 1px solid rgba(159, 190, 207, .12); text-align: left; white-space: nowrap; }
th { color: #92a6b5; font: 10px var(--font-mono); letter-spacing: .11em; }.tunnel-table td { color: #cfe0e8; font: 12px var(--font-mono); }.tunnel-table td strong { color: #e8f2f7; font-weight: 500; }
.type-label { color: #92a6b5; font-size: 10px; }.mono { color: #7ad7f5 !important; }.empty-row { padding: 48px 20px; color: #92a6b5 !important; text-align: center !important; white-space: normal !important; }
.settings { color: #92a6b5; font-size: 9px; letter-spacing: .08em; }.row-actions { display: flex; gap: 5px; }.danger { color: #ef9da9; }
.state { font-size: 10px; letter-spacing: .08em; }.state.running { color: #7ad7f5; }.state.stopped { color: #92a6b5; }.state.error { color: #ef9da9; }.state.starting { color: #e4c37a; }
button { min-height: 40px; padding: 0 12px; border: 1px solid rgba(159, 190, 207, .24); background: transparent; color: #cfe0e8; font: 10px var(--font-mono); letter-spacing: .08em; cursor: pointer; } button:hover:not(:disabled), button:focus-visible { border-color: #7ad7f5; color: #7ad7f5; outline: 2px solid rgba(122, 215, 245, .32); outline-offset: 2px; } button:disabled { cursor: not-allowed; opacity: .38; }
.table-action { min-height: 30px; padding: 0 9px; }.primary-action { border-color: #2496ed; color: #7ad7f5; }.tunnel-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 16px 24px; }.capability-note { margin-left: auto; color: #92a6b5; font: 9px var(--font-mono); letter-spacing: .08em; }
@media (max-width: 720px) { .tunnel-header { display: block; }.tunnel-runtime { margin-top: 16px; }.capability-note { width: 100%; margin-left: 0; line-height: 1.5; } }
</style>
