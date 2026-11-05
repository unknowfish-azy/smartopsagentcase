<template>
  <el-card class="history-card" shadow="never">
    <template #header>
      <div class="history-header">
        <div>
          <span class="card-title">监控历史</span>
          <span class="history-count">最近 {{ metrics.length }} 条</span>
        </div>
        <el-button link :loading="loading" @click="emit('refresh')">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </template>

    <el-table
        v-loading="loading"
        :data="metrics"
        stripe
        border
        empty-text="暂无监控数据"
    >
      <el-table-column label="采集时间" width="190">
        <template #default="{ row }">
          {{ formatDate(row.collectedAt) }}
        </template>
      </el-table-column>
      <el-table-column label="CPU" width="150">
        <template #default="{ row }">
          <span :class="metricNumberClass(row.cpuUsage)">
            {{ formatPercent(row.cpuUsage) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="内存" width="150">
        <template #default="{ row }">
          <span :class="metricNumberClass(row.memoryUsage)">
            {{ formatPercent(row.memoryUsage) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="磁盘" width="150">
        <template #default="{ row }">
          <span :class="metricNumberClass(row.diskUsage)">
            {{ formatPercent(row.diskUsage) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="loadAverage" label="Load" width="120" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag
              :type="
                row.status === 'NORMAL'
                  ? 'success'
                  : row.status === 'WARNING'
                    ? 'warning'
                    : 'danger'
              "
          >
            {{ metricStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { Refresh } from '@element-plus/icons-vue'
import {
  formatDate,
  formatPercent,
  metricNumberClass,
  metricStatusLabel
} from './serverMetricFormat.js'

defineProps({
  metrics: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['refresh'])
</script>

<style scoped>
.history-card {
  margin-bottom: 20px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-count {
  margin-left: 10px;
  color: var(--smart-muted);
  font-size: 13px;
}

.metric-normal {
  color: var(--smart-success);
  font-weight: 600;
}

.metric-warning {
  color: var(--smart-warning);
  font-weight: 600;
}

.metric-critical {
  color: var(--smart-danger);
  font-weight: 600;
}
</style>
