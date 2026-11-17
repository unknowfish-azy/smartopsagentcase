// 机房孪生数据层单测：确定性、阈值边界、2.5s 延迟预算、告警去噪。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  LATENCY_BUDGET_MS,
  buildRackLayout,
  deriveAlarms,
  hottestRacks,
  latencyStatus,
  metricLevel,
  pathLength,
  patrolPositionAt,
  patrolProgress,
  robotWaypoints,
  seededUnit,
  simulateSyncLatency,
  simulateTelemetry,
  twinSummary
} from '../src/domain/sentinel/dataCenterTwin.js'

test('buildRackLayout：排布确定且两排分居冷通道两侧', () => {
  const a = buildRackLayout(6, 2)
  const b = buildRackLayout(6, 2)

  assert.deepEqual(a, b)
  assert.equal(a.length, 12)
  assert.equal(a[0].id, 'R1-01')
  assert.equal(a[11].id, 'R2-06')
  assert.ok(a.filter(r => r.row === 0).every(r => r.z < 0))
  assert.ok(a.filter(r => r.row === 1).every(r => r.z > 0))
  // 同排机柜等距且关于原点对称
  const firstRow = a.filter(r => r.row === 0)
  assert.equal(firstRow[0].x, -firstRow[firstRow.length - 1].x)
})

test('seededUnit：同 seed 同 tick 恒定，且落在 [0,1)', () => {
  assert.equal(seededUnit('R1-01', 7), seededUnit('R1-01', 7))
  assert.notEqual(seededUnit('R1-01', 7), seededUnit('R1-02', 7))
  for (let i = 0; i < 50; i += 1) {
    const v = seededUnit(`rack-${i}`, i)
    assert.ok(v >= 0 && v < 1)
  }
})

test('simulateTelemetry：可重放，字段完整，温度落在合理区间', () => {
  const layout = buildRackLayout()
  const first = simulateTelemetry(layout, 12)
  const second = simulateTelemetry(layout, 12)

  assert.deepEqual(first, second)
  assert.equal(first.length, layout.length)
  for (const rack of first) {
    assert.equal(typeof rack.temperature, 'number')
    assert.equal(typeof rack.humidity, 'number')
    assert.equal(typeof rack.power, 'number')
    assert.ok(rack.temperature > 15 && rack.temperature < 40)
    assert.ok(rack.humidity > 20 && rack.humidity < 80)
    assert.ok(['ok', 'warn', 'critical'].includes(rack.level))
  }
  // 换 tick 后应有变化，否则「实时」不成立
  assert.notDeepEqual(first, simulateTelemetry(layout, 13))
})

test('metricLevel：温度/湿度阈值边界精确', () => {
  assert.equal(metricLevel('temperature', 27.9), 'ok')
  assert.equal(metricLevel('temperature', 28), 'warn')
  assert.equal(metricLevel('temperature', 31.9), 'warn')
  assert.equal(metricLevel('temperature', 32), 'critical')

  assert.equal(metricLevel('humidity', 50), 'ok')
  assert.equal(metricLevel('humidity', 29), 'warn')
  assert.equal(metricLevel('humidity', 65), 'warn')
  assert.equal(metricLevel('humidity', 75), 'critical')

  assert.equal(metricLevel('temperature', Number.NaN), 'unknown')
})

