<template>
  <header class="connections-header">
    <div>
      <p class="eyebrow">OPERATIONS CENTER <span>远程运维</span></p>
      <h1>连接中心</h1>
    </div>
    <div class="connection-status" :class="{ ready: bridgeReady }">
      <span class="status-dot" aria-hidden="true"></span>
      <div>
        <strong>{{ bridgeStatus }}</strong>
        <small>SSH / SFTP · 本地桥接</small>
      </div>
    </div>
  </header>
</template>

<script setup>
defineProps({
  bridgeReady: { type: Boolean, default: false },
  bridgeStatus: { type: String, default: '' }
})
</script>

<style scoped>
.connections-header {
  display: flex;
  min-height: 66px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0 14px;
  border-bottom: 1px solid #18222d;
}

.eyebrow {
  margin: 0;
  color: #8c9ba5;
  font: 10px var(--font-mono);
  letter-spacing: .08em;
}

.eyebrow span {
  margin-left: 8px;
  color: #a8b5bc;
  font-family: var(--font-cn);
  letter-spacing: 0;
}

.connections-header h1 {
  margin: 6px 0 0;
  color: #eef4f6;
  font: 500 22px/1.25 var(--font-cn);
}

.connection-status {
  display: flex;
  min-width: 180px;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #18222d;
  background: #0b1118;
}

.status-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #f59e0b;
}

.connection-status.ready .status-dot {
  background: #22c55e;
}

.connection-status strong,
.connection-status small {
  display: block;
}

.connection-status strong {
  color: #dce5e9;
  font-size: 12px;
  font-weight: 550;
}

.connection-status small {
  margin-top: 3px;
  color: #8c9ba5;
  font-size: 11px;
}

@media (max-width: 700px) {
  .connections-header {
    align-items: flex-start;
  }

  .connection-status {
    min-width: 0;
    padding: 8px;
  }

  .connection-status small {
    display: none;
  }
}
</style>
