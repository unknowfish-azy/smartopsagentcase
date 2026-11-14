/**
 * 预测面 · 演示数据生成器。
 *
 * 确定性合成序列（正弦叠加 + 慢漂移 + 平滑噪声），同参数同输出。
 * 所有序列带 { demo: true } 标记，页面必须双重声明（DEMO 角标 + 页脚）。
 * 本模块只在前端离线 / 用户主动选演示时启用；**绝不**作为接口兜底。
 *
 * 口径对齐 docs/design/forecast-module-v1/index.html 的 SENSORS 与生成函数。
 */

export const SENSORS = Object.freeze([
  Object.freeze({
    key: 'ect', cn: '冷却液温度', en: 'ECT', unit: '°C',
    base: 89, amp: 3.6, period: 96, phase: 0.4,
    warn: 96, crit: 101, digits: 1
  }),
  Object.freeze({
    key: 'rpm', cn: '曲轴转速', en: 'RPM', unit: 'rpm',
    base: 2140, amp: 180, period: 41, phase: 2.1,
    warn: 2450, crit: 2600, digits: 0
  }),
  Object.freeze({
    key: 'egt', cn: '排气温度', en: 'EGT', unit: '°C',
    base: 545, amp: 34, period: 63, phase: 1.2,
    warn: 600, crit: 640, digits: 0
  }),
  Object.freeze({
    key: 'oilp', cn: '机油压力', en: 'OILP', unit: 'bar',
    base: 3.4, amp: 0.34, period: 77, phase: 3.4,
    warn: 2.6, crit: 2.2, digits: 2, low: true
  }),
  Object.freeze({
    key: 'iat', cn: '进气温度', en: 'IAT', unit: '°C',
    base: 36, amp: 4.2, period: 128, phase: 0.9,
    warn: 48, crit: 54, digits: 1
  }),
  Object.freeze({
    key: 'vbat', cn: '电池电压', en: 'VBAT', unit: 'V',
    base: 13.6, amp: 0.42, period: 88, phase: 5.0,
    warn: 12.9, crit: 12.4, digits: 2, low: true
  })
])

export function getSensor(key) {
  return SENSORS.find(s => s.key === key) || SENSORS[0]
}

/** 多层正弦叠加的平滑噪声。 */
function noise(t, seed) {
  return (
    Math.sin(t * 1.7 + seed * 1.3) * 0.5 +
    Math.sin(t * 0.61 + seed * 2.7) * 0.3 +
    Math.sin(t * 0.23 + seed * 4.1) * 0.2
  )
}

/** 某传感器在绝对时间 t 的"实测"值（合成）。 */
export function valueAt(sensor, t) {
  const drift = Math.sin(t / 420 + sensor.phase) * sensor.amp * 0.9
  const wave = Math.sin((t / sensor.period) * Math.PI * 2 + sensor.phase) * sensor.amp
  const ripple = Math.sin((t / (sensor.period * 0.37)) * Math.PI * 2 + sensor.phase * 2) * sensor.amp * 0.18
  return sensor.base + drift + wave + ripple + noise(t * 0.7, sensor.base) * sensor.amp * 0.16
}

/** 某传感器在 t 处的瞬时斜率（中心差分）。 */
export function slopeAt(sensor, t) {
  return (valueAt(sensor, t + 1) - valueAt(sensor, t - 1)) / 2
}

/**
 * 预测：当前值 + 阻尼趋势 + 向均值收敛。
 * 不确定性带宽：sigma = amp * 0.16 + √h * amp * 0.045，p10/p90 ≈ ±1.64σ。
 */
export function forecastAt(sensor, t, h, modelBias = 0) {
  const v0 = valueAt(sensor, t)
  const slope = slopeAt(sensor, t)
  const damp = 1 - Math.exp(-h / 18)
  const pull = (sensor.base - v0) * 0.12 * (1 - Math.exp(-h / 40))
  return v0 + slope * damp * h * 0.55 + pull + modelBias
}

