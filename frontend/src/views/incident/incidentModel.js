/**
 * 工单中心（Incident）纯逻辑模型。
 *
 * 状态机、等级、来源与后端 `IncidentStatus` / `IncidentSeverity` / `IncidentSource`
 * 一一对应；前端只做展示翻译，不自行扩展状态语义。
 * 后端状态机（IncidentStatus#canTransitionTo）：
 *   OPEN -> ACK | CLOSED（误报可直接关闭）
 *   ACK -> MITIGATING | RESOLVED | CLOSED
 *   MITIGATING -> RESOLVED
 *   RESOLVED -> CLOSED | MITIGATING（未解决可退回处置）
 *   CLOSED -> OPEN（允许重开）
 */

export const INCIDENT_STATUSES = Object.freeze([
  { id: 'OPEN', label: '待确认', hint: '新建，未确认' },
  { id: 'ACK', label: '已接单', hint: '已确认，有人接单' },
  { id: 'MITIGATING', label: '处置中', hint: '正在处置' },
  { id: 'RESOLVED', label: '已解决', hint: '已解决，待关闭' },
  { id: 'CLOSED', label: '已关闭', hint: '已关闭（含根因与复盘）' }
])

export const INCIDENT_SEVERITIES = Object.freeze([
  { id: 'P0', label: 'P0 / 紧急' },
  { id: 'P1', label: 'P1 / 高' },
  { id: 'P2', label: 'P2 / 中' },
  { id: 'P3', label: 'P3 / 低' }
])

export const INCIDENT_SOURCES = Object.freeze([
  { id: 'ALERT', label: '告警' },
  { id: 'USER_REPORT', label: '用户报障' },
  { id: 'AGENT_DIAGNOSIS', label: 'Agent 诊断' },
  { id: 'MANUAL', label: '手工' }
])

export const INCIDENT_EVENT_KINDS = Object.freeze([
  { id: 'STATUS_CHANGE', label: '状态流转' },
  { id: 'COMMENT', label: '评论' },
  { id: 'ASSIGN', label: '指派' },
  { id: 'SLA_BREACH', label: 'SLA 超时' },
  { id: 'SYSTEM', label: '系统' }
])

export const INCIDENT_RELATION_TYPES = Object.freeze([
  { id: 'ALERT', label: '关联告警' },
  { id: 'AGENT_RUN', label: '关联 Agent 运行' },
  { id: 'KNOWLEDGE', label: '关联知识' },
  { id: 'EVIDENCE', label: '关联证据' }
])

/** 与后端状态机保持一致的状态转移表；前端用它决定哪些按钮可用，最终以后端校验为准。 */
export const STATUS_TRANSITIONS = Object.freeze({
  OPEN: ['ACK', 'CLOSED'],
  ACK: ['MITIGATING', 'RESOLVED', 'CLOSED'],
  MITIGATING: ['RESOLVED'],
  RESOLVED: ['CLOSED', 'MITIGATING'],
  CLOSED: ['OPEN']
})

/** 当前状态下允许流转到的状态列表（未知状态返回空，禁用一切操作）。 */
export function allowedTransitions(status) {
  return Object.prototype.hasOwnProperty.call(STATUS_TRANSITIONS, status)
    ? STATUS_TRANSITIONS[status]
    : []
}

/** 是否允许从当前状态流转到目标状态。 */
export function canTransitionTo(status, target) {
  return allowedTransitions(status).includes(target)
}

const SEVERITY_ORDER = Object.freeze({ P0: 0, P1: 1, P2: 2, P3: 3 })

/** 列表排序：先按等级（P0 在前），再按创建时间倒序。不修改入参。 */
export function sortIncidents(incidents) {
  return [...(incidents || [])].sort((left, right) => {
    const rank = (SEVERITY_ORDER[left.severity] ?? 9) - (SEVERITY_ORDER[right.severity] ?? 9)
    if (rank !== 0) return rank
    return String(right.createdAt ?? '').localeCompare(String(left.createdAt ?? ''))
  })
}

/**
 * SLA 剩余时间（分钟）。返回正数=剩余，负数=已超时，null=无 SLA。
 * 纯函数：时间由调用方传入，便于测试。
 */
export function slaRemainingMinutes(slaDeadline, now = new Date()) {
  if (!slaDeadline) return null
  const deadline = Date.parse(slaDeadline)
  if (Number.isNaN(deadline)) return null
  return Math.round((deadline - now.getTime()) / 60000)
}

/**
 * 关闭表单是否可提交：根因、处置过程、复盘结论三者都必填（与后端 @NotBlank 对齐）。
 * 前端只做提前拦截，最终以后端校验为准。
 */
export function closeRequestReady(form = {}) {
  return ['rootCause', 'resolution', 'postmortem']
    .every(field => typeof form[field] === 'string' && form[field].trim().length > 0)
}

/** 新建表单最小可提交条件（与后端 @NotBlank title 对齐）。 */
export function createRequestReady(form = {}) {
  return typeof form.title === 'string' && form.title.trim().length > 0
}

export function statusLabel(status) {
  return INCIDENT_STATUSES.find(item => item.id === status)?.label ?? status ?? '—'
}

export function severityLabel(severity) {
  return INCIDENT_SEVERITIES.find(item => item.id === severity)?.label ?? severity ?? '—'
}

export function sourceLabel(source) {
  return INCIDENT_SOURCES.find(item => item.id === source)?.label ?? source ?? '—'
}

export function eventKindLabel(kind) {
  return INCIDENT_EVENT_KINDS.find(item => item.id === kind)?.label ?? kind ?? '—'
}

export function relationTypeLabel(type) {
  return INCIDENT_RELATION_TYPES.find(item => item.id === type)?.label ?? type ?? '—'
}
