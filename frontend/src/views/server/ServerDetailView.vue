<template>
  <div class="detail-page">

    <!-- 顶部 -->
    <div class="page-header">

      <div class="header-left">

        <el-button
            circle
            @click="goBack"
        >
          <el-icon>
            <ArrowLeft />
          </el-icon>
        </el-button>

        <div>

          <h1>
            {{ server?.name || '服务器详情' }}
          </h1>

          <p>
            {{ server?.host || '-' }}
            :
            {{ server?.port || '-' }}
          </p>

        </div>

      </div>


      <div class="header-right">

        <el-button
            :loading="loading"
            @click="loadData"
        >
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>

        <ServerStatusTag
            v-if="server"
            :status="server.status"
        />

      </div>

    </div>


    <!-- 基本信息 -->
    <el-card
        class="info-card"
        shadow="never"
    >

      <template #header>
        <div class="card-title">
          基本信息
        </div>
      </template>


      <el-descriptions
          :column="3"
          border
      >

        <el-descriptions-item
            label="服务器名称"
        >
          {{ server?.name || '-' }}
        </el-descriptions-item>


        <el-descriptions-item
            label="主机地址"
        >
          {{ server?.host || '-' }}
        </el-descriptions-item>


        <el-descriptions-item
            label="SSH端口"
        >
          {{ server?.port || '-' }}
        </el-descriptions-item>


        <el-descriptions-item
            label="操作系统"
        >
          {{ server?.os || '-' }}
        </el-descriptions-item>


        <el-descriptions-item
            label="服务器状态"
        >
          <ServerStatusTag
              v-if="server"
              :status="server.status"
          />
          <span v-else>-</span>
        </el-descriptions-item>


        <el-descriptions-item
            label="创建时间"
        >
          {{ formatDate(server?.createdAt) }}
        </el-descriptions-item>


        <el-descriptions-item
            label="更新时间"
        >
          {{ formatDate(server?.updatedAt) }}
        </el-descriptions-item>


        <el-descriptions-item
            label="说明"
            :span="2"
        >
          {{ server?.description || '-' }}
        </el-descriptions-item>

      </el-descriptions>

    </el-card>


    <!-- 当前指标 -->
    <div class="section-title">
      <div>
        <h2>实时资源指标</h2>
        <span>
          {{ metricTimeText }}
        </span>
      </div>

      <el-tag
          v-if="metric"
          :type="metricTagType"
      >
        {{ metricStatusText }}
      </el-tag>
    </div>


    <div class="metric-grid">

      <!-- CPU -->
      <el-card
          class="metric-card"
          shadow="never"
      >

        <div class="metric-header">
          <span>CPU使用率</span>
          <span class="metric-icon">CPU</span>
        </div>

        <div class="metric-value">
          {{ formatPercent(metric?.cpuUsage) }}
        </div>

        <el-progress
            :percentage="
            normalizePercentage(
              metric?.cpuUsage
            )
          "
            :status="
            getProgressStatus(
              metric?.cpuUsage
            )
          "
            :show-text="false"
        />

        <div class="metric-footer">
          {{ getMetricLevel(metric?.cpuUsage) }}
        </div>

      </el-card>


      <!-- Memory -->
      <el-card
          class="metric-card"
          shadow="never"
      >

        <div class="metric-header">
          <span>内存使用率</span>
          <span class="metric-icon">MEM</span>
        </div>

        <div class="metric-value">
          {{ formatPercent(metric?.memoryUsage) }}
        </div>

        <el-progress
            :percentage="
            normalizePercentage(
              metric?.memoryUsage
            )
          "
            :status="
            getProgressStatus(
              metric?.memoryUsage
            )
          "
            :show-text="false"
        />

        <div class="metric-footer">
          {{ getMetricLevel(metric?.memoryUsage) }}
        </div>

      </el-card>


      <!-- Disk -->
      <el-card
          class="metric-card"
          shadow="never"
      >

        <div class="metric-header">
          <span>磁盘使用率</span>
          <span class="metric-icon">DISK</span>
        </div>

        <div class="metric-value">
          {{ formatPercent(metric?.diskUsage) }}
        </div>

        <el-progress
            :percentage="
            normalizePercentage(
              metric?.diskUsage
            )
          "
            :status="
            getProgressStatus(
              metric?.diskUsage
            )
          "
            :show-text="false"
        />

        <div class="metric-footer">
          {{ getMetricLevel(metric?.diskUsage) }}
        </div>

      </el-card>


      <!-- Load -->
      <el-card
          class="metric-card"
          shadow="never"
      >

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
          采集时间：
          {{ formatDate(metric?.collectedAt) }}
        </div>

      </el-card>

    </div>


    <!-- 网络 -->
    <el-card
        class="network-card"
        shadow="never"
    >

      <template #header>

        <div class="card-title">
          网络流量
        </div>

      </template>


      <div class="network-grid">

        <div class="network-item">

          <div class="network-label">
            ↓ 网络入流量
          </div>

          <div class="network-value">
            {{ formatNumber(metric?.networkIn) }}
          </div>

          <div class="network-unit">
            MB/s
          </div>

        </div>


        <div class="network-item">

          <div class="network-label">
            ↑ 网络出流量
          </div>

          <div class="network-value">
            {{ formatNumber(metric?.networkOut) }}
          </div>

          <div class="network-unit">
            MB/s
          </div>

        </div>

      </div>

    </el-card>


    <!-- 历史指标 -->
    <el-card
        class="history-card"
        shadow="never"
    >

      <template #header>

        <div class="history-header">

          <div>
            <span class="card-title">
              监控历史
            </span>

            <span class="history-count">
              最近 {{ metrics.length }} 条
            </span>
          </div>

          <el-button
              link
              :loading="metricsLoading"
              @click="loadMetrics"
          >
            <el-icon>
              <Refresh />
            </el-icon>
            刷新
          </el-button>

        </div>

      </template>


      <el-table
          v-loading="metricsLoading"
          :data="metrics"
          stripe
          border
          empty-text="暂无监控数据"
      >

        <el-table-column
            label="采集时间"
            width="190"
        >
          <template #default="{ row }">
            {{ formatDate(row.collectedAt) }}
          </template>
        </el-table-column>


        <el-table-column
            label="CPU"
            width="150"
        >
          <template #default="{ row }">

            <span
                :class="
                metricNumberClass(
                  row.cpuUsage
                )
              "
            >
              {{ formatPercent(row.cpuUsage) }}
            </span>

          </template>
        </el-table-column>


        <el-table-column
            label="内存"
            width="150"
        >
          <template #default="{ row }">

            <span
                :class="
                metricNumberClass(
                  row.memoryUsage
                )
              "
            >
              {{ formatPercent(row.memoryUsage) }}
            </span>

          </template>
        </el-table-column>


        <el-table-column
            label="磁盘"
            width="150"
        >
          <template #default="{ row }">

            <span
                :class="
                metricNumberClass(
                  row.diskUsage
                )
              "
            >
              {{ formatPercent(row.diskUsage) }}
            </span>

          </template>
        </el-table-column>


        <el-table-column
            prop="loadAverage"
            label="Load"
            width="120"
        />


        <el-table-column
            label="状态"
            width="120"
        >

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

  </div>
