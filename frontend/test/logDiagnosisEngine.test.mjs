import assert from 'node:assert/strict'
import test from 'node:test'

import { analyzeLog, maskSecrets, toMarkdown, LOG_DIAGNOSIS_RULES } from '../src/utils/logDiagnosisEngine.js'

test('rules library has at least 12 fingerprints with required fields', () => {
  assert.ok(LOG_DIAGNOSIS_RULES.length >= 12, `规则数 ${LOG_DIAGNOSIS_RULES.length} 应 ≥ 12`)
  for (const rule of LOG_DIAGNOSIS_RULES) {
    assert.ok(rule.id && rule.name && rule.reason && rule.recommendation, `${rule.id} 缺基础字段`)
    assert.ok(['WARN', 'ERROR', 'CRITICAL'].includes(rule.severity), `${rule.id} severity 非法`)
    assert.ok(Array.isArray(rule.patterns) && rule.patterns.length > 0, `${rule.id} 缺 patterns`)
    assert.ok(Array.isArray(rule.keywords) && rule.keywords.length > 0, `${rule.id} 缺 keywords`)
  }
})

test('matches multiple rules from a mixed log and keeps evidence', () => {
  const log = [
    '2026-11-16 10:00:01 INFO  boot: service starting on port 8080',
    '2026-11-16 10:00:05 ERROR [http] java.sql.SQLException: deadlock found when trying to get lock; try restarting transaction',
    '2026-11-16 10:00:06 WARN  pool-1: connect timed out after 3000ms',
    '2026-11-16 10:00:07 ERROR k8s: pod web-7f9d CrashLoopBackOff: back-off restarting failed container',
    '2026-11-16 10:00:08 INFO  boot: retry scheduled'
  ].join('\n')

  const result = analyzeLog(log)
  const ids = result.issues.map(issue => issue.ruleId)
  assert.ok(ids.includes('db-deadlock'), '应命中数据库死锁')
  assert.ok(ids.includes('timeout'), '应命中超时')
  assert.ok(ids.includes('k8s-crashloop'), '应命中 CrashLoopBackOff')

  const deadlock = result.issues.find(issue => issue.ruleId === 'db-deadlock')
  assert.equal(deadlock.severity, 'CRITICAL')
  assert.deepEqual(deadlock.lineNumbers, [2])
  assert.ok(deadlock.matches[0].includes('deadlock found'), '命中行应保留原始证据（脱敏后）')

  /* 严重级别降序：CRITICAL 在最前 */
  const order = result.issues.map(issue => issue.severity)
  assert.deepEqual(order, [...order].sort((a, b) => ({ CRITICAL: 3, ERROR: 2, WARN: 1 }[b]) - ({ CRITICAL: 3, ERROR: 2, WARN: 1 }[a])))

  /* 统计正确：5 行、2 个错误级别行 */
  assert.equal(result.stats.totalLines, 5)
  assert.equal(result.stats.errorLines, 2)
  assert.equal(result.stats.levelDist.ERROR, 2)
  assert.equal(result.stats.levelDist.WARN, 1)
  assert.equal(result.stats.levelDist.INFO, 2)
  assert.equal(result.stats.truncated, false)

  /* 摘要诚实描述命中 */
  assert.match(result.summary, /命中 3 条已知故障指纹/)
  /* markdown 报告可生成且含标题 */
  const report = toMarkdown(result)
  assert.match(report, /# 日志诊断报告/)
  assert.match(report, /CrashLoopBackOff/)
})

test('masks bearer tokens and passwords in matched evidence', () => {
  /* Authorization 头整段视为凭据（scheme+token 一起脱敏） */
  assert.equal(maskSecrets('Authorization: Bearer abc.def ghi'), 'Authorization:***')
  assert.equal(maskSecrets('Bearer raw-token-value'), 'Bearer ***')
  assert.equal(maskSecrets('jdbc:mysql://h/db?user=root&password=s3cret'), 'jdbc:mysql://h/db?user=root&password=***')
  assert.equal(maskSecrets('token: "very-secret-value"'), 'token:***')
  assert.equal(maskSecrets('API_KEY=abcd1234'), 'API_KEY=***')

  const result = analyzeLog('11:00:00 ERROR query failed: permission denied; user=A password=hunter2')
  const permission = result.issues.find(issue => issue.ruleId === 'permission-denied')
  assert.ok(permission, 'permission denied 应命中权限规则')
  assert.doesNotMatch(permission.matches[0], /hunter2/, '命中行不得泄漏明文密码')
  assert.match(permission.matches[0], /password=\*\*\*/)
})

test('empty input returns empty honest result', () => {
  const result = analyzeLog('')
  assert.deepEqual(result.issues, [])
  assert.equal(result.stats.totalLines, 0)
  assert.equal(result.stats.errorLines, 0)
  assert.match(result.summary, /未命中任何已知故障指纹/)
  assert.match(result.summary, /输入为空/)
  const report = toMarkdown(result)
  assert.match(report, /未命中任何已知故障指纹/)
})

test('oversized log is truncated to 200KB and flagged', () => {
  const line = 'x'.repeat(300) + ' ERROR OutOfMemoryError: Java heap space\n'
  const text = line.repeat(1000) /* 约 300KB+ */
  const result = analyzeLog(text)
  assert.equal(result.stats.truncated, true, '超过 200KB 应标记截断')
  assert.ok(result.stats.totalLines < 1000, '总行数应基于截断后的内容')
  assert.match(result.summary, /已截断|截断/)
  /* 截断后 OOM 仍应命中（指纹出现在前 200KB 内的行） */
  assert.ok(result.issues.some(issue => issue.ruleId === 'oom-memory'), '截断范围内的指纹仍应命中')
})

test('no fingerprint hit yields honest conclusion, not fabricated findings', () => {
  const log = [
    '2026-11-16 09:00:00 INFO app: config loaded',
    '2026-11-16 09:00:01 INFO app: serving /healthz'
  ].join('\n')
  const result = analyzeLog(log)
  assert.deepEqual(result.issues, [])
  assert.equal(result.stats.errorLines, 0)
  assert.match(result.summary, /未命中任何已知故障指纹/)
  assert.match(result.summary, /不编造结论|通用建议/)
  /* 无未解释样本 */
  assert.deepEqual(result.unmatchedErrorSamples, [])
})

test('unexplained error lines are surfaced honestly', () => {
  const log = [
    '2026-11-16 09:00:00 ERROR weixin-pay custom error code 8888 happened',
    '2026-11-16 09:00:01 ERROR gateway upstream hiccup'
  ].join('\n')
  const result = analyzeLog(log)
  /* 两行错误但不命中任何规则（避免误伤） */
  assert.deepEqual(result.issues, [])
  assert.equal(result.stats.errorLines, 2)
  assert.ok(result.unmatchedErrorSamples.length > 0, '未解释错误样本应如实列出')
  assert.ok(result.unmatchedErrorSamples.every(line => line.startsWith('2026-11-16')))
  assert.match(result.summary, /人工排查/)
})
