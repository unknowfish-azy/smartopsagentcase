import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getServer } from '../api/server'
import { getLatestMetric, getMetricList } from '../api/metric'
import { formatDate } from '../components/server/detail/serverMetricFormat.js'

export function useServerDetail() {
  const route = useRoute()
  const router = useRouter()

  const serverId = route.params.id

  const server = ref(null)
  const metric = ref(null)
  const metrics = ref([])
  const loading = ref(false)
  const metricsLoading = ref(false)

  let timer = null

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
    return `最后采集：${formatDate(metric.value.collectedAt)}`
  })

  async function loadServer() {
    const result = await getServer(serverId)
    server.value = result.data
  }

  async function loadLatestMetric() {
    try {
      const result = await getLatestMetric(serverId)
      metric.value = result.data
    } catch {
      /*
       * 当前还没有监控数据时，
       * 页面仍然可以正常显示。
       */
      metric.value = null
    }
  }

  async function loadMetrics() {
    metricsLoading.value = true
    try {
      const result = await getMetricList(serverId)
      metrics.value = result.data || []
    } catch (error) {
      ElMessage.error(error.message || '监控历史加载失败')
    } finally {
      metricsLoading.value = false
    }
  }

  async function loadData() {
    loading.value = true
    try {
      await Promise.all([
        loadServer(),
        loadLatestMetric()
      ])
      await loadMetrics()
    } catch (error) {
      ElMessage.error(error.message || '服务器详情加载失败')
    } finally {
      loading.value = false
    }
  }

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
      window.clearInterval(timer)
      timer = null
    }
  }

  function goBack() {
    router.push('/servers')
  }

  onMounted(async () => {
    await loadData()
    startAutoRefresh()
  })

  onBeforeUnmount(() => {
    stopAutoRefresh()
  })

  return {
    server,
    metric,
    metrics,
    loading,
    metricsLoading,
    metricTagType,
    metricStatusText,
    metricTimeText,
    loadData,
    loadMetrics,
    goBack
  }
}
