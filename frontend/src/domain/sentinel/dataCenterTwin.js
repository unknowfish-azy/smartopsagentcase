/**
 * dataCenterTwin — 云服务器厂房 3D 孪生数据层（纯函数，node:test 可测）
 *
 * 第一版是「虚拟场景演示」：机柜布局、温度/湿度/功率采样、机器人巡逻轨迹
 * 全部由确定性公式生成，不伪造任何真实机房数据，页面上会明确标注演示态。
 *
 * 数据红线：
 *  - 采样值只由 (rackId, t) 决定，同一时刻反复调用结果一致，便于测试与回放；
 *  - 真实场景接管后，只需把 simulateTelemetry 换成扫描/传感器接口，其余分层不动；
 *  - 同步延迟预算 2.5 秒是硬指标，latencyStatus 是唯一判定入口。
 */

/** 端到端同步延迟预算：采集 → 传输 → 渲染上屏，超过即视为不达标。 */
export const LATENCY_BUDGET_MS = 2500
/** 延迟预警水位：超过预算的 60% 提前提示，留出抖动余量。 */
export const LATENCY_WARN_MS = 1500

/** 温度阈值（摄氏度）：机房冷通道常规 18~27，机柜进风超 28 需关注。 */
export const TEMP_THRESHOLDS = Object.freeze({ warn: 28, critical: 32 })
/** 湿度阈值（%RH）：低于 30 易静电、高于 65 易凝露。 */
export const HUMIDITY_THRESHOLDS = Object.freeze({ warn: 65, critical: 75, low: 30 })

export const METRIC_LABELS = Object.freeze({
  temperature: '温度',
  humidity: '湿度',
  power: '功率'
})

/**
 * 确定性伪随机：把字符串与时间片散列成 [0,1)。
 * 不用 Math.random，保证同一 tick 可重放、测试稳定。
 */
export function seededUnit(seedText, tick) {
  let h = 2166136261
  const text = `${seedText}:${tick}`
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 10000) / 10000
}

/**
 * 机柜布局：两排面对面，中间留冷通道。
 * 返回 [{ id, label, row, index, x, z }]，坐标单位为「米」，中心为原点。
 */
export function buildRackLayout(perRow = 6, rows = 2) {
  const safePerRow = Math.max(1, Math.floor(perRow))
  const safeRows = Math.max(1, Math.floor(rows))
  const gapX = 1.6
  const gapZ = 3.2
  const racks = []
  for (let r = 0; r < safeRows; r += 1) {
    for (let i = 0; i < safePerRow; i += 1) {
      const label = `R${r + 1}-${String(i + 1).padStart(2, '0')}`
      racks.push({
        id: label,
        label,
        row: r,
        index: i,
        x: (i - (safePerRow - 1) / 2) * gapX,
        z: r === 0 ? -gapZ / 2 : gapZ / 2
      })
    }
  }
  return racks
}

/** 单指标分级；未知指标按数值越大越危险处理。 */
export function metricLevel(metric, value) {
  const v = Number(value)
  if (!Number.isFinite(v)) return 'unknown'
  if (metric === 'temperature') {
    if (v >= TEMP_THRESHOLDS.critical) return 'critical'
    if (v >= TEMP_THRESHOLDS.warn) return 'warn'
    return 'ok'
  }
  if (metric === 'humidity') {
    if (v >= HUMIDITY_THRESHOLDS.critical) return 'critical'
    if (v >= HUMIDITY_THRESHOLDS.warn) return 'warn'
    if (v < HUMIDITY_THRESHOLDS.low) return 'warn'
    return 'ok'
  }
  return 'ok'
}

/**
 * 生成一个 tick 的全量采样。
 * @param {Array} layout buildRackLayout 的输出
 * @param {number} tick 秒级时间片；同一 tick 输出恒定
 * @returns {Array<{id,label,temperature,humidity,power,level}>}
 */
export function simulateTelemetry(layout, tick) {
  const t = Math.max(0, Math.floor(Number(tick) || 0))
  return (layout || []).map((rack, index) => {
    const noise = seededUnit(rack.id, t)
    /* 相位错开，避免所有机柜同时升温；周期 90 秒，肉眼可辨但不跳动。 */
    const wave = Math.sin(((t / 90) * Math.PI * 2) + index * 0.7)
    const temperature = Number((23.4 + wave * 2.6 + noise * 4.2 + (rack.row === 1 ? 0.8 : 0)).toFixed(1))
    const humidity = Number((46 + Math.cos(((t / 120) * Math.PI * 2) + index) * 8 + noise * 6).toFixed(1))
    const power = Number((3.6 + noise * 2.4 + (wave + 1) * 0.9).toFixed(2))
    return {
      id: rack.id,
      label: rack.label,
      temperature,
      humidity,
      power,
      level: metricLevel('temperature', temperature)
    }
  })
}

/** 巡逻闭合轨迹：沿两排机柜外侧绕行一圈，作为机器人巡航路线。 */
export function robotWaypoints(layout) {
  const racks = layout || []
  if (!racks.length) {
    return [
      { x: -4, z: -3 },
      { x: 4, z: -3 },
      { x: 4, z: 3 },
      { x: -4, z: 3 }
    ]
  }
  const xs = racks.map(r => r.x)
  const zs = racks.map(r => r.z)
  const minX = Math.min(...xs) - 1.2
  const maxX = Math.max(...xs) + 1.2
  const minZ = Math.min(...zs) - 1.2
  const maxZ = Math.max(...zs) + 1.2
  /* 顺时针绕行：先沿前排在冷通道侧，再绕到后排。 */
  return [
    { x: minX, z: minZ },
    { x: maxX, z: minZ },
    { x: maxX, z: 0 },
    { x: maxX, z: maxZ },
    { x: minX, z: maxZ },
    { x: minX, z: 0 }
  ]
}