test('robotWaypoints / patrolPositionAt：闭合轨迹包住机柜并可循环插值', () => {
  const layout = buildRackLayout()
  const path = robotWaypoints(layout)
  assert.ok(path.length >= 4)
  assert.ok(pathLength(path) > 0)

  const xs = layout.map(r => r.x)
  const zs = layout.map(r => r.z)
  const pathXs = path.map(p => p.x)
  const pathZs = path.map(p => p.z)
  // 轨迹外围必须完整包住所有机柜
  assert.ok(Math.min(...pathXs) <= Math.min(...xs))
  assert.ok(Math.max(...pathXs) >= Math.max(...xs))
  assert.ok(Math.min(...pathZs) <= Math.min(...zs))
  assert.ok(Math.max(...pathZs) >= Math.max(...zs))

  const start = patrolPositionAt(path, 0)
  const wrapped = patrolPositionAt(path, 1)
  assert.deepEqual(start, wrapped)
  for (const p of [0, 0.13, 0.5, 0.87, 2.4]) {
    const pos = patrolPositionAt(path, p)
    assert.ok(Number.isFinite(pos.x) && Number.isFinite(pos.z) && Number.isFinite(pos.heading))
  }
  assert.deepEqual(patrolPositionAt([], 0.5), { x: 0, z: 0, heading: 0 })
})

test('patrolProgress：按圈时长循环，缺省 45 秒一圈', () => {
  assert.equal(patrolProgress(0), 0)
  assert.ok(Math.abs(patrolProgress(22500) - 0.5) < 1e-9)
  assert.equal(patrolProgress(45000), 0)
  assert.ok(patrolProgress(-100) === 0)
})

test('latencyStatus：2.5s 预算是闭区间上界', () => {
  assert.equal(LATENCY_BUDGET_MS, 2500)
  assert.equal(latencyStatus(320).level, 'ok')
  assert.equal(latencyStatus(1500).level, 'ok')
  assert.equal(latencyStatus(1501).level, 'warn')
  assert.equal(latencyStatus(2500).level, 'warn')
  assert.equal(latencyStatus(2501).level, 'breach')
  assert.equal(latencyStatus(Number.NaN).level, 'unknown')
})

test('simulateSyncLatency：存在超预算峰值供看板演示告警', () => {
  const values = []
  for (let t = 0; t < 40; t += 1) values.push(simulateSyncLatency(t))
  assert.ok(values.every(v => v > 0))
  assert.ok(values.some(v => v > LATENCY_BUDGET_MS))
  assert.equal(simulateSyncLatency(20), simulateSyncLatency(20))
})

test('deriveAlarms：只上报越界项，严重项排前', () => {
  const telemetry = [
    { id: 'R1-01', label: 'R1-01', temperature: 24, humidity: 50, power: 4 },
    { id: 'R1-02', label: 'R1-02', temperature: 33, humidity: 50, power: 4 },
    { id: 'R1-03', label: 'R1-03', temperature: 29, humidity: 50, power: 4 },
    { id: 'R1-04', label: 'R1-04', temperature: 24, humidity: 78, power: 4 }
  ]
  const alarms = deriveAlarms(telemetry)

  assert.equal(alarms.length, 3)
  assert.equal(alarms[0].level, 'critical')
  assert.equal(alarms[0].rackId, 'R1-02')
  assert.equal(alarms[0].metric, 'temperature')
  assert.ok(alarms.some(a => a.rackId === 'R1-04' && a.metric === 'humidity'))
  assert.ok(alarms.every(a => a.rackId !== 'R1-01'))
  assert.deepEqual(deriveAlarms([]), [])
})

test('hottestRacks / twinSummary：排行截断与汇总口径', () => {
  const layout = buildRackLayout()
  const telemetry = simulateTelemetry(layout, 5)
  const top = hottestRacks(telemetry, 3)

  assert.equal(top.length, 3)
  assert.ok(top[0].temperature >= top[1].temperature)
  assert.ok(top[1].temperature >= top[2].temperature)

  const summary = twinSummary(telemetry, 860, deriveAlarms(telemetry))
  assert.equal(summary.racks, layout.length)
  assert.equal(summary.latencyMs, 860)
  assert.equal(summary.latencyLevel, 'ok')
  assert.ok(summary.avgTemperature > 0)
  assert.ok(summary.totalPower > 0)

  const breached = twinSummary(telemetry, 2600, [])
  assert.equal(breached.latencyLevel, 'breach')
})
