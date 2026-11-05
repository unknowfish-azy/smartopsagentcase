<template>
  <div>
    <div class="section-title">
      <div>
        <h2>实时资源指标</h2>
        <span>{{ timeText }}</span>
      </div>
      <el-tag v-if="metric" :type="tagType">
        {{ statusText }}
      </el-tag>
    </div>

    <div class="metric-grid">
      <!-- CPU -->
      <el-card class="metric-card" shadow="never">
        <div class="metric-header">
          <span>CPU使用率</span>
          <span class="metric-icon">CPU</span>
        </div>
        <div class="metric-value">
          {{ formatPercent(metric?.cpuUsage) }}
        </div>
        <el-progress
            :percentage="normalizePercentage(metric?.cpuUsage)"
            :status="getProgressStatus(metric?.cpuUsage)"
            :show-text="false"
        />
        <div class="metric-footer">
          {{ getMetricLevel(metric?.cpuUsage) }}
        </div>
      </el-card>

      <!-- Memory -->
      <el-card class="metric-card" shadow="never">
        <div class="metric-header">
          <span>内存使用率</span>
          <span class="metric-icon">MEM</span>
        </div>
        <div class="metric-value">
          {{ formatPercent(metric?.memoryUsage) }}
        </div>
        <el-progress
            :percentage="normalizePercentage(metric?.memoryUsage)"
            :status="getProgressStatus(metric?.memoryUsage)"
            :show-text="false"
        />
        <div class="metric-footer">
          {{ getMetricLevel(metric?.memoryUsage) }}
        </div>
      </el-card>

      <!-- Disk -->
      <el-card class="metric-card" shadow="never">
        <div class="metric-header">
          <span>磁盘使用率</span>
          <span class="metric-icon">DISK</span>
        </div>
        <div class="metric-value">
          {{ formatPercent(metric?.diskUsage) }}
        </div>
        <el-progress
            :percentage="normalizePercentage(metric?.diskUsage)"
            :status="getProgressStatus(metric?.diskUsage)"
            :show-text="false"
        />
        <div class="metric-footer">
          {{ getMetricLevel(metric?.diskUsage) }}
        </div>
      </el-card>

      <!-- Load -->
      <el-card class="metric-card" shadow="never">
        <div class="metric-header">
          <span>系统负载</span>
          <span class="metric-icon">LOAD</span>
        </div>
        <div class="metric-value load-value">
          {{ metric?.loadAverage ?? '-' }}
        </div>
        <div class="load-description">
          Linux Load Average
        </div>
        <div class="metric-footer">
          采集时间：{{ formatDate(metric?.collectedAt) }}
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import {
  formatDate,
  formatPercent,
  getMetricLevel,
  getProgressStatus,
  normalizePercentage
} from './serverMetricFormat.js'

defineProps({
  metric: {
    type: Object,
    default: null
  },
  tagType: {
    type: String,
    default: 'info'
  },
  statusText: {
    type: String,
    default: '暂无数据'
  },
  timeText: {
    type: String,
    default: '暂无采集数据'
  }
})
</script>

<style scoped>
.section-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title h2 {
  margin: 0 0 5px;
  font-size: 18px;
}

.section-title span {
  color: var(--smart-muted);
  font-size: 13px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.metric-card {
  min-height: 190px;
}

.metric-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--smart-muted);
  font-size: 14px;
}

.metric-icon {
  padding: 4px 8px;
  border-radius: 5px;
  background: var(--smart-bg);
  font-size: 11px;
  font-weight: 600;
}

.metric-value {
  margin: 20px 0 16px;
  font-size: 32px;
  font-weight: 700;
}

.load-value {
  margin-bottom: 8px;
}

.metric-footer {
  margin-top: 12px;
  color: var(--smart-muted);
  font-size: 13px;
}

.load-description {
  color: var(--smart-muted);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 700px) {
  .metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
