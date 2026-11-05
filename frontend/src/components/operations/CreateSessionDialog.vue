<template>
  <div v-if="showCreate" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="create-session-title" @click.self="showCreate = false">
    <form class="create-session" @submit.prevent="submitCreate">
      <p class="eyebrow">新建会话</p>
      <h2 id="create-session-title">创建连接</h2>
      <label>会话类型<select v-model="draft.protocol"><option v-for="item in capabilities" :key="item.protocol" :value="item.protocol" :disabled="!canConnect(item)">{{ item.protocol }} · {{ capabilityLabelZh(item) }}</option></select></label>
      <label>会话名称<input v-model="draft.name" required placeholder="prod-web-01" /></label>
      <label>主机<input v-model="draft.host" required placeholder="10.0.0.10" /></label>
      <label>端口<input v-model.number="draft.port" type="number" min="1" max="65535" required /></label>
      <label>用户名<input v-model="draft.username" required placeholder="operator" /></label>
      <p v-if="draft.protocol !== 'SSH' && draft.protocol !== 'SFTP'" class="capability-warning">{{ draft.protocol }} 需要本地桥接</p>
      <div class="form-actions"><button type="button" @click="showCreate = false">取消</button><button type="submit" :disabled="!canSubmit">保存会话</button></div>
    </form>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { canConnect } from '../../api/operations.ts'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'

const {
  showCreate,
  draft,
  capabilities,
  canSubmit,
  capabilityLabelZh,
  submitCreate
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

.create-session label {
  display: grid;
  gap: 7px;
  margin: 15px 0;
  color: #a8b5bc;
  font-size: 11px;
}

.create-session input,
.create-session select {
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid #263541;
  border-radius: 3px;
  outline: none;
  background: #080e14;
  color: #e2eaed;
  font: 12px var(--font-cn);
  resize: vertical;
}

.create-session input:focus,
.create-session select:focus {
  border-color: #38bdf8;
}

.capability-warning {
  padding: 10px;
  border-left: 2px solid #f59e0b;
  color: #f4c879;
  font-size: 11px;
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

button:disabled {
  opacity: .42;
  cursor: not-allowed;
}
</style>