export function bandAt(sensor, t, h) {
  const sigma = sensor.amp * 0.16 + Math.sqrt(h) * sensor.amp * 0.045
  return sigma * 1.64
}

/**
 * 生成历史序列（从 t0 到 t1，步长 stepSec）。
 * @param {object} sensor
 * @param {number} t0  起始绝对时间（秒）
 * @param {number} t1  结束绝对时间（秒）
 * @param {number} [stepSec=2]
 * @returns {Array<{t:number, v:number}>}
 */
export function historySeries(sensor, t0, t1, stepSec = 2) {
  const pts = []
  for (let t = t0; t <= t1; t += stepSec) {
    pts.push({ t: Math.round(t), v: valueAt(sensor, t) })
  }
  return pts
}

/**
 * 生成预测序列（从 t 到 t+horizon，步长 stepSec）。
 * @returns {{ median: Array<{t, v}>, p10: Array<{t, v}>, p90: Array<{t, v}> }}
 */
export function forecastSeries(sensor, t, horizon, stepSec = 2, modelBias = 0) {
  const median = []
  const p10 = []
  const p90 = []
  for (let h = stepSec; h <= horizon; h += stepSec) {
    const m = forecastAt(sensor, t, h, modelBias)
    const b = bandAt(sensor, t, h)
    median.push({ t: Math.round(t + h), v: m })
    p10.push({ t: Math.round(t + h), v: m - b })
    p90.push({ t: Math.round(t + h), v: m + b })
  }
  return { median, p10, p90 }
}

/**
 * 计算预测越界事件。
 * @returns {Array<{kind:'warn'|'crit', h:number, value:number, threshold:number, confidence:number}>}
 */
export function crossingEvents(sensor, t, horizon, stepSec = 2) {
  const events = []
  const isLow = !!sensor.low
  const belowWarn = v => isLow ? v <= sensor.warn : v >= sensor.warn
  const belowCrit = v => isLow ? v <= sensor.crit : v >= sensor.crit

  for (let h = stepSec; h <= horizon; h += stepSec) {
    const m = forecastAt(sensor, t, h)
    const already = events[events.length - 1]
    if (belowCrit(m) && (!already || already.kind !== 'crit')) {
      events.push({
        kind: 'crit',
        h,
        value: m,
        threshold: sensor.crit,
        confidence: Math.min(0.9, Math.max(0.5, 0.9 - h / (4 * horizon)))
      })
    } else if (belowWarn(m) && (!already || already.kind !== 'warn')) {
      events.push({
        kind: 'warn',
        h,
        value: m,
        threshold: sensor.warn,
        confidence: Math.min(0.9, Math.max(0.5, 0.9 - h / (4 * horizon)))
      })
    }
  }
  return events.slice(0, 4)
}

/** 构造整页 demo 数据包（与 §7 接口形状对齐）。 */
export function buildDemoPayload(metricKey = 'ect', horizon = 30, nowOffset = 0) {
  const sensor = getSensor(metricKey)
  const now = Math.round(Date.now() / 1000) + nowOffset

  const history = historySeries(sensor, now - 120, now, 2)
  const fc = forecastSeries(sensor, now, horizon, 2)
  const crossings = crossingEvents(sensor, now, horizon, 2)

  return {
    demo: true,
    generatedAt: new Date(now * 1000).toISOString(),
    model: {
      version: 'v3.2',
      arch: 'MLP+GRU',
      params: 28417,
      metrics: { mae: 1.84, rmse: 2.61, mape: 2.3 },
      trainedAt: new Date((now - 8 * 3600) * 1000).toISOString(),
      epochs: 42,
      gate: 'PASS'
    },
    series: history,
    forecast: fc.median.map((p, i) => ({
      t: p.t,
      median: p.v,
      p10: fc.p10[i].v,
      p90: fc.p90[i].v
    })),
    crossings,
    unit: sensor.unit
  }
}
