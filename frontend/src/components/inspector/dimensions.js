/**
 * 纠察维度共享定义。
 * 供 InspectorDimensionGrid 与 InspectorCenterView 共用，避免两处各自维护
 * 一套别名导致筛选结果与卡片计数对不上。
 *
 * 诚实性约束：category 未命中任何别名时返回空串，调用方应忽略该事件，
 * 不得把它「均摊」到 8 个维度里凑数。
 */
export const DIMENSIONS = Object.freeze([
  { key: 'behavior', cn: '智能体行为', en: 'AGENT BEHAVIOR', aliases: ['AGENT_BEHAVIOR', 'BEHAVIOR', 'PLANNER', 'AGENT'] },
  { key: 'evidence', cn: '证据质量', en: 'EVIDENCE QUALITY', aliases: ['EVIDENCE_QUALITY', 'EVIDENCE'] },
  { key: 'tool', cn: '工具使用', en: 'TOOL USAGE', aliases: ['TOOL_USAGE', 'TOOL'] },
  { key: 'risk', cn: '风险', en: 'RISK', aliases: ['RISK', 'OBSERVABILITY'] },
  { key: 'approval', cn: '审批', en: 'APPROVAL', aliases: ['APPROVAL', 'HITL'] },
  { key: 'verification', cn: '验证', en: 'VERIFICATION', aliases: ['VERIFICATION', 'VERIFY'] },
  { key: 'knowledge', cn: '知识', en: 'KNOWLEDGE', aliases: ['KNOWLEDGE', 'DATABASE'] },
  { key: 'security', cn: '安全', en: 'SECURITY', aliases: ['SECURITY', 'STABILITY', 'CLOUD_NATIVE'] }
])

export const SEVERITIES = Object.freeze(['PASS', 'WARN', 'HIGH', 'CRITICAL'])

export function toEventTimestamp(event) {
  const raw = event?.at ?? event?.createdAt ?? event?.time
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  const parsed = Date.parse(raw)
  return Number.isNaN(parsed) ? 0 : parsed
}

export function dimensionKeyOf(event) {
  const category = String(event?.category || '').toUpperCase()
  if (!category) return ''
  const found = DIMENSIONS.find(item => item.aliases.includes(category))
  return found ? found.key : ''
}

export function summaryFromEvents(events) {
  const result = { total: events.length, pass: 0, warning: 0, high: 0, critical: 0 }
  events.forEach(event => {
    const level = String(event.severity || '').toUpperCase()
    if (level === 'PASS') result.pass += 1
    else if (level === 'WARN' || level === 'WARNING') result.warning += 1
    else if (level === 'HIGH') result.high += 1
    else if (level === 'CRITICAL') result.critical += 1
  })
  return result
}
