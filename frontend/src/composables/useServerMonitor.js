import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getRuntimeMonitor } from '../api/operations.ts'
import { netRate, pushHistory } from '../components/operations/serverMonitor.js'

/** 真实监控轮询：runtime 在线才轮询，连续 3 次失败自动停（诚实报错，不编数字）。 */
export function useServerMonitor(runtimeIdSource, onlineSource) {
  const INTERVALS = [3000, 5000, 10000]
  const intervalMs = ref(INTERVALS[0])
  const latest = ref(null)
  const prev = ref(null)
  const rate = ref(null)
  const history = ref([])
  const error = ref('')
  const failureCount = ref(0)
  const sampling = ref(false)
  let timer = null

  const failed = computed(() => latest.value?.supported === false)

  async function sample() {
    const runtimeId = runtimeIdSource.value
    if (!runtimeId || sampling.value) return
    sampling.value = true
    try {
      const response = await getRuntimeMonitor(runtimeId)
      const data = response.data?.data || response.data
      if (runtimeIdSource.value !== runtimeId) return
      prev.value = latest.value
      latest.value = data
      rate.value = netRate(prev.value, data)
      history.value = pushHistory(history.value, data)
      if (data?.supported === false) {
        failureCount.value += 1
        error.value = data.reason || '采样失败'
        if (failureCount.value >= 3) stop(`连续采样失败（${data.reason || '未知原因'}），已停止轮询`)
      } else {
        failureCount.value = 0
        error.value = ''
      }
    } catch (caught) {
      if (runtimeIdSource.value !== runtimeId) return
      failureCount.value += 1
      error.value = caught?.message || '采样请求失败'
      if (failureCount.value >= 3) stop(`连续采样失败，已停止轮询`)
    } finally {
      sampling.value = false
    }
  }

  function start() {
    if (timer) return
    error.value = ''
    sample()
    timer = setInterval(sample, intervalMs.value)
  }

  function stop(reason = '') {
    if (timer) { clearInterval(timer); timer = null }
    if (reason) error.value = reason
  }

  function setIntervalValue(value) {
    if (!INTERVALS.includes(value)) return
    intervalMs.value = value
    if (timer) { clearInterval(timer); timer = setInterval(sample, value) }
  }

  function reset() {
    stop()
    latest.value = null
    prev.value = null
    rate.value = null
    history.value = []
    failureCount.value = 0
    error.value = ''
  }

  watch([runtimeIdSource, onlineSource], ([id, online]) => {
    if (id && online) start()
    else reset()
  }, { immediate: true })

  onBeforeUnmount(() => stop())

  return { intervalMs, latest, rate, history, error, failed, sampling, start, stop, setIntervalValue, reset }
}
