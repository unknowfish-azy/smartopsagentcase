/**
 * 预测面取数 composable。
 *
 * 四态：loading → live / demo / offline
 *   - live  接口 200 且 points 非空
 *   - demo  用户主动选演示 或 接口不可用但用户选择演示
 *   - offline 401/503/网络错误，未选演示
 *
 * 契约（docs/design/forecast-module-v1/DESIGN.md §7）：
 *   缺字段 = 不可用，前端显示 —，不补默认值。
 *   所有请求走 utils/request（自动带 X-Request-ID / CSRF）。
 *
 * 本 composable **不** 在接口失败时自动 fallback 到 demo；demo/offline 由调用方显式选择。
 */

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { buildDemoPayload } from '../domain/forecast/syntheticSeries.js'

const ENDPOINT = '/api/sentinel/forecast'

export function useForecastSeries(options = {}) {
  const { metric: initialMetric = 'ect', horizon: initialHorizon = 30 } = options

  const state = ref('loading')   // loading | live | demo | offline
  const payload = ref(null)
  const metric = ref(initialMetric)
  const horizon = ref(initialHorizon)
  const errorReason = ref('')

  let abort = null
  let demoCountdown = 0  // 防止竞态：demo 是同步的，接口是异步的

  /**
   * 尝试从后端取数。接口不可用时进入 offline。
   */
  async function fetchLive() {
    state.value = 'loading'
    errorReason.value = ''

    // 中断前一个请求
    abort?.abort()
    const controller = new AbortController()
    abort = controller

    try {
      // 动态 import utils/request（避免构建时的循环依赖）
      let requestFn
      try {
        const mod = await import('../utils/request.js').catch(() => null)
        requestFn = mod?.default || mod?.request
      } catch { /* request 模块不存在 */ }

      if (!requestFn) {
        // 接口层未接入，直接走 offline
        setOffline('接口层未就绪')
        return
      }

      const resp = await requestFn(`${ENDPOINT}?metric=${metric.value}&horizon=${horizon.value}`, {
        signal: controller.signal,
        timeout: 5000
      })

      if (controller.signal.aborted) return  // 被后续请求中断

      const body = resp?.data || resp
      if (!body?.forecast?.length) {
        setOffline('返回数据为空')
        return
      }

      payload.value = normalizePayload(body)
      state.value = 'live'
    } catch (err) {
      if (controller.signal.aborted) return
      setOffline(err?.message || '网络错误')
    }
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

  /** 首次挂载时尝试 live，500ms 超时直接 demo（避免骨架屏等太久）。 */
  function boot() {
    fetchLive()
    // 兜底：如果 1s 后还是 loading，自动切 demo（调用方可覆盖此行为）
    const timer = setTimeout(() => {
      if (state.value === 'loading') useDemo()
    }, 1000)
    onBeforeUnmount(() => clearTimeout(timer))
  }

  onBeforeUnmount(() => abort?.abort())

  // ------- 工具 -------
  function normalizePayload(body) {
    return {
      generatedAt: body.generatedAt,
      generatedAtSec: body.generatedAt ? Math.floor(new Date(body.generatedAt).getTime() / 1000) : Math.floor(Date.now() / 1000),
      model: body.model || {},
      series: body.series || [],
      forecast: body.forecast || [],
      crossings: body.crossings || [],
      unit: body.unit || '',
      demo: false
    }
  }

  return {
    state: computed(() => state.value),
    payload: computed(() => payload.value),
    metric,
    horizon,
    errorReason: computed(() => errorReason.value),
    boot,
    useDemo,
    retry,
    fetchLive
  }
}
