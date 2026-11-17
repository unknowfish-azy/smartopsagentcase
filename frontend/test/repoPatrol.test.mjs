import assert from 'node:assert/strict'
import test from 'node:test'
import { mapSummaryToZones, matchZoneKey, ZONE_KEYS } from '../src/utils/repoPatrol.js'

test('mapSummaryToZones：按事件 target 关键词匹配到对应区块', () => {
  const events = [
    { target: 'KNOWLEDGE-BASE INDEX', severity: 'WARN' },
    { target: '知识图谱蒸馏任务', severity: 'CRITICAL' },
    { target: 'CLOUD-NATIVE K8S POD', severity: 'HIGH' },
    { target: 'harbor image scan', severity: 'WARN' },
    { target: 'insights query plan', severity: 'WARN' }
  ]
  const { zones } = mapSummaryToZones({ total: 5, pass: 0, warning: 3, high: 2, critical: 0 }, events)
  assert.equal(zones.knowledge.warningCount, 1)
  assert.equal(zones.knowledge.criticalCount, 1)
  assert.equal(zones.knowledge.level, 'alert')
  assert.equal(zones['cloud-native'].criticalCount, 1)
  assert.equal(zones['cloud-native'].level, 'alert')
  assert.equal(zones.harbor.warningCount, 1)
  assert.equal(zones.harbor.level, 'warn')
  assert.equal(zones.insights.warningCount, 1)
  assert.equal(zones.insights.level, 'warn')
  assert.equal(zones.general.warningCount, 0)
  assert.equal(zones.general.criticalCount, 0)
})

test('mapSummaryToZones：无法匹配 target 的异常归入 general 兜底桶', () => {
  const events = [
    { target: 'MYSTERY-SERVICE-07', severity: 'WARN' },
    { target: null, severity: 'CRITICAL' },
    { target: '   ', severity: 'HIGH' }
  ]
  const { zones, overall } = mapSummaryToZones(null, events)
  assert.equal(zones.general.warningCount, 1)
  assert.equal(zones.general.criticalCount, 2)
  assert.equal(zones.general.level, 'alert')
  // 4 个功能区块不受 general 事件污染
  assert.equal(zones.knowledge.criticalCount, 0)
  assert.equal(zones.knowledge.level, 'ok')
  // summary 缺失（接口失败）时 overall 回退为事件合计，仍为真实数据
  assert.deepEqual(overall, { warningCount: 1, criticalCount: 2, level: 'alert' })
})

test('mapSummaryToZones：无事件 / 入参为空时全部 ok（静默降级不编造）', () => {
  const { zones, overall } = mapSummaryToZones({ total: 0, pass: 0, warning: 0, high: 0, critical: 0 }, [])
  for (const key of ZONE_KEYS) {
    assert.equal(zones[key].warningCount, 0)
    assert.equal(zones[key].criticalCount, 0)
    assert.equal(zones[key].level, 'ok')
  }
  assert.deepEqual(overall, { warningCount: 0, criticalCount: 0, level: 'ok' })
  // summary / events 双缺失（接口全失败的降级路径）
  const empty = mapSummaryToZones(null, undefined)
  assert.equal(empty.zones.harbor.level, 'ok')
  assert.deepEqual(empty.overall, { warningCount: 0, criticalCount: 0, level: 'ok' })
})

test('mapSummaryToZones：critical 优先于 warn 的 level 判定', () => {
  // 仅 warn → warn
  const warnOnly = mapSummaryToZones(null, [{ target: 'knowledge', severity: 'WARN' }])
  assert.equal(warnOnly.zones.knowledge.level, 'warn')
  // warn + critical → alert（critical 优先）
  const both = mapSummaryToZones(null, [
    { target: 'knowledge', severity: 'WARN' },
    { target: 'knowledge', severity: 'CRITICAL' }
  ])
  assert.equal(both.zones.knowledge.level, 'alert')
  // HIGH 与 CRITICAL 同计入严重档
  const highCounts = mapSummaryToZones(null, [{ target: 'harbor', severity: 'HIGH' }])
  assert.equal(highCounts.zones.harbor.criticalCount, 1)
  assert.equal(highCounts.zones.harbor.level, 'alert')
  // PASS 事件不计入任何计数
  const passOnly = mapSummaryToZones(null, [{ target: 'harbor', severity: 'PASS' }])
  assert.equal(passOnly.zones.harbor.level, 'ok')
  // overall：summary 有 high（并入严重档）→ alert
  const overallAlert = mapSummaryToZones({ total: 4, pass: 1, warning: 2, high: 1, critical: 0 }, [])
  assert.equal(overallAlert.overall.level, 'alert')
  assert.equal(overallAlert.overall.criticalCount, 1)
  // overall：summary 仅 warning → warn
  const overallWarn = mapSummaryToZones({ total: 4, pass: 2, warning: 2, high: 0, critical: 0 }, [])
  assert.equal(overallWarn.overall.level, 'warn')
})

test('matchZoneKey：中文别名与大小写不敏感匹配，空值归 general', () => {
  assert.equal(matchZoneKey('知识库巡检'), 'knowledge')
  assert.equal(matchZoneKey('harbor cve scan'), 'harbor')
  assert.equal(matchZoneKey('Cloud Native Deploy'), 'cloud-native')
  assert.equal(matchZoneKey('insights 洞察'), 'insights')
  assert.equal(matchZoneKey(''), 'general')
  assert.equal(matchZoneKey(undefined), 'general')
})
