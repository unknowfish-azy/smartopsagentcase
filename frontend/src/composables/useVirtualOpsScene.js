/**
 * useVirtualOpsScene — 虚拟运维场景 / 后果预测的演示态数据源
 *
 * 拓扑与推演全部来自 domain 层的确定性公式：
 *  - 拓扑固定（机柜 / 交换机 / 路由器 / 网关 / 链路 / 空调）；
 *  - 选择一个「失误操作」后，立即计算未来 N 个 tick 的级联后果；
 *  - 时间线可播放、暂停、拖动到任意 tick，3D 与侧栏同步当前帧；
 *  - 接入真实数据时只需替换 predictConsequences 的实现，页面与 3D 组件无需改动。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  DEFAULT_HORIZON,
  OPERATION_CATALOG,
  buildVirtualTopology,
  predictAssetPeaks,
  predictConsequences,
  snapshotAt
} from '../domain/sentinel/virtualOpsScene.js'

export function useVirtualOpsScene(options = {}) {
  const tickMs = Math.max(200, Number(options.tickMs) || 520)
  const horizon = ref(Math.max(8, Math.min(40, Number(options.horizon) || DEFAULT_HORIZON)))

  const topology = buildVirtualTopology()
  const catalog = OPERATION_CATALOG

  const selectedOperationId = ref('')
  const playhead = ref(0)
  const playing = ref(false)
  const selectedAssetId = ref('')

  const prediction = computed(() => {
    if (!selectedOperationId.value) return null
    return predictConsequences(topology, selectedOperationId.value, horizon.value)
  })
  const summary = computed(() => prediction.value?.summary || null)
  const currentSnapshot = computed(() => (
    prediction.value ? snapshotAt(prediction.value.timeline, playhead.value) : null
  ))
  const atEnd = computed(() => (
    !!prediction.value && playhead.value >= prediction.value.timeline.length - 1
  ))
  /**
   * 前向预测：每个资产在整个推演时间窗内的峰值（最坏）状态 + 首次劣化 tick。
   * 供 3D 画布悬浮徽章使用——在操作执行瞬间（T+0）就提示「将恶化到什么程度」，
   * 而非仅随当前帧着色。
   */
  const assetPredictions = computed(() => {
    const p = prediction.value
    if (!p) return []
    return predictAssetPeaks(topology, p.timeline)
  })

  let timer = null
  function stopTimer() {
    if (timer) {
      window.clearInterval(timer)
      timer = null
    }
  }
  function schedule() {
    stopTimer()
    if (typeof window === 'undefined') return
    timer = window.setInterval(() => {
      if (!playing.value || !prediction.value) return
      const last = prediction.value.timeline.length - 1
      if (playhead.value >= last) {
        playing.value = false
        stopTimer()
        return
      }
      playhead.value += 1
    }, tickMs)
  }

  function selectOperation(id) {
    selectedOperationId.value = id || ''
    playhead.value = 0
    selectedAssetId.value = ''
    if (id) {
      playing.value = true
      schedule()
    } else {
      playing.value = false
      stopTimer()
    }
  }
  function play() {
    if (!prediction.value) return
    if (atEnd.value) playhead.value = 0
    playing.value = true
    schedule()
  }
  function pause() {
    playing.value = false
    stopTimer()
  }
  function toggle() {
    playing.value ? pause() : play()
  }
  function reset() {
    playhead.value = 0
    selectedAssetId.value = ''
    if (selectedOperationId.value) {
      playing.value = true
      schedule()
    }
  }
  function seek(tick) {
    if (!prediction.value) return
    const last = prediction.value.timeline.length - 1
    playhead.value = Math.max(0, Math.min(last, Math.floor(Number(tick) || 0)))
  }
  function selectAsset(id) {
    selectedAssetId.value = selectedAssetId.value === id ? '' : id
  }
  /** 调整推演时间窗（tick 数）；变化后 prediction 自动重算，并把播放头钳制到新长度内。 */
  function setHorizon(value) {
    const next = Math.max(8, Math.min(40, Math.floor(Number(value) || 0)))
    if (next !== horizon.value) horizon.value = next
  }

  watch(horizon, () => {
    if (!prediction.value) return
    const last = prediction.value.timeline.length - 1
    if (playhead.value > last) playhead.value = last
  })
  watch(playing, (on) => { if (on) schedule(); else stopTimer() })
  onBeforeUnmount(stopTimer)

  return {
    topology,
    catalog,
    horizon,
    selectedOperationId,
    prediction,
    summary,
    assetPredictions,
    currentSnapshot,
    playhead,
    playing,
    atEnd,
    selectedAssetId,
    selectOperation,
    play,
    pause,
    toggle,
    reset,
    seek,
    selectAsset,
    setHorizon
  }
}
