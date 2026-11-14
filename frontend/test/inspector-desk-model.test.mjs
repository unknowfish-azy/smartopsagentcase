import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import {
  binEvents, linkState, linkStateRun, linkText, linkTextRun,
  filterEvents, filterRuns,
  normalizeEvents, normalizeRuns, buildDemoData
} from '../src/components/inspector/desk/deskModel.js'

const __dirname = dirname(fileURLToPath(import.meta.url))

test('InspectorCenterView 源码中不得出现 Preview: 编造指标', () => {
  const src = readFileSync(join(__dirname, '../src/views/inspector/InspectorCenterView.vue'), 'utf8')
  assert.ok(!src.includes('Preview:'), 'InspectorCenterView 不得包含 Preview: 编造指标')
})

test('分箱函数对空数组返回空箱（计数全 0）', () => {
  const start = 0
  const end = 86400000
  const bins = binEvents([], '24h', start, end)
  assert.equal(bins.length, 12)
  for (const bin of bins) {
    assert.equal(bin.CRITICAL, 0)
    assert.equal(bin.HIGH, 0)
    assert.equal(bin.WARN, 0)
    assert.equal(bin.PASS, 0)
    assert.ok(bin.from >= start && bin.to <= end)
  }
})

test('分箱按等级正确聚合计数', () => {
  const start = 0
  const end = 86400000
  const events = [
    { id: 'e1', at: start + 1000, severity: 'CRITICAL' },
    { id: 'e2', at: start + 2000, severity: 'HIGH' },
    { id: 'e3', at: start + 3000, severity: 'WARN' },
    { id: 'e4', at: start + 4000, severity: 'PASS' }
  ]
  const bins = binEvents(events, '24h', start, end)
  const first = bins[0]
  assert.equal(first.CRITICAL, 1)
  assert.equal(first.HIGH, 1)
  assert.equal(first.WARN, 1)
  assert.equal(first.PASS, 1)
})

test('linkState 四态：no-trace / miss / linked', () => {
  const runs = new Map()
  // no-trace
  assert.deepEqual(linkState({ traceId: null }, runs), { kind: 'no-trace' })
  assert.deepEqual(linkState({}, runs), { kind: 'no-trace' })
  // miss
  assert.deepEqual(linkState({ traceId: 'tr_miss' }, runs), { kind: 'miss', traceId: 'tr_miss' })
  // linked
  runs.set('tr_hit', { id: 'RUN-1' })
  const state = linkState({ traceId: 'tr_hit' }, runs)
  assert.equal(state.kind, 'linked')
  assert.equal(state.run.id, 'RUN-1')
})

test('linkText 四种文案与 DESIGN.md §5 一致', () => {
  assert.equal(linkText({ kind: 'no-trace' }), '没有 traceId · 无法定位运行记录')
  assert.equal(linkText({ kind: 'miss', traceId: 'tr_abc' }), '有 traceId（tr_abc），但运行记录里没有命中——可能超出窗口或未被采集')
  assert.equal(linkText({ kind: 'linked', run: { id: 'RUN-5521' } }), '已关联 RUN-5521 · 切到「运行」可看到高亮')
})

test('linkStateRun 反向四态与文案', () => {
  const events = new Map()
  assert.equal(linkTextRun(linkStateRun({ traceId: null }, events)), '没有 traceId · 无法定位纠察事件')
  assert.equal(linkTextRun(linkStateRun({ traceId: 'tr_x' }, events)), '有 traceId（tr_x），但纠察里没有命中（可能超出窗口）')
  events.set('tr_y', { id: 'EV-1' })
  assert.equal(linkTextRun(linkStateRun({ traceId: 'tr_y' }, events)), '已关联 EV-1 · 切到「纠察」可看到高亮')
})

test('filterEvents 按等级和已关联筛选', () => {
  const runs = new Map([['tr_1', { id: 'R1' }]])
  const events = [
    { id: 'e1', severity: 'CRITICAL', traceId: 'tr_1' },
    { id: 'e2', severity: 'WARN', traceId: null },
    { id: 'e3', severity: 'CRITICAL', traceId: 'tr_miss' }
  ]
  assert.equal(filterEvents(events, { severity: 'CRITICAL', runsByTrace: runs }).length, 2)
  assert.equal(filterEvents(events, { severity: 'WARN', runsByTrace: runs }).length, 1)
  const linked = filterEvents(events, { linkedOnly: true, runsByTrace: runs })
  assert.equal(linked.length, 1)
  assert.equal(linked[0].id, 'e1')
})

test('filterRuns 按工具和已关联筛选', () => {
  const events = new Map([['tr_1', { id: 'E1' }]])
  const runs = [
    { id: 'r1', tool: 'mysql-query', traceId: 'tr_1' },
    { id: 'r2', tool: 'docker-compose-status', traceId: null },
    { id: 'r3', tool: 'mysql-query', traceId: 'tr_miss' }
  ]
  assert.equal(filterRuns(runs, { tool: 'mysql-query', eventsByTrace: events }).length, 2)
  const linked = filterRuns(runs, { linkedOnly: true, eventsByTrace: events })
  assert.equal(linked.length, 1)
  assert.equal(linked[0].id, 'r1')
})

test('normalizeEvents 把后端字段映射到内部结构', () => {
  const raw = [
    { id: 'E1', createdAt: '2026-11-14T10:00:00Z', severity: 'HIGH', taskId: 'prom-mem' }
  ]
  const [e] = normalizeEvents(raw)
  assert.equal(e.id, 'E1')
  assert.equal(e.severity, 'HIGH')
  assert.equal(e.taskId, 'prom-mem')
  assert.ok(typeof e.at === 'number' && e.at > 0)
  assert.equal(e.traceId, null)
})

test('normalizeRuns 计算 duration 并归一化状态', () => {
  const raw = [
    { id: 'R1', toolId: 'mysql-query', startedAt: '2026-11-14T10:00:00Z', endedAt: '2026-11-14T10:00:05Z', status: 'ok' }
  ]
  const [r] = normalizeRuns(raw)
  assert.equal(r.id, 'R1')
  assert.equal(r.tool, 'mysql-query')
  assert.equal(r.status, 'SUCCESS')
  assert.ok(Math.abs(r.duration - 5) < 0.01)
})

test('buildDemoData 同一 windowKey 产出相同序列（确定性）', () => {
  const a = buildDemoData('24h')
  const b = buildDemoData('24h')
  assert.equal(a.events.length, b.events.length)
  assert.equal(a.runs.length, b.runs.length)
  // id / severity / taskId / traceId 由 seed 决定，是确定性的
  assert.equal(a.events[0].id, b.events[0].id)
  assert.equal(a.events[0].severity, b.events[0].severity)
  assert.equal(a.events[0].taskId, b.events[0].taskId)
  assert.equal(a.events[0].traceId, b.events[0].traceId)
  // at 依赖 Date.now()，两次调用会有毫秒级差异，只断言都落在窗口内
  assert.ok(a.events[0].at >= a.start && a.events[0].at <= a.end)
  assert.ok(b.events[0].at >= b.start && b.events[0].at <= b.end)
})
