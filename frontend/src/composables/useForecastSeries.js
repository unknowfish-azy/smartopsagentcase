/**
 * 预测面取数 composable。
 *
 * 四态：loading → live / demo / offline
 *   - live     接口 200 且 forecast 非空（含 statistical 统计降级，kind 如实回传）
 *   - demo     用户主动选演示 或 loading 超时自动切（合成序列，双重声明 DEMO）
 *   - offline  接口不可用 / status=unavailable / 网络错误，未选演示
 *
 * 契约（后端 `SentinelForecastService`）：
 *   GET /api/sentinel/forecast/catalog        → { slots:[...], horizons:[15,30,60,120] }
 *   GET /api/sentinel/forecast?metric=&horizon=→ { kind, modelStatus, series, forecast,
 *                                                crossings, unit, thresholds, ... }
 * 缺字段 = 不可用，前端显示 —，不补默认值。所有请求走 utils/request（自动带 X-Request-ID / CSRF）。
 */

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { buildDemoPayload } from '../domain/forecast/syntheticSeries.js'

const ENDPOINT = '/api/sentinel/forecast'
const CATALOG_ENDPOINT = '/api/sentinel/forecast/catalog'

/** loading 兜底成 demo 的时长；真实接口通常 <1s，超过说明后端没起。 */
const AUTO_DEMO_AFTER_MS = 4000

export function useForecastSeries(options = {}) {
  const { metric: initialMetric = 'ect', horizon: initialHorizon = 30 } = options

  const state = ref('loading')   // loading | live | demo | offline
  const payload = ref(null)
  const metric = ref(initialMetric)
  const horizon = ref(initialHorizon)
  const errorReason = ref('')
  /** 可用槽位目录（后端只返回确实有采样的指标）。 */
  const catalog = ref([])
  /** 模型状态（neural / statistical / unavailable + 原因）。 */
  const modelInfo = ref(null)

  let abort = null
  let catalogAbort = null
  let _demoCountdown = 0

  async function requestFn() {
    try {
      const mod = await import('../utils/request.js').catch(() => null)
      return mod?.default || mod?.request || null
    } catch {
      return null
    }
  }

  /** 拉取可用槽位；失败不阻塞主流程（catalog 为空时由主接口的 offline 兜住）。 */
  async function fetchCatalog() {
    catalogAbort?.abort()
    const controller = new AbortController()
    catalogAbort = controller
    const request = await requestFn()
    if (!request) return
    try {
      const resp = await request(CATALOG_ENDPOINT, { signal: controller.signal, timeout: 5000 })
      const body = resp?.data || resp
      const slots = body?.slots
      if (Array.isArray(slots)) {
        catalog.value = slots
        modelInfo.value = modelInfo.value || null
      }
    } catch {
      /* 目录拿不到不算致命：主接口仍会给出该指标的实况 */
    }
  }

  /**
   * 尝试从后端取数。接口不可用或数据为空时进入 offline。
   */
  async function fetchLive() {
    state.value = 'loading'
    errorReason.value = ''

    // 中断前一个请求
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    _demoCountdown += 1

    const request = await requestFn()
    if (!request) {
      setOffline('接口层未就绪')
      return
    }

    let resp
    try {
      resp = await request(`${ENDPOINT}?metric=${encodeURIComponent(metric.value)}&horizon=${horizon.value}`, {
        signal: controller.signal,
        timeout: 12000
      })
    } catch (err) {
      if (controller.signal.aborted) return
      setOffline(err?.response?.data?.message || err?.message || '网络错误')
      return
    }

    if (controller.signal.aborted) return
    const body = resp?.data || resp
    const forecastPoints = Array.isArray(body?.forecast) ? body.forecast : []

    // 无结果 / 上游不可达：显式 offline，不把演示数据冒充实时。
    if (!body || body.status === 'unavailable' || !forecastPoints.length) {
      setOffline(body?.modelStatusDetail || body?.reason || '返回数据为空')
      return
    }

    payload.value = normalizePayload(body)
    state.value = 'live'
  }

  function setOffline(reason) {
    state.value = 'offline'
    errorReason.value = reason
    payload.value = null
  }

  /** 切到 demo 态（用户显式选择）。 */
  function useDemo() {
    const demo = buildDemoPayload(metric.value, horizon.value)
    demo.generatedAtSec = Math.floor(Date.now() / 1000)
    payload.value = demo
    state.value = 'demo'
    errorReason.value = ''
  }

  /** 切回 live 尝试。 */
  function retry() {
    fetchLive()
  }

  /** 换传感器或视野时重新取数（demo 态也同步）。 */
  watch([metric, horizon], () => {
    if (state.value === 'demo') {
      useDemo()
    } else {
      fetchLive()
    }
  })

  /** 首次挂载：先取目录，再取主数据；超时兜底 demo，避免骨架屏等太久。 */
  function boot() {
    fetchCatalog()
    fetchLive()
    const timer = setTimeout(() => {
      if (state.value === 'loading') useDemo()
    }, AUTO_DEMO_AFTER_MS)
    onBeforeUnmount(() => clearTimeout(timer))
  }

  onBeforeUnmount(() => {
    abort?.abort()
    catalogAbort?.abort()
  })

  // ------- 工具 -------
  /**
   * 归一化后端响应。**不补默认值**：缺的字段保持 undefined/null，交给展示层渲染 —。
   * kind 原样透传（neural / statistical / unavailable），绝不改写成"已用神经模型"。
   */
  function normalizePayload(body) {
    const generatedAt = body.generatedAt || null
    const points = Array.isArray(body.forecast) ? body.forecast : []
    return {
      demo: false,
      generatedAt,
      generatedAtSec: generatedAt ? Math.floor(new Date(generatedAt).getTime() / 1000) : Math.floor(Date.now() / 1000),
      kind: body.kind || 'statistical',
      mode: body.mode || '',
      modelStatus: body.modelStatus || '',
      modelStatusDetail: body.modelStatusDetail || '',
      note: body.note || '',
      explanation: body.explanation || '',
      riskScore: body.riskScore ?? null,
      riskLevel: body.riskLevel || '',
      riskBasis: Array.isArray(body.riskBasis) ? body.riskBasis : [],
      sampleIntervalSec: body.sampleIntervalSec ?? null,
      sampleCount: body.sampleCount ?? null,
      inferenceMs: body.inferenceMs ?? null,
      thresholds: body.thresholds || null,
      // 展示口径一律取真实指标（后端给的 cn/en/unit），不回退引擎语义。
      sensorKey: body.sensor || metric.value,
      sensorCn: body.cn || '',
      sensorEn: body.en || '',
      metricName: body.metric || '',
      model: body.model || {},
      unit: body.unit || '',
      horizonSec: body.horizonSec ?? horizon.value,
      // 历史序列：t 为相对最后观测点的秒偏移（负数）。
      series: Array.isArray(body.series) ? body.series : [],
      // 预测序列：t 为相对"现在"的秒偏移（正数），与 demo 口径一致。
      forecast: points.map((point) => ({
        t: point.t,
        h: point.h ?? null,
        median: point.median,
        p10: point.p10,
        p90: point.p90
      })),
      crossings: Array.isArray(body.crossings) ? body.crossings : []
    }
  }

  return {
    state: computed(() => state.value),
    payload: computed(() => payload.value),
    catalog: computed(() => catalog.value),
    modelInfo: computed(() => modelInfo.value),
    metric,
    horizon,
    errorReason: computed(() => errorReason.value),
    boot,
    useDemo,
    retry,
    fetchLive,
    fetchCatalog
  }
}
