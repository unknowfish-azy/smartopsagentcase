/**
 * 告警事件流时间线 · 纯函数层。
 *
 * 从告警对象的真实字段推导处置事件流（后端 sentinel_alert 无事件读取接口，
 * 因此前端按字段推导；缺时间戳显示 —，绝不编造时间）。
 *
 * 字段来源（SentinelService.mapAlert，GET /api/sentinel/alerts）：
 *   firedAt / acknowledgedAt / resolvedAt / closeNote / aiSummary /
 *   ticketId / status / severity / title / metric
 *
 * 事件 kinds（与后端 sentinel_alert_event 的记录口径对齐）：
 *   fired → acknowledged → analyzed → remediation → resolved → closed
 */

/**
 * @param {object|null} alert
 * @returns {Array<{kind:string, label:string, at:string|null, detail:string, done:boolean}>}
 *          按 firedAt 起点的时间升序返回
 */
export function buildAlertTimeline(alert) {
  if (!alert || typeof alert !== 'object') return []

  const status = String(alert.status || '').toUpperCase()
  const items = []

  items.push({
    kind: 'fired',
    label: '告警触发',
    at: alert.firedAt || null,
    detail: `${alert.metric || '指标'} 观测 ${alert.observedValue ?? '—'} / 阈值 ${alert.thresholdValue ?? '—'}`,
    done: true
  })

  items.push({
    kind: 'acknowledged',
    label: '确认收到',
    at: alert.acknowledgedAt || null,
    detail: alert.acknowledgedAt ? '人工确认收到告警' : '尚未确认（OPEN）',
    done: Boolean(alert.acknowledgedAt) || ['NOTIFIED', 'REMEDIATING', 'RESOLVED', 'CLOSED'].includes(status)
  })

  items.push({
    kind: 'analyzed',
    label: 'AI 研判',
    at: null, // 后端不回传研判时间，只有结论存在与否
    detail: alert.aiSummary ? '已生成研判建议（仅建议，不改变状态）' : '尚未研判',
    done: Boolean(alert.aiSummary)
  })

  items.push({
    kind: 'remediation',
    label: '处置/审批',
    at: null,
    detail: alert.ticketId ? `已关联工单 #${alert.ticketId}` : '未关联工单；脚本处置走预览→审批→执行链路',
    done: ['REMEDIATING', 'RESOLVED', 'CLOSED'].includes(status) || Boolean(alert.ticketId)
  })

  items.push({
    kind: 'resolved',
    label: '恢复/解决',
    at: alert.resolvedAt || null,
    detail: alert.resolvedAt ? '指标恢复或人工标记解决' : '尚未恢复',
    done: ['RESOLVED', 'CLOSED'].includes(status)
  })

  items.push({
    kind: 'closed',
    label: '关闭',
    at: null, // closed_by/close_note 有值但无关闭时间戳字段回传
    detail: alert.closeNote ? `关闭备注：${alert.closeNote}` : (status === 'CLOSED' ? '已关闭' : '未关闭'),
    done: status === 'CLOSED'
  })

  return items
}

/** 时间显示：缺值显示 —（不编造）。 */
export function formatTimelineAt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 当前进行到的事件（第一个未 done 的），用于高亮。 */
export function activeKind(timeline) {
  const firstOpen = timeline.find(item => !item.done)
  return firstOpen ? firstOpen.kind : null
}
