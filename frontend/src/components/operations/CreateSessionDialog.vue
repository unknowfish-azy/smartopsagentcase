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
  color: var(--smart-muted);
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
  background: color-mix(in srgb, var(--smart-bg) 78%, transparent);
}

.create-session {
  width: min(100%, 500px);
  padding: 24px;
  border: 1px solid var(--smart-border-strong);
  background: var(--smart-surface);
  box-shadow: 0 22px 70px color-mix(in srgb, var(--smart-bg) 40%, transparent);
}

.create-session h2 {
  margin: 6px 0 24px;
  color: var(--smart-text);
  font-size: 22px;
  font-weight: 550;
}

.create-session label {
  display: grid;
  gap: 7px;
  margin: 15px 0;
  color: var(--smart-muted);
  font-size: 11px;
}

.create-session input,
.create-session select {
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid var(--smart-border-strong);
  border-radius: 3px;
  outline: none;
  background: var(--smart-bg);
  color: var(--smart-text);
  font: 12px var(--font-cn);
  resize: vertical;
}

.create-session input:focus,
.create-session select:focus {
  border-color: var(--smart-primary-strong);
}

.capability-warning {
  padding: 10px;
  border-left: 2px solid var(--ds-semantic-warning);
  color: var(--smart-warning);
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
  border: 1px solid var(--smart-border-strong);
  border-radius: 3px;
  background: var(--smart-surface-raised);
  color: var(--smart-muted);
  font: 11px var(--font-cn);
  cursor: pointer;
}

button:disabled {
  opacity: .42;
  cursor: not-allowed;
}
</style>