/** 轨迹总长度，用于把「进度」换算成匀速移动。 */
export function pathLength(points) {
  const list = points || []
  let total = 0
  for (let i = 0; i < list.length; i += 1) {
    const a = list[i]
    const b = list[(i + 1) % list.length]
    total += Math.hypot(b.x - a.x, b.z - a.z)
  }
  return total
}

/**
 * 按进度取轨迹上的位置（0~1 循环），返回 { x, z, heading }。
 * heading 为朝向弧度，供 3D 机器人模型转向。
 */
export function patrolPositionAt(points, progress) {
  const list = points || []
  if (!list.length) return { x: 0, z: 0, heading: 0 }
  const total = pathLength(list)
  if (total <= 0) return { x: list[0].x, z: list[0].z, heading: 0 }
  const normalized = ((Number(progress) || 0) % 1 + 1) % 1
  let remaining = normalized * total
  for (let i = 0; i < list.length; i += 1) {
    const a = list[i]
    const b = list[(i + 1) % list.length]
    const segment = Math.hypot(b.x - a.x, b.z - a.z)
    if (remaining <= segment || i === list.length - 1) {
      const ratio = segment > 0 ? Math.min(1, remaining / segment) : 0
      return {
        x: Number((a.x + (b.x - a.x) * ratio).toFixed(3)),
        z: Number((a.z + (b.z - a.z) * ratio).toFixed(3)),
        heading: Number(Math.atan2(b.x - a.x, b.z - a.z).toFixed(3))
      }
    }
    remaining -= segment
  }
  const first = list[0]
  return { x: first.x, z: first.z, heading: 0 }
}

/** 巡逻进度：默认 45 秒一圈。 */
export function patrolProgress(elapsedMs, lapSeconds = 45) {
  const lap = Math.max(1, Number(lapSeconds) || 45)
  const ms = Math.max(0, Number(elapsedMs) || 0)
  return (ms / 1000 / lap) % 1
}

/**
 * 模拟一段端到端同步延迟（毫秒）。
 * 平台期在 300~900ms，每 20 个 tick 制造一次 2.6s 峰值用于演示预算告警，
 * 便于在虚拟场景阶段就验证 2.5 秒红线是否可见、可告警。
 */
export function simulateSyncLatency(tick) {
  const t = Math.max(0, Math.floor(Number(tick) || 0))
  const base = 320 + seededUnit('latency', t) * 480
  if (t > 0 && t % 20 === 0) return 2600
  if (t % 20 === 19) return Number((1900 + seededUnit('latency-peak', t) * 380).toFixed(0))
  return Number(base.toFixed(0))
}

/** 延迟分级：ok / warn / breach（超过 2.5s 预算）。 */
export function latencyStatus(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value < 0) return { level: 'unknown', label: '未知' }
  if (value > LATENCY_BUDGET_MS) return { level: 'breach', label: '超出预算' }
  if (value > LATENCY_WARN_MS) return { level: 'warn', label: '接近预算' }
  return { level: 'ok', label: '达标' }
}

/**
 * 从采样派生实时预警：只上报真实越界项，正常机柜不生成噪音。
 * @returns {Array<{id, rackId, metric, label, value, level, text}>}
 */
export function deriveAlarms(telemetry) {
  const alarms = []
  for (const rack of telemetry || []) {
    const tempLevel = metricLevel('temperature', rack.temperature)
    if (tempLevel === 'warn' || tempLevel === 'critical') {
      alarms.push({
        id: `${rack.id}:temperature`,
        rackId: rack.id,
        metric: 'temperature',
        label: METRIC_LABELS.temperature,
        value: rack.temperature,
        level: tempLevel,
        text: `${rack.label} 进风温度 ${rack.temperature}°C`
      })
    }
    const humidityLevel = metricLevel('humidity', rack.humidity)
    if (humidityLevel !== 'ok') {
      alarms.push({
        id: `${rack.id}:humidity`,
        rackId: rack.id,
        metric: 'humidity',
        label: METRIC_LABELS.humidity,
        value: rack.humidity,
        level: humidityLevel,
        text: `${rack.label} 湿度 ${rack.humidity}%RH`
      })
    }
  }
  /* 严重项优先；同级按指标优先级（温度 > 湿度）再看数值——
     不同指标的量纲不可直接比大小，先比指标再比数值才有意义。 */
  const weight = { critical: 0, warn: 1, ok: 2, unknown: 3 }
  const metricOrder = { temperature: 0, humidity: 1 }
  return alarms.sort((a, b) => (
    weight[a.level] - weight[b.level]
    || (metricOrder[a.metric] ?? 9) - (metricOrder[b.metric] ?? 9)
    || b.value - a.value
  ))
}

/** 机柜按温度倒序取前 n，侧栏「温度排行」用。 */
export function hottestRacks(telemetry, limit = 5) {
  return [...(telemetry || [])]
    .sort((a, b) => b.temperature - a.temperature)
    .slice(0, Math.max(0, Math.floor(limit)))
}

/** 底部信息条汇总。 */
export function twinSummary(telemetry, latencyMs, alarms) {
  const list = telemetry || []
  const avg = list.length
    ? Number((list.reduce((sum, r) => sum + r.temperature, 0) / list.length).toFixed(1))
    : null
  const totalPower = Number(list.reduce((sum, r) => sum + (r.power || 0), 0).toFixed(1))
  return {
    racks: list.length,
    avgTemperature: avg,
    totalPower,
    alarms: (alarms || []).length,
    latencyMs: Number(latencyMs) || 0,
    latencyLevel: latencyStatus(latencyMs).level
  }
}
