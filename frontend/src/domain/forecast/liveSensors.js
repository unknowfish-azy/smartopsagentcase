/**
 * 预测面 · live 态指标槽位。
 *
 * 口径（与后端 `SentinelForecastService.SLOTS` 一一对应）：
 *   六个 UI 槽位是**语义别名**，不是引擎传感器。真实数据源只有哨兵采样
 *   cpu / memory / disk / tcp / port / log_hits，采样间隔 30~60s。
 *
 * 后端 `/api/sentinel/forecast/catalog` 只返回**确实有采样**的槽位，
 * 并给出该槽位的真实名称、单位与阈值方向；本模块只做展示层归一化，不猜值、不补默认值。
 *
 * demo 态仍用 `syntheticSeries.js` 的六传感器（ECT/RPM/EGT/OILP/IAT/VBAT），
 * 那是设计稿的虚构示例，双重声明 DEMO，不得当作接口返回值。
 */

/** 低水位型指标（越低越危险），阈值方向与其他相反。 */
const LOW_METRICS = new Set(['port'])

/** 槽位 → 真实哨兵指标的兜底说明（后端 catalog 缺失时至少能说明"在等什么"）。 */
export const LIVE_SENSOR_NOTES = Object.freeze({
  ect: '映射到真实指标 cpu',
  rpm: '映射到真实指标 memory',
  egt: '映射到真实指标 disk',
  oilp: '映射到真实指标 tcp',
  iat: '映射到真实指标 port',
  vbat: '映射到真实指标 log_hits'
})

/**
 * 把后端 catalog 条目转成图表可用的 sensor 形状。
 * 缺字段一律留空 / 0，由调用方决定是否显示 offline。
 */
export function normalizeCatalogEntry(entry) {
  return {
    key: entry.key,
    cn: entry.cn,
    en: entry.en,
    metric: entry.metric,
    unit: entry.unit || '',
    warn: numberOrZero(entry.warnAbove, entry.warnBelow),
    crit: numberOrZero(entry.critAbove, entry.critBelow),
    low: isLowMetric(entry),
    // 真实指标没有"小数位"约定：cpu/memory/disk 百分比取 1 位，其余整数。
    digits: pickDigits(entry.metric),
    // 供「门控权重」等 UI 组件继续按 key 高亮使用。
    base: baselineFor(entry.metric)
  }
}

function numberOrZero(primary, fallback) {
  if (primary !== null && primary !== undefined && primary !== 0) return Number(primary)
  if (fallback !== null && fallback !== undefined && fallback !== 0) return Number(fallback)
  return 0
}

function isLowMetric(entry) {
  if (entry.low === true) return true
  return LOW_METRICS.has(String(entry.metric || '').toLowerCase())
}

function pickDigits(metric) {
  switch (String(metric || '').toLowerCase()) {
    case 'cpu':
    case 'memory':
    case 'disk':
      return 1
    default:
      return 0
  }
}

/** 真实指标的典型量级，仅用于门控权重条的相对长度；不是实测值。 */
function baselineFor(metric) {
  switch (String(metric || '').toLowerCase()) {
    case 'cpu': return 40
    case 'memory': return 55
    case 'disk': return 62
    case 'tcp': return 80
    case 'port': return 1
    case 'log_hits': return 40
    default: return 50
  }
}

/** 按 key（或真实指标名）从 catalog 里挑一个槽位；找不到返回 null，调用方显式处理。 */
export function findLiveSensor(catalogSlots, key) {
  const list = Array.isArray(catalogSlots) ? catalogSlots : []
  return (
    list.find((slot) => slot.key === key) ||
    list.find((slot) => slot.metric === key) ||
    list[0] ||
    null
  )
}
