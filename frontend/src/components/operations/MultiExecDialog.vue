<template>
  <div v-if="showMultiExec" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="command-preview-title">
    <form class="create-session" @submit.prevent="previewCommand">
      <p class="eyebrow">批量执行 / 审批</p>
      <h2 id="command-preview-title">命令预览</h2>
      <label>命令<textarea v-model="multiCommand" rows="3" placeholder="uptime" required></textarea></label>
      <fieldset class="multi-targets"><legend>目标（{{ selectedRuntimeIds.length }}）</legend><label v-for="tab in onlineTabs" :key="tab.runtimeId"><input v-model="selectedRuntimeIds" type="checkbox" :value="tab.runtimeId" /> {{ tab.session.name }}</label></fieldset>
      <p class="host-key-copy">审批后才会发送命令；服务端只返回 SENT，表示已写入终端输入流。</p>
      <div v-if="multiPreview" class="risk-preview">
        <span>风险等级</span>
        <strong :class="multiPreview.risk.toLowerCase()">{{ riskLabel(multiPreview.risk) }}</strong>
        <small>需要 {{ multiPreview.requiredApprovals }} 次确认</small>
      </div>
      <div class="form-actions">
        <button type="button" @click="showMultiExec = false">取消</button>
        <button v-if="!multiPreview" type="submit">查看风险</button>
        <button v-else type="button" @click="approveCommand">{{ multiApprovalStep === 1 ? '进行第二次确认' : '确认并发送' }}</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'

const {
  showMultiExec,
  multiCommand,
  multiPreview,
  selectedRuntimeIds,
  multiApprovalStep,
  onlineTabs,
  riskLabel,
  previewCommand,
  approveCommand
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

.create-session textarea {
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

.create-session textarea:focus {
  border-color: #38bdf8;
}

.host-key-copy {
  color: #a8b5bc;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.risk-preview {
  display: grid;
  gap: 7px;
  margin: 18px 0;
  padding: 12px;
  border: 1px solid #263541;
  border-left: 3px solid #38bdf8;
  background: #0d151d;
}

.risk-preview span,
.risk-preview small {
  color: #a8b5bc;
  font-size: 11px;
}

.risk-preview strong {
  color: #38bdf8;
  font-size: 14px;
}

.risk-preview strong.high,
.risk-preview strong.critical {
  color: #ef4444;
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
