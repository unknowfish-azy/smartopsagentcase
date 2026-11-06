import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

// T3 工单前端：模型层直接导入（纯 JS，无依赖）。
const {
  INCIDENT_STATUSES,
  INCIDENT_SEVERITIES,
  allowedTransitions,
  canTransitionTo,
  closeRequestReady,
  createRequestReady,
  sortIncidents,
  slaRemainingMinutes,
  statusLabel,
  severityLabel,
  sourceLabel,
  eventKindLabel,
  relationTypeLabel
} = await import(new URL('../src/views/incident/incidentModel.js', import.meta.url))

test('status transition map mirrors backend IncidentStatus state machine', () => {
  // 后端：OPEN -> ACK | CLOSED；ACK -> MITIGATING | RESOLVED | CLOSED；
  // MITIGATING -> RESOLVED；RESOLVED -> CLOSED | MITIGATING；CLOSED -> OPEN
  assert.deepEqual(allowedTransitions('OPEN'), ['ACK', 'CLOSED'])
  assert.deepEqual(allowedTransitions('ACK'), ['MITIGATING', 'RESOLVED', 'CLOSED'])
  assert.deepEqual(allowedTransitions('MITIGATING'), ['RESOLVED'])
  assert.deepEqual(allowedTransitions('RESOLVED'), ['CLOSED', 'MITIGATING'])
  assert.deepEqual(allowedTransitions('CLOSED'), ['OPEN'])
})

test('canTransitionTo rejects illegal transitions and unknown statuses fail closed', () => {
  assert.equal(canTransitionTo('OPEN', 'MITIGATING'), false) // 必须先接单
  assert.equal(canTransitionTo('MITIGATING', 'ACK'), false) // 不可回退到接单
  assert.equal(canTransitionTo('CLOSED', 'MITIGATING'), false)
  assert.equal(canTransitionTo('RESOLVED', 'MITIGATING'), true) // 未解决可退回处置
  assert.equal(canTransitionTo('UNKNOWN_STATUS', 'ACK'), false) // 未知状态一律禁用
  assert.equal(canTransitionTo(undefined, 'ACK'), false)
})

test('close form requires root cause, resolution and postmortem together', () => {
  assert.equal(closeRequestReady({}), false)
  assert.equal(closeRequestReady({ rootCause: 'r', resolution: '', postmortem: 'p' }), false)
  assert.equal(closeRequestReady({ rootCause: 'r', resolution: 'x', postmortem: 'p' }), true)
  assert.equal(closeRequestReady({ rootCause: '   ', resolution: 'x', postmortem: 'p' }), false) // 空白不算填
})

test('create form only requires a non-blank title', () => {
  assert.equal(createRequestReady({}), false)
  assert.equal(createRequestReady({ title: '  ' }), false)
  assert.equal(createRequestReady({ title: '支付服务 5xx 升高' }), true)
})

test('slaRemainingMinutes handles deadline, overdue and invalid input', () => {
  const now = new Date('2026-11-06T12:00:00Z')
  assert.equal(slaRemainingMinutes(null, now), null)
  assert.equal(slaRemainingMinutes('', now), null)
  assert.equal(slaRemainingMinutes('not-a-date', now), null)
  assert.equal(slaRemainingMinutes('2026-11-06T12:30:00Z', now), 30)
  assert.equal(slaRemainingMinutes('2026-11-06T11:00:00Z', now), -60)
})

test('sortIncidents orders by severity rank then newest first without mutating input', () => {
  const input = [
    { id: 1, severity: 'P3', createdAt: '2026-11-06T10:00:00' },
    { id: 2, severity: 'P0', createdAt: '2026-11-06T09:00:00' },
    { id: 3, severity: 'P0', createdAt: '2026-11-06T11:00:00' },
    { id: 4, severity: 'P2', createdAt: '2026-11-06T08:00:00' }
  ]
  const sorted = sortIncidents(input)
  assert.deepEqual(sorted.map(item => item.id), [3, 2, 4, 1])
  assert.deepEqual(input.map(item => item.id), [1, 2, 3, 4]) // 原数组不动
})

test('enum labels cover backend values and fall back to raw ids', () => {
  assert.equal(INCIDENT_STATUSES.length, 5)
  assert.equal(INCIDENT_SEVERITIES.map(item => item.id).join(','), 'P0,P1,P2,P3')
  assert.equal(statusLabel('CLOSED'), '已关闭')
  assert.equal(severityLabel('P0'), 'P0 / 紧急')
  assert.equal(sourceLabel('AGENT_DIAGNOSIS'), 'Agent 诊断')
  assert.equal(eventKindLabel('SLA_BREACH'), 'SLA 超时')
  assert.equal(relationTypeLabel('AGENT_RUN'), '关联 Agent 运行')
  assert.equal(statusLabel('SOMETHING_NEW'), 'SOMETHING_NEW') // 未知值原样透出，不吞掉
})

test('router and navigation register the incident pages (source-level wiring)', async () => {
  const router = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')
  assert.match(router, /path: 'incidents'/)
  assert.match(router, /name: 'IncidentCenter'/)
  assert.match(router, /path: 'incidents\/:id'/)
  assert.match(router, /name: 'IncidentDetail'/)
  assert.match(router, /IncidentCenterView\.vue/)
  assert.match(router, /IncidentDetailView\.vue/)

  const navigation = await readFile(new URL('../src/navigation/personalSystemNavigation.js', import.meta.url), 'utf8')
  assert.match(navigation, /routeName: 'IncidentCenter'/)
  assert.match(navigation, /to: '\/incidents'/)
})

test('views follow the honest-status convention instead of showing fake data', async () => {
  const list = await readFile(new URL('../src/views/incident/IncidentCenterView.vue', import.meta.url), 'utf8')
  const detail = await readFile(new URL('../src/views/incident/IncidentDetailView.vue', import.meta.url), 'utf8')
  // 三态口径：unauthorized / unavailable 必须显式提示，不允许静默或填充假数据
  for (const source of [list, detail]) {
    assert.match(source, /unauthorized/)
    assert.match(source, /unavailable/)
  }
  // 列表页把数据源如实映射为 ready 才渲染
  assert.match(list, /state\.status === 'ready'/)
  // 详情页关闭走后端强制校验的三个必填字段
  assert.match(detail, /closeRequestReady\(closeForm\)/)
})