</template>


<script setup>

import {
  computed,
  onMounted,
  onBeforeUnmount,
  ref
} from 'vue'

import {
  useRoute,
  useRouter
} from 'vue-router'

import { ElMessage } from 'element-plus/es/components/message/index.mjs'

import {
  ArrowLeft,
  Refresh
} from '@element-plus/icons-vue'

import {
  getServer
} from '../../api/server'

import {
  getLatestMetric,
  getMetricList
} from '../../api/metric'

import ServerStatusTag
  from '../../components/server/ServerStatusTag.vue'


const route = useRoute()

const router = useRouter()


const serverId =
    route.params.id


const server = ref(null)

const metric = ref(null)

const metrics = ref([])

const loading = ref(false)

const metricsLoading = ref(false)

let timer = null


/* ===================================
   当前指标状态
   =================================== */

const metricTagType = computed(() => {

  if (!metric.value) {
    return 'info'
  }

  switch (metric.value.status) {

    case 'NORMAL':
      return 'success'

    case 'WARNING':
      return 'warning'

    case 'CRITICAL':
      return 'danger'

    default:
      return 'info'
  }
})


const metricStatusText = computed(() => {

  if (!metric.value) {
    return '暂无数据'
  }

  switch (metric.value.status) {

    case 'NORMAL':
      return '运行正常'

    case 'WARNING':
      return '需要关注'

    case 'CRITICAL':
      return '严重异常'

    default:
      return '未知'
  }
})


const metricTimeText = computed(() => {

  if (!metric.value?.collectedAt) {
    return '暂无采集数据'
  }

  return `最后采集：
    ${formatDate(metric.value.collectedAt)}`
})


/* ===================================
   加载服务器详情
   =================================== */

async function loadServer() {

  const result =
      await getServer(serverId)

  server.value =
      result.data
}


