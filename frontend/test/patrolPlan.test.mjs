import assert from 'node:assert/strict'
import test from 'node:test'

import { mapProbeToInspection, summarizePatrol, REASON_MAX_LENGTH } from '../src/utils/patrolPlan.js'

/* 真实返回形状参照 backend HttpProbeService.Result：
 * { status, statusCode, durationMs, responseBytes, truncated, assertion, summary, nextAction, errorCategory } */
const HEALTHY_PROBE = {
  status: 'HEALTHY',
  statusCode: 200,
  durationMs: 43,
  responseBytes: 512,
  truncated: false,
  assertion: 'PASS',
  summary: '检查完成',
  nextAction: '无需处理',
  errorCategory: null
}

const UNHEALTHY_ASSERTION = {
  status: 'UNHEALTHY',
  statusCode: 200,
  durationMs: 51,
  responseBytes: 96,
  truncated: false,
  assertion: 'FAIL',
  summary: '检查完成',
  nextAction: '核对目标状态码、路径和服务日志',
  errorCategory: 'ASSERTION'
}

const UNHEALTHY_TIMEOUT = {
  status: 'UNHEALTHY',
  statusCode: 0,
  durationMs: 1005,
  responseBytes: 0,
  truncated: false,
  assertion: 'TIMEOUT',
  summary: '目标连接或读取超时',
  nextAction: '检查目标配置、网络和证书',
  errorCategory: 'TIMEOUT'
}

test('HEALTHY 探测映射为 PASS / INFO，taskId 与 metadata 来自真实输入', () => {
  const payload = mapProbeToInspection('gateway-web', HEALTHY_PROBE, 87)

  assert.equal(payload.status, 'PASS')
  assert.equal(payload.severity, 'INFO')
  assert.equal(payload.requiresHuman, false)
  assert.equal(payload.category, 'PATROL')
  assert.equal(payload.target, 'gateway-web')
  /* taskId 形状：PATROL-<targetId>-<6 位大写随机段> */
  assert.match(payload.taskId, /^PATROL-gateway-web-[A-Z0-9]{6}$/)
  /* reason 拼接真实状态码与断言，不编造 */
  assert.match(payload.reason, /HEALTHY/)
  assert.match(payload.reason, /状态码 200/)
  assert.match(payload.reason, /断言 PASS/)
  /* metadata 契约：耗时 + 探测类型 */
  assert.deepEqual(payload.metadata, { elapsedMs: 87, probeKind: 'http' })
  /* recommendation 来自真实 nextAction 字段 */
  assert.equal(payload.recommendation, '无需处理')
  /* evidence 保留原始探测字段 */
  const evidence = JSON.parse(payload.evidence[0].content)
  assert.equal(evidence.status, 'HEALTHY')
  assert.equal(evidence.statusCode, 200)
  assert.equal(payload.evidence[0].source, 'diagnostics/http')
  /* PASS 不带 issues */
  assert.equal(payload.issues, undefined)
})

test('UNHEALTHY 探测（断言不过 / 网络失败）映射为 FAIL / HIGH 且要求人工', () => {
  for (const probe of [UNHEALTHY_ASSERTION, UNHEALTHY_TIMEOUT]) {
    const payload = mapProbeToInspection('gateway-web', probe, 120)

    assert.equal(payload.status, 'FAIL')
    assert.equal(payload.severity, 'HIGH')
    assert.equal(payload.requiresHuman, true)
    assert.equal(payload.category, 'PATROL')
    /* reason 如实携带真实状态码、断言与 summary */
    assert.match(payload.reason, /UNHEALTHY/)
    assert.match(payload.reason, new RegExp(`断言 ${probe.assertion}`))
    assert.ok(payload.reason.includes(probe.summary), 'reason 应包含真实 summary')
    /* recommendation 仍是真实 nextAction */
    assert.equal(payload.recommendation, probe.nextAction)
    /* FAIL 附带一条 issue 且 reason 一致 */
    assert.equal(payload.issues.length, 1)
    assert.equal(payload.issues[0].category, 'PATROL')
    assert.equal(payload.issues[0].severity, 'HIGH')
    assert.equal(payload.issues[0].reason, payload.reason)
    assert.deepEqual(payload.metadata, { elapsedMs: 120, probeKind: 'http' })
  }
})

test('接口异常（probeResult 为空）映射为 FAIL / HIGH，reason 用真实错误文本', () => {
  const payload = mapProbeToInspection('gateway-web', null, 320, '无法连接服务器，请检查后端服务是否启动')

  assert.equal(payload.status, 'FAIL')
  assert.equal(payload.severity, 'HIGH')
  assert.equal(payload.requiresHuman, true)
  assert.equal(payload.reason, '无法连接服务器，请检查后端服务是否启动')
  /* 异常时无真实探测返回，不得编造 nextAction 与 evidence */
  assert.equal(payload.recommendation, undefined)
  assert.deepEqual(payload.evidence, [])
  assert.equal(payload.issues.length, 1)
  assert.equal(payload.issues[0].reason, payload.reason)
})

test('接口异常错误文本超长时截断到 500 字符，不添油加醋', () => {
  const longError = 'E'.repeat(1200)
  const payload = mapProbeToInspection('gateway-web', null, 0, longError)

  assert.equal(payload.reason.length, REASON_MAX_LENGTH)
  assert.ok(payload.reason.startsWith('E'.repeat(100)))
})

test('缺少 errorText 时给出诚实的兜底描述，不编造具体原因', () => {
  const payload = mapProbeToInspection('gateway-web', null, 0)
  assert.equal(payload.status, 'FAIL')
  assert.match(payload.reason, /HTTP 探测接口调用异常/)
})

test('summarizePatrol 按结论统计 total/pass/fail/unknown', () => {
  const rows = [
    { conclusion: 'PASS' },
    { conclusion: 'PASS' },
    { conclusion: 'FAIL' },
    { conclusion: null },
    { phase: 'running' }
  ]
  assert.deepEqual(summarizePatrol(rows), { total: 5, pass: 2, fail: 1, unknown: 2 })
})

test('summarizePatrol 对空与非数组输入返回全零，不抛错', () => {
  assert.deepEqual(summarizePatrol([]), { total: 0, pass: 0, fail: 0, unknown: 0 })
  assert.deepEqual(summarizePatrol(null), { total: 0, pass: 0, fail: 0, unknown: 0 })
  assert.deepEqual(summarizePatrol(undefined), { total: 0, pass: 0, fail: 0, unknown: 0 })
})

test('同目标多次映射 taskId 不重复（随机段去重）', () => {
  const ids = new Set(Array.from({ length: 50 }, () => mapProbeToInspection('gateway-web', HEALTHY_PROBE, 1).taskId))
  assert.equal(ids.size, 50, '50 次映射应产生 50 个不同 taskId')
})
