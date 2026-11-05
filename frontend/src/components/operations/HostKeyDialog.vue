<template>
  <div v-if="hostKey" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="host-key-title">
    <section class="create-session host-key-dialog">
      <p class="eyebrow">主机密钥验证</p>
      <h2 id="host-key-title">确认远程身份</h2>
      <p class="host-key-copy">{{ selectedSession?.host }}:{{ selectedSession?.port }} 返回了新的 {{ hostKey.algorithm }} 主机密钥</p>
      <code>{{ hostKey.fingerprint }}</code>
      <div class="form-actions">
        <button type="button" @click="hostKey = null">取消</button>
        <button type="button" @click="hostKey = null; connectSelected('TRUST_ONCE')">仅信任本次</button>
        <button type="button" @click="hostKey = null; connectSelected('TRUST_AND_SAVE')">信任并保存</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'

const {
  hostKey,
  selectedSession,
  connectSelected
} = inject(CONNECTIONS_WORKSPACE_KEY)
</script>

<style scoped>
.eyebrow {
  margin: 0;
  color: #8c9ba5;
  font: 10px var(--font-mono);
  letter-spacing: .08em;
}

.create-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(3, 7, 13, .78);
}

.create-session {
  width: min(100%, 500px);
  padding: 24px;
  border: 1px solid #263541;
  background: #0b1118;
  box-shadow: 0 22px 70px rgba(0, 0, 0, .4);
}

.create-session h2 {
  margin: 6px 0 24px;
  color: #eef4f6;
  font-size: 22px;
  font-weight: 550;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 22px;
}

.form-actions button {
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid #263541;
  border-radius: 3px;
  background: #0d151d;
  color: #b9c7cd;
  font: 11px var(--font-cn);
  cursor: pointer;
}

.host-key-copy {
  color: #a8b5bc;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.host-key-dialog code {
  display: block;
  margin: 18px 0;
  padding: 12px;
  border: 1px solid #263541;
  color: #c9d5da;
  font: 11px var(--font-mono);
  overflow-wrap: anywhere;
}
</style>
