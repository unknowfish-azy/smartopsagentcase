<template>
  <el-card class="network-card" shadow="never">
    <template #header>
      <div class="card-title">网络流量</div>
    </template>
    <div class="network-grid">
      <div class="network-item">
        <div class="network-label">↓ 网络入流量</div>
        <div class="network-value">
          {{ formatNumber(metric?.networkIn) }}
        </div>
        <div class="network-unit">MB/s</div>
      </div>
      <div class="network-item">
        <div class="network-label">↑ 网络出流量</div>
        <div class="network-value">
          {{ formatNumber(metric?.networkOut) }}
        </div>
        <div class="network-unit">MB/s</div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { formatNumber } from './serverMetricFormat.js'

defineProps({
  metric: {
    type: Object,
    default: null
  }
})
</script>

<style scoped>
.network-card {
  margin-bottom: 20px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.network-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.network-item {
  padding: 20px;
  border-radius: 10px;
  background: var(--smart-bg);
}

.network-label {
  color: var(--smart-muted);
  font-size: 14px;
}

.network-value {
  display: inline-block;
  margin-top: 10px;
  font-size: 28px;
  font-weight: 700;
}

.network-unit {
  display: inline-block;
  margin-left: 5px;
  color: var(--smart-muted);
}

@media (max-width: 700px) {
  .network-grid {
    grid-template-columns: 1fr;
  }
}
</style>
