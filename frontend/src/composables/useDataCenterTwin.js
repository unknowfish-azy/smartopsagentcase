/**
 * useDataCenterTwin — 机房孪生演示态数据源
 *
 * 第一版没有真实传感器与扫描数据，全部由确定性公式按 tick 生成：
 *  - 机柜布局固定（两排 + 冷通道）；
 *  - 每 tick 生成温度/湿度/功率采样与派生告警；
 *  - 机器人沿闭合轨迹匀速巡逻，位置由进度插值；
 *  - 同步延迟模拟包含周期峰值，用来验证 2.5s 预算告警是否可见。
 *
 * 接入真实数据时只需替换本文件的 tick 数据来源，页面与 3D 组件无需改动。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  buildRackLayout,
  deriveAlarms,
  hottestRacks,
  latencyStatus,
  patrolPositionAt,
  patrolProgress,
  robotWaypoints,
  simulateSyncLatency,
  simulateTelemetry,
  twinSummary
} from '../domain/sentinel/dataCenterTwin.js'

export function useDataCenterTwin(options = {}) {
  const tickMs = Math.max(250, Number(options.tickMs) || 1000)
  const lapSeconds = Math.max(10, Number(options.lapSeconds) || 45)

  const layout = ref(buildRackLayout(options.perRow ?? 6, options.rows ?? 2))
  const running = ref(true)
  const tick = ref(0)
  const selectedId = ref('')

  const path = computed(() => robotWaypoints(layout.value))
  const telemetry = computed(() => simulateTelemetry(layout.value, tick.value))
  const latencyMs = computed(() => simulateSyncLatency(tick.value))
  const latency = computed(() => latencyStatus(latencyMs.value))
  const alarms = computed(() => deriveAlarms(telemetry.value))
  const hottest = computed(() => hottestRacks(telemetry.value, 5))
  const robot = computed(() => {
    const elapsed = tick.value * tickMs
    return patrolPositionAt(path.value, patrolProgress(elapsed, lapSeconds))
  })
  const patrolRatio = computed(() => patrolProgress(tick.value * tickMs, lapSeconds))
  const summary = computed(() => twinSummary(telemetry.value, latencyMs.value, alarms.value))
  const heartbeat = computed(() => {
    const route = path.value
    return { waypoints: route.length, lapSeconds, tickMs }
  })

  let timer = null
  function start() {
    if (timer || typeof window === 'undefined') return
    running.value = true
    timer = window.setInterval(() => {
      if (running.value) tick.value += 1
    }, tickMs)
  }
  function stop() {
    if (timer) {
      window.clearInterval(timer)
      timer = null
    }
  }
  function pause() {
    running.value = false
  }
  function resume() {
    running.value = true
  }
  function reset() {
    tick.value = 0
    selectedId.value = ''
    running.value = true
  }
  function select(id) {
    selectedId.value = selectedId.value === id ? '' : id
  }

  start()
  onBeforeUnmount(stop)

  return {
    layout,
    path,
    running,
    tick,
    selectedId,
    telemetry,
    latencyMs,
    latency,
    alarms,
    hottest,
    robot,
    patrolRatio,
    summary,
    heartbeat,
    start,
    stop,
    pause,
    resume,
    reset,
    select
  }
}
