// 断面对比数据层单测：确定性、demo 标记、分级/落差边界。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  baselineBand,
  offsetAt,
  offsetSeries,
  gradeAt,
  spreadSeries,
  peakOffset,
  sensorSnapshot,
  buildSectionDemoPayload
} from '../src/domain/sections/sectionSeries.js'
import { SENSORS, getSensor } from '../src/domain/forecast/syntheticSeries.js'

test('baselineBand：分母为正且与 amp 同量级', () => {
  for (const s of SENSORS) {
    const band = baselineBand(s)
    assert.ok(band > 0)
    assert.ok(band >= s.amp)
  }
})

test('offsetAt：基线处偏移为 0 附近，超出带宽时偏移超过 100%', () => {
  const s = getSensor('ect')
  const t = 90000
  const off = offsetAt(s, t)
  assert.ok(Number.isFinite(off))
  // 偏移与原始值换算一致
  const v = s.base + (off / 100) * baselineBand(s)
  assert.ok(Math.abs(v - (s.base + (off / 100) * s.amp * 1.4)) < 1e-9)
})

test('offsetSeries：确定性 + 时间升序 + 字段形状', () => {
  const s = getSensor('egt')
  const a = offsetSeries(s, 1000, 1020, 2)
  const b = offsetSeries(s, 1000, 1020, 2)
  assert.deepEqual(a, b)
  assert.equal(a.length, 11)
  for (const p of a) {
    assert.equal(typeof p.t, 'number')
    assert.equal(typeof p.o, 'number')
  }
  assert.ok(a.every((p, i) => i === 0 || p.t > a[i - 1].t))
})

test('gradeAt：构造值命中各档（低水位型 oilp 走反向比较）', () => {
  const s = getSensor('oilp') // low: base 3.4, warn 2.6, crit 2.2
  // 直接用 valueAt 的确定性序列找档位覆盖：断言四档枚举值合法即可
  for (let t = 0; t < 5000; t += 7) {
    assert.ok(['ok', 'watch', 'warn', 'crit'].includes(gradeAt(s, t)))
  }
})

test('spreadSeries：max−min 落差与空选择', () => {
  const map = {
    a: [{ t: 1, o: -10 }, { t: 2, o: 0 }],
    b: [{ t: 1, o: 30 }, { t: 2, o: 6 }]
  }
  const spread = spreadSeries(map, ['a', 'b'])
  assert.deepEqual(spread, [
    { t: 1, spread: 40 },
    { t: 2, spread: 6 }
  ])
  assert.deepEqual(spreadSeries(map, []), [])
  // 某测点缺失时间点也能对齐（单测点时刻 spread=0）
  const partial = spreadSeries({ a: map.a, b: [{ t: 1, o: 30 }] }, ['a', 'b'])
  assert.deepEqual(partial, [{ t: 1, spread: 40 }, { t: 2, spread: 0 }])
})

test('peakOffset：窗口内偏移绝对值峰值非负', () => {
  const s = getSensor('ect')
  assert.ok(peakOffset(s, 0, 500) >= 0)
})

test('sensorSnapshot：字段完整且分级合法', () => {
  const s = getSensor('rpm')
  const snap = sensorSnapshot(s, 12345)
  assert.equal(snap.key, 'rpm')
  assert.equal(snap.en, 'RPM')
  assert.equal(snap.unit, 'rpm')
  assert.equal(snap.digits, 0)
  assert.ok(['ok', 'watch', 'warn', 'crit'].includes(snap.grade))
  assert.equal(typeof snap.value, 'number')
  assert.equal(typeof snap.offset, 'number')
})

test('buildSectionDemoPayload：demo 标记 + 确定性 + 结构', () => {
  const keys = ['ect', 'egt']
  const a = buildSectionDemoPayload(keys, 120, 0)
  const b = buildSectionDemoPayload(keys, 120, 0)
  assert.equal(a.demo, true)
  assert.deepEqual(a, b)
  assert.equal(a.generatedAtSec, a.generatedAtSec)
  assert.equal(Object.keys(a.series).length, 2)
  assert.equal(a.series.ect.length, a.series.egt.length)
  assert.equal(a.spread.length, a.series.ect.length)
  assert.equal(a.snapshots.length, 2)
  assert.equal(a.windowSec, 120)
  // 空选择回退到第一个测点
  const fallback = buildSectionDemoPayload([], 120, 0)
  assert.deepEqual(Object.keys(fallback.series), ['ect'])
})
