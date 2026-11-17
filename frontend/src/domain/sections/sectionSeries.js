/**
 * 断面对比分析面 · 数据层。
 *
 * 语义口径（来源：外部作品"多断面对比"标题语义蒸馏；映射为本项目引擎传感器域
 * 的"多测点对比"，不指向任何真实河流或外部作品页面）：
 *   - 测点 = forecast 域的一个传感器（复用 SENSORS / valueAt / historySeries）
 *   - 归一化偏移 = 相对"基线带宽"的无量纲偏移 %，使不同单位可在同图对比
 *   - 离散落差 = 同一时刻窗口内多测点偏移的 max − min
 *   - 分级 = 正常 / 注意 / 预警 / 严重（由基线距、预警线、越界线推导）
 *
 * 所有 demo 序列带 { demo: true } 标记，页面必须双重声明（DEMO 角标 + 页脚）。
 * 本模块只在前端离线 / 用户主动选演示时启用；**绝不**作为接口兜底。
 */

import { SENSORS, getSensor, valueAt, historySeries } from '../forecast/syntheticSeries.js'

/** 基线带宽：amp 的 1.4 倍（与预测 sigma 同量级的稳定分母）。 */
export function baselineBand(sensor) {
  return Math.max(1e-6, sensor.amp * 1.4)
}

/**
 * 某测点在绝对时间 t 的归一化偏移（%）。
 * low 型传感器（如 OILP 越低越危险）取绝对偏移，方向语义由分级函数处理。
 */
export function offsetAt(sensor, t) {
  const v = valueAt(sensor, t)
  return ((v - sensor.base) / baselineBand(sensor)) * 100
}

/** 多测点同窗口偏移序列：{ [key]: Array<{t, o}> }，步长 2s。 */
export function offsetSeries(sensor, t0, t1, stepSec = 2) {
  return historySeries(sensor, t0, t1, stepSec).map(p => ({ t: p.t, o: offsetAt(sensor, p.t) }))
}

/**
 * 分级推导（G7：红=严重、琥珀=预警；正常/注意为中性）。
 * 返回 'ok' | 'watch' | 'warn' | 'crit'。
 */
export function gradeAt(sensor, t) {
  const v = valueAt(sensor, t)
  const off = Math.abs(v - sensor.base)
  const span = Math.abs(sensor.warn - sensor.base)
  if (sensor.low ? v <= sensor.crit : v >= sensor.crit) return 'crit'
  if (sensor.low ? v <= sensor.warn : v >= sensor.warn) return 'warn'
  if (off >= span * 0.6) return 'watch'
  return 'ok'
}

/**
 * 同一时刻多测点的离散落差（偏移 % 的 max − min）。
 * @param {Record<string, Array<{t:number, o:number}>>} seriesMap
 * @param {string[]} keys 参与对比的测点 key
 * @returns {Array<{t:number, spread:number}>}
 */
export function spreadSeries(seriesMap, keys) {
  if (!keys.length) return []
  const byTime = new Map()
  for (const key of keys) {
    for (const p of seriesMap[key] || []) {
      if (!byTime.has(p.t)) byTime.set(p.t, [])
      byTime.get(p.t).push(p.o)
    }
  }
  return [...byTime.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([t, vals]) => ({ t, spread: Math.max(...vals) - Math.min(...vals) }))
}

/** 某测点窗口内偏移绝对值的峰值（离散度排序条用）。 */
export function peakOffset(sensor, t0, t1) {
  let peak = 0
  for (let t = t0; t <= t1; t += 2) peak = Math.max(peak, Math.abs(offsetAt(sensor, t)))
  return peak
}

/** 测点当前读数快照（指标目录侧栏 / 读数汇总卡用）。 */
export function sensorSnapshot(sensor, t) {
  const v = valueAt(sensor, t)
  return {
    key: sensor.key,
    cn: sensor.cn,
    en: sensor.en,
    unit: sensor.unit,
    digits: sensor.digits,
    value: v,
    offset: Math.round(offsetAt(sensor, t) * 10) / 10,
    grade: gradeAt(sensor, t)
  }
}

/**
 * 构造整页 demo 数据包（与 /api/sentinel/sections 期望形状对齐）。
 * @param {string[]} selectedKeys 参与对比的测点 key
 * @param {number} windowSec 历史窗口秒数（默认 120）
 */
export function buildSectionDemoPayload(selectedKeys, windowSec = 120, nowOffset = 0) {
  const keys = (selectedKeys && selectedKeys.length ? selectedKeys : [SENSORS[0].key])
  const now = Math.round(Date.now() / 1000) + nowOffset
  const t0 = now - windowSec
  const seriesMap = {}
  const snapshots = []
  for (const key of keys) {
    const sensor = getSensor(key)
    seriesMap[key] = offsetSeries(sensor, t0, now, 2)
    snapshots.push(sensorSnapshot(sensor, now))
  }
  return {
    demo: true,
    generatedAt: new Date(now * 1000).toISOString(),
    generatedAtSec: now,
    windowSec,
    series: seriesMap,
    spread: spreadSeries(seriesMap, keys),
    snapshots
  }
}
