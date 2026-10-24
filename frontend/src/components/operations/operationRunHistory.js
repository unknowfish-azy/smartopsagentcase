const STATUS_LABELS = Object.freeze({
  SUCCESS: '执行成功', FAILED: '执行失败', RUNNING: '执行中', CANCELLED: '已取消'
})

export function runStatusLabel(status) { return STATUS_LABELS[status] || status || '未知状态' }
export function outputState(exitCode) {
  if (exitCode == null || exitCode === '') return 'unknown'
  return Number(exitCode) === 0 ? 'success' : 'failed'
}
export function visibleOutput(value) { return value == null ? '' : String(value) }
export function candidateStatusLabel(status) {
  return status === 'PENDING_REVIEW' ? '待人工审核' : status || '未知状态'
}

export function formatDuration(startedAt, endedAt) {
  if (!endedAt) return '执行中'
  const milliseconds = new Date(endedAt).getTime() - new Date(startedAt).getTime()
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '—'
  if (milliseconds < 1000) return `${milliseconds} 毫秒`
  return `${Number((milliseconds / 1000).toFixed(2))} 秒`
}

export function cleanRunQuery(query = {}) {
  const cleaned = {}
  for (const key of ['traceId', 'toolId', 'status', 'startedFrom', 'startedTo']) {
    const value = query[key]
    if (value != null && String(value).trim()) cleaned[key] = String(value).trim()
  }
  cleaned.page = Math.max(1, Number(query.page) || 1)
  cleaned.pageSize = Math.max(1, Math.min(100, Number(query.pageSize) || 20))
  return cleaned
}

export function normalizeDateTime(value) {
  if (!value || String(value).length < 16) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString()
}

export function validateRunTimeRange(startedFrom, startedTo) {
  const errors = {}
  if (startedFrom && !normalizeDateTime(startedFrom)) errors.startedFrom = '开始时间格式无效。'
  if (startedTo && !normalizeDateTime(startedTo)) errors.startedTo = '结束时间格式无效。'
  if (!errors.startedFrom && !errors.startedTo && startedFrom && startedTo && new Date(startedFrom) > new Date(startedTo)) {
    errors.startedFrom = '结束时间必须晚于开始时间。'
  }
  return errors
}
