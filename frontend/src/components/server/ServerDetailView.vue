<template>
  <div v-loading="loading">

    <div class="page-header">

      <div>
        <h1>
          {{ server?.name || '服务器详情' }}
        </h1>

        <p>
          {{ server?.host }}
        </p>
      </div>

      <el-button @click="goBack">
        返回
      </el-button>

    </div>

    <el-card
        v-if="server"
        shadow="never"
    >

      <el-descriptions
          title="基本信息"
          :column="2"
          border
      >

        <el-descriptions-item label="名称">
          {{ server.name }}
        </el-descriptions-item>

        <el-descriptions-item label="主机">
          {{ server.host }}
        </el-descriptions-item>

        <el-descriptions-item label="端口">
          {{ server.port }}
        </el-descriptions-item>

        <el-descriptions-item label="操作系统">
          {{ server.os || '-' }}
        </el-descriptions-item>

        <el-descriptions-item label="状态">
          <ServerStatusTag
              :status="server.status"
          />
        </el-descriptions-item>

        <el-descriptions-item label="说明">
          {{ server.description || '-' }}
        </el-descriptions-item>

      </el-descriptions>

    </el-card>

    <el-card
        v-if="metric"
        class="metric-card"
        shadow="never"
    >

      <template #header>
        最新监控指标
      </template>

      <div class="metric-grid">

        <div class="metric-item">
          <span>CPU</span>
          <strong>
            {{ metric.cpuUsage }}%
          </strong>
        </div>

        <div class="metric-item">
          <span>内存</span>
          <strong>
            {{ metric.memoryUsage }}%
          </strong>
        </div>

        <div class="metric-item">
          <span>磁盘</span>
          <strong>
            {{ metric.diskUsage }}%
          </strong>
        </div>

        <div class="metric-item">
          <span>负载</span>
          <strong>
            {{ metric.loadAverage ?? '-' }}
          </strong>
        </div>

      </div>

    </el-card>

  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  getServer
} from '../../api/server'

import {
  getLatestMetric
} from '../../api/metric'

import ServerStatusTag
  from '../../components/server/ServerStatusTag.vue'

const route = useRoute()
const router = useRouter()

const server = ref(null)
const metric = ref(null)
const loading = ref(false)

async function loadData() {

  loading.value = true

  try {

    const [
      serverResult,
      metricResult
    ] = await Promise.all([
      getServer(route.params.id),
      getLatestMetric(route.params.id)
          .catch(() => null)
    ])

    server.value = serverResult.data

    metric.value =
        metricResult?.data || null

  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/servers')
}

onMounted(loadData)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 6px;
}

.page-header p {
  color: var(--smart-muted);
  margin: 0;
}

.metric-card {
  margin-top: 20px;
}

.metric-grid {
  display: grid;
  grid-template-columns:
    repeat(4, 1fr);
  gap: 16px;
}

.metric-item {
  padding: 20px;
  background: var(--smart-bg);
  border-radius: 10px;
}

.metric-item span {
  display: block;
  color: var(--smart-muted);
  margin-bottom: 10px;
}

.metric-item strong {
  font-size: 28px;
}
</style>