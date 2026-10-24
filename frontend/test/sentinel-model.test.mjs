// 哨兵 / 脚本 / 告警 三个模块的纯业务内核测试。
//
// 这些逻辑决定"什么时候该告警"和"什么脚本必须被拦住"，
// 是整套自动化里最容易出错、也最需要被钉死的部分。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  ALERT_SEVERITIES,
  canAutoDispatch,
  debounceDecision,
  describeRules,
  lintScript,
  requiresApproval,
  requiresHumanBeforeRemediation,
  rulesBreached,
  applyVariables
} from '../src/views/sentinel/sentinelModel.js'

test('single metric threshold fires only when the operator is satisfied', () => {
  const rules = [{ metric: 'memory', operator: 'gt', value: 90 }]
  assert.equal(rulesBreached(rules, { memory: 95 }), true)
  assert.equal(rulesBreached(rules, { memory: 90 }), false, 'gt must be strict')
  assert.equal(rulesBreached(rules, { memory: 89.9 }), false)
  assert.equal(rulesBreached([{ metric: 'memory', operator: 'gte', value: 90 }], { memory: 90 }), true)
})

test('compound thresholds require every condition in the same rule set', () => {
  const rules = [{ metric: 'cpu', operator: 'gt', value: 85 }, { metric: 'memory', operator: 'gt', value: 80 }]
  assert.equal(rulesBreached(rules, { cpu: 90, memory: 85 }), true)
  assert.equal(rulesBreached(rules, { cpu: 90, memory: 70 }), false, 'one unmet condition must not fire')
  assert.equal(rulesBreached(rules, { cpu: 10, memory: 99 }), false)
})

test('missing or non-numeric observations never fire an alert', () => {
  const rules = [{ metric: 'cpu', operator: 'gt', value: 85 }]
  assert.equal(rulesBreached(rules, {}), false)
  assert.equal(rulesBreached(rules, { cpu: null }), false)
  assert.equal(rulesBreached(rules, { cpu: 'high' }), false)
  assert.equal(rulesBreached(rules, { cpu: Number.NaN }), false)
  assert.equal(rulesBreached([], { cpu: 99 }), false)
  assert.equal(rulesBreached(rules, null), false)
})

test('debounce suppresses instantaneous spikes and fires only after the hold duration', () => {
  const rules = [{ metric: 'memory', operator: 'gt', value: 90 }]
  const start = 1_000_000
  // 刚越界：只记录起点，不告警
  const justBreached = debounceDecision({ rules, snapshot: { memory: 95 }, debounceSec: 300, breachedSinceMs: null, nowMs: start })
  assert.deepEqual(justBreached, { breached: true, shouldFire: false, heldSec: 0, remainingSec: 300 })
  // 持续 299 秒：仍不告警
  const holding = debounceDecision({ rules, snapshot: { memory: 95 }, debounceSec: 300, breachedSinceMs: start, nowMs: start + 299_000 })
  assert.equal(holding.shouldFire, false)
  assert.equal(holding.remainingSec, 1)
  // 持续满 300 秒：告警
  const fired = debounceDecision({ rules, snapshot: { memory: 95 }, debounceSec: 300, breachedSinceMs: start, nowMs: start + 300_000 })
  assert.equal(fired.shouldFire, true)
  assert.equal(fired.remainingSec, 0)
})

test('debounce state resets when the metric recovers', () => {
  const rules = [{ metric: 'memory', operator: 'gt', value: 90 }]
  const start = 1_000_000
  const recovered = debounceDecision({ rules, snapshot: { memory: 40 }, debounceSec: 300, breachedSinceMs: start, nowMs: start + 600_000 })
  assert.equal(recovered.breached, false)
  assert.equal(recovered.shouldFire, false, 'a recovered metric must never fire')
  assert.equal(recovered.heldSec, 0)
})

test('rule descriptions are readable and cover both metric kinds', () => {
  assert.equal(describeRules([{ metric: 'memory', operator: 'gt', value: 90 }]), '内存使用率 > 90')
  assert.equal(
    describeRules([{ metric: 'cpu', operator: 'gt', value: 85 }, { metric: 'disk', operator: 'gte', value: 80 }]),
    'CPU 使用率 > 85 且 磁盘使用率 ≥ 80'
  )
  assert.equal(describeRules([]), '未配置阈值')
})

