/**
 * 断面对比分析面取数 composable（照 useForecastSeries 四态模式）。
 *
 * 四态：loading → live / demo / offline
 *   - live  接口 200 且 series 非空
 *   - demo  用户主动选演示 或 loading 超时自动切（与预测面一致）
 *   - offline 接口不可用且未选演示；显示 — 与"查看演示数据集"按钮
 *
 * 本 composable **不**在接口失败时自动 fallback 到 demo（失败 → offline）。
 */

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { buildSectionDemoPayload } from '../domain/sections/sectionSeries.js'

const ENDPOINT = '/api/sentinel/sections'

export function useSectionSeries(options = {}) {
  const { selected: initialSelected = ['ect', 'egt', 'oilp'], windowSec: initialWindow = 120 } = options

  const state = ref('loading')   // loading | live | demo | offline
  const payload = ref(null)
  const selected = ref([...initialSelected])
  const windowSec = ref(initialWindow)
  const errorReason = ref('')

  let abort = null

  async function fetchLive() {
    state.value = 'loading'
    errorReason.value = ''

    abort?.abort()
    const controller = new AbortController()
    abort = controller

    try {
      let requestFn
      try {
        const mod = await import('../utils/request.js').catch(() => null)
        requestFn = mod?.default || mod?.request
      } catch { /* request 模块不存在 */ }

      if (!requestFn) {
        setOffline('接口层未就绪')
        return
      }

      const qs = `keys=${selected.value.join(',')}&window=${windowSec.value}`
      const resp = await requestFn(`${ENDPOINT}?${qs}`, {
        signal: controller.signal,
        timeout: 5000
      })

      if (controller.signal.aborted) return

      const body = resp?.data || resp
      if (!body?.series || !Object.keys(body.series).length) {
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
    payload.value = buildSectionDemoPayload(selected.value, windowSec.value)
    state.value = 'demo'
    errorReason.value = ''
  }

  function retry() {
    fetchLive()
  }

  /** 选中集或窗口变化：demo 同步重建，其余重新取数。 */
  watch([selected, windowSec], () => {
    if (state.value === 'demo') {
      useDemo()
    } else if (state.value !== 'offline') {
      fetchLive()
    }
  }, { deep: true })

  /** 首次挂载尝试 live；1s 仍 loading 自动切 demo（与预测面一致）。 */
  function boot() {
    fetchLive()
    const timer = setTimeout(() => {
      if (state.value === 'loading') useDemo()
    }, 1000)
    onBeforeUnmount(() => clearTimeout(timer))
  }

  onBeforeUnmount(() => abort?.abort())

  function normalizePayload(body) {
    return {
      generatedAt: body.generatedAt,
      generatedAtSec: body.generatedAt ? Math.floor(new Date(body.generatedAt).getTime() / 1000) : Math.floor(Date.now() / 1000),
      windowSec: body.windowSec || windowSec.value,
      series: body.series || {},
      spread: body.spread || [],
      snapshots: body.snapshots || [],
      demo: false
    }
  }

  return {
    state: computed(() => state.value),
    payload: computed(() => payload.value),
    selected,
    windowSec,
    errorReason: computed(() => errorReason.value),
    boot,
    useDemo,
    retry,
    fetchLive
  }
}
