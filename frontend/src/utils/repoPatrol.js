/**
 * repoPatrol.js — 智能仓库大屏「孪生巡检」数据映射（纯函数，可单测）
 *
 * 职责：把纠察中心真实接口数据（summary + events）映射到仓库 4 个功能区块
 *      （knowledge / insights / cloud-native / harbor），无法归区的事件进 general
 *      兜底桶；供 SmartRepositoryView 绘制状态气泡、模块卡徽标与跳转判定。
 *
 * 证据规则：所有计数都来自入参真实数据，函数不编造任何数字；
 *          入参为空（接口失败静默降级）时返回全 ok 的空状态。
 */

/** 区块关键词表：按事件 target 字段匹配（不区分大小写的包含匹配 + 中文别名） */
const ZONE_KEYWORDS = Object.freeze([
  { key: 'knowledge', keywords: ['KNOWLEDGE', '知识', 'ATLAS', '图谱'] },
  { key: 'insights', keywords: ['INSIGHT', '洞察', 'QUERY', '问数'] },
  { key: 'cloud-native', keywords: ['CLOUD', '云原生', 'K8S', 'KUBERNETES', 'CONTAINER', '容器', 'DOCKER', 'NATIVE'] },
  { key: 'harbor', keywords: ['HARBOR', '镜像', 'IMAGE', 'REGISTRY', 'SCAN', '扫描', 'CVE'] },
  { key: 'general', keywords: [] }
])

export const ZONE_KEYS = ZONE_KEYWORDS.map(zone => zone.key)

/** 严重度分组：CRITICAL/HIGH 计入 critical，WARN/WARNING 计入 warning，PASS/OK 不计 */
function severityBucket(value) {
  const up = String(value || '').toUpperCase()
  if (up === 'CRITICAL' || up === 'HIGH') return 'critical'
  if (up === 'WARN' || up === 'WARNING') return 'warning'
  return null
}

/** 事件 target → zone key：按关键词表顺序首个命中；空值 / 无法匹配归 general */
export function matchZoneKey(target) {
  const text = String(target || '').trim().toUpperCase()
  if (!text) return 'general'
  for (const zone of ZONE_KEYWORDS) {
    if (zone.keywords.some(keyword => text.includes(keyword))) return zone.key
  }
  return 'general'
}

/** level 判定：critical 优先于 warn，均无则 ok */
function levelOf({ warningCount, criticalCount }) {
  if (criticalCount > 0) return 'alert'
  if (warningCount > 0) return 'warn'
  return 'ok'
}

/**
 * overall 汇总：summary 可用则优先采用（high 与 critical 均计入严重档），
 * summary 缺失（接口失败）时回退为事件列表合计，仍为真实数据。
 */
function buildOverall(summary, eventList) {
  if (summary && typeof summary === 'object') {
    const warningCount = Math.max(0, Number(summary.warning) || 0)
    const criticalCount = Math.max(0, (Number(summary.high) || 0) + (Number(summary.critical) || 0))
    return { warningCount, criticalCount, level: levelOf({ warningCount, criticalCount }) }
  }
  let warningCount = 0
  let criticalCount = 0
  for (const event of eventList) {
    const bucket = severityBucket(event?.severity)
    if (bucket === 'critical') criticalCount += 1
    else if (bucket === 'warning') warningCount += 1
  }
  return { warningCount, criticalCount, level: levelOf({ warningCount, criticalCount }) }
}

/**
 * mapSummaryToZones(summary, events) → { zones, overall }
 *
 * @param {object|null} summary 纠察汇总 { total, pass, warning, high, critical }，可为 null
 * @param {Array} events 纠察事件列表 [{ target, severity, category, createdAt, ... }]
 * @returns {{ zones: Record<string, {key, warningCount, criticalCount, level}>, overall: {warningCount, criticalCount, level} }}
 *          zones 含 4 个功能区块 + general 兜底桶，level ∈ 'ok' | 'warn' | 'alert'
 */
export function mapSummaryToZones(summary, events = []) {
  const eventList = Array.isArray(events) ? events : []
  const counters = Object.fromEntries(ZONE_KEYS.map(key => [key, { warningCount: 0, criticalCount: 0 }]))

  for (const event of eventList) {
    const bucket = severityBucket(event?.severity)
    if (!bucket) continue
    const zoneKey = matchZoneKey(event?.target)
    counters[zoneKey][bucket === 'critical' ? 'criticalCount' : 'warningCount'] += 1
  }

  const zones = Object.fromEntries(
    ZONE_KEYS.map(key => {
      const zone = { key, ...counters[key] }
      zone.level = levelOf(zone)
      return [key, zone]
    })
  )

  return { zones, overall: buildOverall(summary, eventList) }
}