test('script pre-check blocks the dangerous patterns it claims to block', () => {
  const blocked = [
    'rm -rf /',
    'sudo rm -rf /var/lib/mysql',
    'mkfs.ext4 /dev/sda1',
    'dd if=/dev/zero of=/dev/sda',
    'shutdown -h now',
    ':(){ :|:& };:',
    'iptables -F',
    'userdel ops',
    'DROP TABLE users;',
    'TRUNCATE TABLE orders;'
  ]
  for (const body of blocked) {
    const result = lintScript(body, 'shell')
    assert.equal(result.verdict, 'blocked', `must block: ${body}`)
    assert.ok(result.matches.length > 0, `must report which rule matched: ${body}`)
  }
})

test('script pre-check allows ordinary read-only operations', () => {
  for (const body of ['df -h', 'systemctl status nginx', 'free -m', 'cat /var/log/app.log | tail -n 50']) {
    const result = lintScript(body, 'shell')
    assert.equal(result.verdict, 'ok', `must allow: ${body}`)
    assert.equal(result.matches.length, 0)
  }
})

test('script pre-check rejects empty bodies and unsupported languages', () => {
  assert.equal(lintScript('', 'shell').verdict, 'syntax_error')
  assert.equal(lintScript('   ', 'shell').verdict, 'syntax_error')
  assert.equal(lintScript('echo hi', 'ruby').verdict, 'syntax_error')
})

test('bracket imbalance is reported as a suspected syntax error, not silently accepted', () => {
  // 只有括号数不配对时才报 syntax_error
  const imbalanced = lintScript('if [ -f /tmp/x ]; then echo $(date', 'shell')
  assert.equal(imbalanced.verdict, 'syntax_error')
  assert.match(imbalanced.detail, /括号/)
  // 括号配对但变量写法可疑时不应误报为语法错误（那属于运行期问题，预检只做粗检）
  assert.equal(lintScript('if [ -f /tmp/x ]; then echo ${x', 'shell').verdict, 'ok')
  // 语法错误与高危命中同时成立时，高危优先（更严重的结论不能被降级掩盖）
  assert.equal(lintScript('rm -rf / (', 'shell').verdict, 'blocked')
})

test('high risk scripts require administrator approval', () => {
  assert.equal(requiresApproval('HIGH'), true)
  assert.equal(requiresApproval('MEDIUM'), false)
  assert.equal(requiresApproval('LOW'), false)
})

test('platform variables are substituted and unreplaced tokens are reported', () => {
  // 键名与后端 SentinelVariables.SUPPORTED 一致（中文变量名），服务端才是权威。
  // missing 只报"受支持但没给值"的变量：完全未知的占位符会原样保留，
  // 由服务端 applyChecked 报出（前端不假装认识未知变量）。
  const result = applyVariables('echo ${主机IP} ${告警指标} ${告警值} ${告警级别}', { 主机IP: '10.0.0.1', 告警指标: 'memory', 告警值: 95 })
  assert.equal(result.body, 'echo 10.0.0.1 memory 95 ${告警级别}')
  assert.deepEqual(result.missing, ['${告警级别}'])
})

test('unknown placeholders are left untouched rather than silently dropped', () => {
  const result = applyVariables('echo ${完全未知}', { 主机IP: '10.0.0.1' })
  assert.equal(result.body, 'echo ${完全未知}')
  assert.deepEqual(result.missing, [], 'frontend does not claim to know unknown variables')
})

test('P0 and P1 always require a human before remediation', () => {
  assert.equal(requiresHumanBeforeRemediation('P0'), true)
  assert.equal(requiresHumanBeforeRemediation('P1'), true)
  assert.equal(requiresHumanBeforeRemediation('P2'), false)
  assert.equal(requiresHumanBeforeRemediation('P3'), false)
  assert.deepEqual(ALERT_SEVERITIES.map(item => item.id), ['P0', 'P1', 'P2', 'P3'])
})

test('auto dispatch never bypasses the approval gate', () => {
  // 高危脚本：即使低危告警、开关打开、也已审批，也不能自动发起
  assert.equal(canAutoDispatch({ severity: 'P3', autoDispatch: true, scriptRisk: 'HIGH', scriptApproved: true }), false)
  // 未审批脚本：不能自动发起
  assert.equal(canAutoDispatch({ severity: 'P3', autoDispatch: true, scriptRisk: 'LOW', scriptApproved: false }), false)
  // P0/P1：一律人工确认
  assert.equal(canAutoDispatch({ severity: 'P0', autoDispatch: true, scriptRisk: 'LOW', scriptApproved: true }), false)
  assert.equal(canAutoDispatch({ severity: 'P1', autoDispatch: true, scriptRisk: 'LOW', scriptApproved: true }), false)
  // 只有"低危级别 + 开关打开 + 低危脚本 + 已审批"才允许策略发起（且仍走预览与审批）
  assert.equal(canAutoDispatch({ severity: 'P3', autoDispatch: true, scriptRisk: 'LOW', scriptApproved: true }), true)
})
