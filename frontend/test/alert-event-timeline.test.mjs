// 告警事件流时间线 · buildAlertTimeline 纯函数单测。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildAlertTimeline, formatTimelineAt, activeKind } from '../src/domain/sentinel/alertTimeline.js'

test('空/null 告警返回空时间线', () => {
  assert.deepEqual(buildAlertTimeline(null), [])
  assert.deepEqual(buildAlertTimeline(undefined), [])
  assert.deepEqual(buildAlertTimeline('x'), [])
})

test('完整生命周期：六个事件，字段时间透传，done 顺序推进', () => {
  const alert = {
    id: 1,
    title: 'EGT 越限',
    metric: 'egt',
    observedValue: 562,
    thresholdValue: 520,
    status: 'CLOSED',
    severity: 'P1',
    firedAt: '2026-11-16T10:00:00Z',
    acknowledgedAt: '2026-11-16T10:01:00Z',
    aiSummary: '建议查看排气温度趋势',
    ticketId: 42,
    resolvedAt: '2026-11-16T10:20:00Z',
    closeNote: '已人工复核'
  }
  const tl = buildAlertTimeline(alert)
  assert.equal(tl.length, 6)
  assert.deepEqual(tl.map(s => s.kind), ['fired', 'acknowledged', 'analyzed', 'remediation', 'resolved', 'closed'])
  assert.ok(tl.every(s => s.done), 'CLOSED 告警全部步骤 done')
  // 时间透传，缺省 null
  assert.equal(tl[0].at, '2026-11-16T10:00:00Z')
  assert.equal(tl[1].at, '2026-11-16T10:01:00Z')
  assert.equal(tl[4].at, '2026-11-16T10:20:00Z')
  assert.equal(tl[2].at, null, '研判无时间戳字段，恒为 null')
  assert.equal(tl[3].detail, '已关联工单 #42')
  assert.equal(tl[5].detail, '关闭备注：已人工复核')
  assert.equal(activeKind(tl), null, '全部完成时无进行中步骤')
})

test('OPEN 告警：确认/研判/处置/关闭未完成，进行中高亮在 acknowledged', () => {
  const alert = {
    status: 'OPEN',
    metric: 'ect',
    observedValue: 96.4,
    thresholdValue: 96,
    firedAt: '2026-11-16T10:00:00Z'
  }
  const tl = buildAlertTimeline(alert)
  assert.equal(tl[0].done, true)
  assert.ok(!tl[1].done)
  assert.ok(!tl[2].done)
  assert.ok(!tl[3].done)
  assert.equal(activeKind(tl), 'acknowledged')
  // detail 如实展示观测/阈值
  assert.ok(tl[0].detail.includes('96.4'))
  assert.ok(tl[0].detail.includes('96'))
})

test('REMEDIATING：处置已启动但未恢复（状态机已越过确认阶段）', () => {
  const tl = buildAlertTimeline({ status: 'REMEDIATING' })
  assert.ok(tl[1].done)    // REMEDIATING 意味着已经确认过（状态机越过 NOTIFIED）
  assert.ok(tl[3].done)    // REMEDIATING = 处置已启动
  assert.ok(!tl[4].done)
  assert.equal(activeKind(tl), 'analyzed')
  const withTicket = buildAlertTimeline({ status: 'OPEN', ticketId: 7 })
  assert.ok(withTicket[3].done)
})

test('formatTimelineAt：缺值/非法值显示 —（不编造）', () => {
  assert.equal(formatTimelineAt(null), '—')
  assert.equal(formatTimelineAt(''), '—')
  assert.equal(formatTimelineAt('not-a-date'), '—')
  const out = formatTimelineAt('2026-11-16T10:00:00Z')
  assert.notEqual(out, '—')
})