/* ===================================
   加载最新指标
   =================================== */

async function loadLatestMetric() {

  try {

    const result =
        await getLatestMetric(serverId)

    metric.value =
        result.data

  } catch (error) {

    /*
     * 当前还没有监控数据时，
     * 页面仍然可以正常显示。
     */
    metric.value = null
  }
}


/* ===================================
   加载历史
   =================================== */

async function loadMetrics() {

  metricsLoading.value = true

  try {

    const result =
        await getMetricList(
            serverId
        )

    metrics.value =
        result.data || []

  } catch (error) {

    ElMessage.error(
        error.message ||
        '监控历史加载失败'
    )

  } finally {

    metricsLoading.value = false
  }
}


/* ===================================
   总加载
   =================================== */

async function loadData() {

  loading.value = true

  try {

    await Promise.all([
      loadServer(),
      loadLatestMetric()
    ])

    await loadMetrics()

  } catch (error) {

    ElMessage.error(
        error.message ||
        '服务器详情加载失败'
    )

  } finally {

    loading.value = false
  }
}


/* ===================================
   自动刷新
   =================================== */

function startAutoRefresh() {

  stopAutoRefresh()

  timer = window.setInterval(
      async () => {

        await Promise.all([
          loadLatestMetric(),
          loadMetrics()
        ])

      },
      10000
  )
}


function stopAutoRefresh() {

  if (timer) {

    window.clearInterval(
        timer
    )

    timer = null
  }
}


/* ===================================
   百分比
   =================================== */

function normalizePercentage(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return 0
  }

  const number =
      Number(value)

  if (Number.isNaN(number)) {
    return 0
  }

  return Math.min(
      100,
      Math.max(
          0,
          number
      )
  )
}


/* ===================================
   进度条状态
   =================================== */

function getProgressStatus(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return undefined
  }

  const number =
      Number(value)

  if (number >= 90) {
    return 'exception'
  }

  if (number >= 80) {
    return 'warning'
  }

  return 'success'
}


/* ===================================
   指标等级
   =================================== */

function getMetricLevel(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return '暂无数据'
  }

  const number =
      Number(value)

  if (number >= 90) {
    return '严重异常'
  }

  if (number >= 80) {
    return '需要关注'
  }

  return '运行正常'
}


/* ===================================
   指标显示
   =================================== */

function formatPercent(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return '-'
  }

  return `${Number(value).toFixed(1)}%`
}


function formatNumber(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return '-'
  }

  return Number(value).toFixed(2)
}


/* ===================================
   日期
   =================================== */

function formatDate(value) {

  if (!value) {
    return '-'
  }

  return new Date(value)
      .toLocaleString(
          'zh-CN'
      )
}


/* ===================================
   指标颜色
   =================================== */

function metricNumberClass(value) {

  if (
      value === null ||
      value === undefined
  ) {
    return ''
  }

  const number =
      Number(value)

  if (number >= 90) {
    return 'metric-critical'
  }

  if (number >= 80) {
    return 'metric-warning'
  }

  return 'metric-normal'
}


/* ===================================
   状态
   =================================== */

function metricStatusLabel(status) {

  switch (status) {

    case 'NORMAL':
      return '正常'

    case 'WARNING':
      return '告警'

    case 'CRITICAL':
      return '严重'

    default:
      return '未知'
  }
}


/* ===================================
   返回
   =================================== */

function goBack() {

  router.push('/servers')
}


onMounted(
    async () => {

      await loadData()

      startAutoRefresh()

    }
)


onBeforeUnmount(
    () => {

      stopAutoRefresh()

    }
)

</script>


<style scoped>

.detail-page {
  width: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-left h1 {
  margin: 0 0 6px;
  font-size: 26px;
}

.header-left p {
  margin: 0;
  color: var(--smart-muted);
  font-family:
      "Consolas",
      "Courier New",
      monospace;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-card {
  margin-bottom: 28px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

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
  grid-template-columns:
    repeat(4, minmax(0, 1fr));

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

.network-card {
  margin-bottom: 20px;
}

.network-grid {
  display: grid;
  grid-template-columns:
    repeat(2, 1fr);

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

.history-card {
  margin-bottom: 20px;
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

@media (max-width: 1100px) {

  .metric-grid {
    grid-template-columns:
      repeat(2, 1fr);
  }

}

@media (max-width: 700px) {

  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .header-right {
    width: 100%;
    justify-content: flex-end;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .network-grid {
    grid-template-columns: 1fr;
  }

}

</style>