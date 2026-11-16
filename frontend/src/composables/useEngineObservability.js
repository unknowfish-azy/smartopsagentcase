/**
 * 引擎可观测大屏取数 composable（T39）。
 *
 * 三态：loading → live / offline
 *   - live    接口 200 且 engines 为数组
 *   - offline 401/503/网络错误/空数据
 *
 * 铁律：本页主题是"真数据"，**不提供 demo 态、不自动 fallback**。
 * 接口失败一律 offline 空态 + 重试；缺字段显示 —，不补默认值。
 */
import { computed, ref } from 'vue'
import { getEngineSnapshot, getEngineEventStream } from '../api/engineObservability'

const POLL_MS = 30_000

// axios response → .data = ApiResponse{code,message,data} → .data.data = 业务体。
// 兼容后端直接返回业务体的情况（如某些 mock）。
function unwrap(resp) {
  const outer = resp?.data ?? resp
  if (outer && typeof outer === 'object' && 'code' in outer && 'data' in outer) {
    return outer.data
  }
  return outer
}

export function useEngineObservability() {
  const state = ref('loading') // loading | live | offline
  const snapshot = ref(null)
  const errorReason = ref('')
  const selectedEngine = ref(null)
  const events = ref([])
  const eventLoading = ref(false)

  let pollTimer = null
  let inflight = null

  async function fetchSnapshot() {
    if (inflight) return inflight
    inflight = (async () => {
      try {
        const resp = await getEngineSnapshot()
        const body = unwrap(resp)
        if (!body || !Array.isArray(body.engines)) {
          setOffline('快照数据为空')
          return
        }
        snapshot.value = body
        state.value = 'live'
        errorReason.value = ''
        // 保持选中项：优先沿用，否则选第一条非 NOT_RUN
        if (!selectedEngine.value || !body.engines.some(e => e.id === selectedEngine.value)) {
          const first = body.engines.find(e => e.status !== 'NOT_RUN') || body.engines[0]
          if (first) selectedEngine.value = first.id
        }
        if (selectedEngine.value) await fetchEvents(selectedEngine.value)
      } catch (err) {
        setOffline(err?.message || '网络错误')
      } finally {
        inflight = null
      }
    })()
    return inflight
  }

  async function fetchEvents(engineId) {
    if (!engineId) return
    eventLoading.value = true
    try {
      const resp = await getEngineEventStream(engineId, 50)
      const body = unwrap(resp)
      events.value = Array.isArray(body?.events) ? body.events : []
    } catch {
      // 事件流失败不拖垮快照：仅清空事件，不伪造
      events.value = []
    } finally {
      eventLoading.value = false
    }
  }

  function setOffline(reason) {
    state.value = 'offline'
    errorReason.value = reason
    snapshot.value = null
    events.value = []
  }

  function selectEngine(id) {
    selectedEngine.value = id
    fetchEvents(id)
  }

  function startPolling() {
    stopPolling()
    pollTimer = window.setInterval(fetchSnapshot, POLL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function dispose() {
    stopPolling()
  }

  const engines = computed(() => snapshot.value?.engines || [])
  const selected = computed(() => engines.value.find(e => e.id === selectedEngine.value) || null)
  const generatedAtText = computed(() => {
    if (!snapshot.value?.generatedAt) return '—'
    try {
      return new Date(snapshot.value.generatedAt * 1000).toLocaleTimeString('zh-CN', { hour12: false })
    } catch { return '—' }
  })

  return {
    state, snapshot, errorReason, engines, selected, selectedEngine,
    events, eventLoading, generatedAtText,
    fetchSnapshot, selectEngine, startPolling, stopPolling, dispose
  }
}
