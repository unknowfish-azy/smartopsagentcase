/**
 * test/useCompositionField.test.mjs
 *
 * 纯函数单测：(loops, stats, summary, companion) → field{8参数}
 * 边界覆盖：全零输入、超大值、未知 stage、非法输入不抛错
 */

import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { computeField, neutralField } from '../src/views/agent/fable/useCompositionField.js'

/* ---------------------------- 夹具 ---------------------------- */

// 最常见的"正常运行"数据
// stage 真实取值（DecisionLoopService.STAGES）：ANALYZE → MEMORIZE → DECIDE → REVIEW → LEARNED
const NORMAL_LOOPS = [
  { id: 'l1', stage: 'ANALYZE', requiresHuman: false, createdAt: '2026-11-14T10:00:00Z', reviewedAt: '2026-11-14T10:02:30Z' },
  { id: 'l2', stage: 'ANALYZE', requiresHuman: false, createdAt: '2026-11-14T09:30:00Z', reviewedAt: '2026-11-14T09:34:12Z' },
  { id: 'l3', stage: 'DECIDE',  requiresHuman: true,  createdAt: '2026-11-14T08:00:00Z', updatedAt: '2026-11-14T08:05:00Z' },
]
const NORMAL_STATS = {
  total: 42, reviewed: 38, resolved: 36, learnedCount: 57,
  resolveRate: 0.86,
  byStage: [
    { stage: 'ANALYZE', count: 15 },
    { stage: 'MEMORIZE', count: 6 },
    { stage: 'DECIDE',  count: 8 },
    { stage: 'REVIEW',  count: 6 },
    { stage: 'LEARNED', count: 7 },
  ]
}
const NORMAL_SUMMARY = { total: 100, pass: 92, warning: 3, high: 1, critical: 0 }
const NORMAL_COMPANION = { states: { whale: 'IDLE' } }

/* ---------------------------- 主逻辑 ---------------------------- */

describe('computeField — 正常运行', () => {
  it('返回八个参数字段，类型全部正确', () => {
    const f = computeField(NORMAL_LOOPS, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.ok(typeof f.aperture === 'number')
    assert.ok(typeof f.tilt === 'number')
    assert.ok(typeof f.volume === 'number')
    assert.ok(typeof f.spin === 'number')
    assert.ok(typeof f.groove === 'number')
    assert.ok(typeof f.grain === 'number')
    assert.ok(typeof f.gaze.x === 'number')
    assert.ok(typeof f.gaze.y === 'number')
    assert.ok(typeof f.pulse === 'number')
  })

  it('所有参数落在 DESIGN §2 规定的区间内', () => {
    const f = computeField(NORMAL_LOOPS, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.ok(f.aperture >= 0.40 && f.aperture <= 1.20, `aperture ${f.aperture} 越界`)
    assert.ok(f.tilt >= -34 && f.tilt <= -6, `tilt ${f.tilt} 越界`)
    assert.ok(f.volume >= 0.85 && f.volume <= 1.15, `volume ${f.volume} 越界`)
    assert.ok(f.spin >= 0 && f.spin <= 1, `spin ${f.spin} 越界`)
    assert.ok(f.groove >= 8 && f.groove <= 48, `groove ${f.groove} 越界`)
    assert.ok(Number.isInteger(f.groove), `groove 不是整数: ${f.groove}`)
    assert.ok(f.grain >= 0 && f.grain <= 1, `grain ${f.grain} 越界`)
    assert.ok(f.gaze.x >= -1 && f.gaze.x <= 1, `gaze.x ${f.gaze.x} 越界`)
    assert.ok(f.gaze.y >= -1 && f.gaze.y <= 1, `gaze.y ${f.gaze.y} 越界`)
    assert.ok(f.pulse >= 2.4 && f.pulse <= 6.0, `pulse ${f.pulse} 越界`)
  })

  it('ANALYZE 主导 → tilt 往 −21° 靠拢', () => {
    const byStage = [{ stage: 'ANALYZE', count: 20 }, { stage: 'DECIDE', count: 2 }]
    const f = computeField([], { ...NORMAL_STATS, byStage }, NORMAL_SUMMARY, NORMAL_COMPANION)
    // 加权平均 = (−21×20 + −7×2)/22 ≈ −19.7
    assert.ok(f.tilt < -15, `ANALYZE 主导时 tilt 应 < −15°，实际 ${f.tilt}°`)
  })

  it('DECIDE 主导 → tilt 往 −7° 靠拢（倾角最平）', () => {
    const byStage = [{ stage: 'DECIDE', count: 20 }, { stage: 'LEARNED', count: 3 }]
    const f = computeField([], { ...NORMAL_STATS, byStage }, NORMAL_SUMMARY, NORMAL_COMPANION)
    // 加权 = (−7×20 + −12×3)/23 ≈ −7.7°
    assert.ok(f.tilt > -14, `DECIDE 主导时 tilt 应 > −14°，实际 ${f.tilt}°`)
  })

  it('high+critical 增大 → aperture 收窄（单调递减）', () => {
    const s1 = { ...NORMAL_SUMMARY, high: 0, critical: 0 }
    const s2 = { ...NORMAL_SUMMARY, high: 4, critical: 2 }
    const f1 = computeField([], NORMAL_STATS, s1, NORMAL_COMPANION)
    const f2 = computeField([], NORMAL_STATS, s2, NORMAL_COMPANION)
    assert.ok(f2.aperture < f1.aperture,
      `告警多时孔径应收窄，但 ${f2.aperture} >= ${f1.aperture}`)
  })

  it('warning 增大 → spin 增大（单调递增）', () => {
    const s1 = { ...NORMAL_SUMMARY, warning: 0 }
    const s2 = { ...NORMAL_SUMMARY, warning: 5 }
    const f1 = computeField([], NORMAL_STATS, s1, NORMAL_COMPANION)
    const f2 = computeField([], NORMAL_STATS, s2, NORMAL_COMPANION)
    assert.ok(f2.spin > f1.spin,
      `warning 多时 spin 应增大，但 ${f2.spin} <= ${f1.spin}`)
  })

  it('learnedCount 增大 → groove 加密（单调递增）', () => {
    const st1 = { ...NORMAL_STATS, learnedCount: 0 }
    const st2 = { ...NORMAL_STATS, learnedCount: 200 }
    const f1 = computeField([], st1, NORMAL_SUMMARY, NORMAL_COMPANION)
    const f2 = computeField([], st2, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.ok(f2.groove > f1.groove,
      `learnedCount 多时 groove 应加密，但 ${f2.groove} <= ${f1.groove}`)
  })

  it('有 requiresHuman loop → gaze.y < 0（往上看）', () => {
    const loops = [{ stage: 'DECIDE', requiresHuman: true }]
    const f = computeField(loops, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.ok(f.gaze.y < 0, `有 requiresHuman 时 gaze.y 应 < 0，实际 ${f.gaze.y}`)
  })

  it('无告警且无 requiresHuman → gaze 回正 (0, 0)', () => {
    const summary = { ...NORMAL_SUMMARY, high: 0, critical: 0 }
    const f = computeField([], NORMAL_STATS, summary, NORMAL_COMPANION)
    assert.equal(f.gaze.x, 0)
    assert.equal(f.gaze.y, 0)
  })

  it('runtime DEGRADED → tilt 往 −7° 靠（无 byStage 时）', () => {
    const f = computeField([], { ...NORMAL_STATS, byStage: [] }, NORMAL_SUMMARY, { states: { whale: 'DEGRADED' } })
    // DECIDE target = −7
    assert.ok(f.tilt >= -10 && f.tilt <= -4, `DEGRADED 时 tilt 应在 −7° 附近，实际 ${f.tilt}`)
  })

  it('有 createdAt/reviewedAt → pulse 不为默认 4.0', () => {
    // 数据库无 started_at/ended_at，用 reviewedAt - createdAt 作为闭环时长
    const long = [
      { stage: 'ANALYZE', createdAt: '2026-11-14T10:00:00Z', reviewedAt: '2026-11-14T10:15:00Z' }, // 15min
      { stage: 'ANALYZE', createdAt: '2026-11-14T09:00:00Z', reviewedAt: '2026-11-14T09:10:00Z' }, // 10min
    ]
    const f = computeField(long, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION)
    // avg 12.5min = 750s → 归一上限 600s → pulse ≈ 6.0
    assert.ok(f.pulse >= 2.4 && f.pulse <= 6.0)
  })
})

/* ---------------------------- 边界 ---------------------------- */

describe('computeField — 边界输入', () => {
  it('全空输入 → 返回中性值（不是全 0）', () => {
    const f = neutralField()
    assert.ok(f.aperture > 1.0, '中性 aperture 应接近 1.0')
    assert.ok(f.tilt < -6, '中性 tilt 应在负值区')
    assert.ok(f.volume >= 0.85 && f.volume <= 1.0)
    assert.equal(f.groove, 8) // learnedCount=0 → 8
    assert.equal(f.spin, 0)  // warning=0 → 0
    assert.equal(f.pulse, 4.0) // 无闭环时长 → 默认
  })

  it('超大值不越界', () => {
    const stats = { total: 999999, learnedCount: 999999, resolveRate: 1 }
    const summary = { high: 9999, critical: 9999, warning: 9999 }
    const f = computeField([], stats, summary, NORMAL_COMPANION)
    assert.ok(f.aperture >= 0.40 && f.aperture <= 1.20)
    assert.ok(f.tilt >= -34 && f.tilt <= -6)
    assert.ok(f.volume >= 0.85 && f.volume <= 1.15)
    assert.ok(f.spin >= 0 && f.spin <= 1)
    assert.ok(f.groove >= 8 && f.groove <= 48)
    assert.ok(f.grain >= 0 && f.grain <= 1)
    assert.ok(f.pulse >= 2.4 && f.pulse <= 6.0)
  })

  it('全零数值 → 不越界、不抛错', () => {
    const f = computeField([], { total: 0, learnedCount: 0, resolveRate: 0 }, { high: 0, critical: 0, warning: 0 }, NORMAL_COMPANION)
    assert.ok(f.aperture >= 0.40 && f.aperture <= 1.20)
    assert.ok(f.groove === 8)
    assert.ok(f.spin === 0)
  })

  it('未知 stage 值 → 归为 ANALYZE，不抛错', () => {
    const byStage = [
      { stage: 'UNKNOWN_PHASE', count: 10 },
      { stage: 'ANALYZE', count: 10 },
      { stage: 'PENDING', count: 5 },
    ]
    let f
    assert.doesNotThrow(() => {
      f = computeField([], { ...NORMAL_STATS, byStage }, NORMAL_SUMMARY, NORMAL_COMPANION)
    })
    assert.ok(f.tilt >= -34 && f.tilt <= -6)
  })

  it('完全非法输入（null, 字符串, NaN）→ 不抛错、不越界', () => {
    let f
    assert.doesNotThrow(() => {
      f = computeField(null, null, null, null)
    })
    assert.ok(f.aperture >= 0.40 && f.aperture <= 1.20)
    assert.ok(Number.isFinite(f.tilt))
    assert.ok(Number.isFinite(f.volume))
    assert.ok(Number.isFinite(f.pulse))
  })

  it('byStage 为空数组 → 用默认 tilt 或 runtimeDegraded 近似', () => {
    const f1 = computeField([], { ...NORMAL_STATS, byStage: [] }, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.ok(f1.tilt < -6)
  })

  it('loops 无 createdAt/reviewedAt → pulse 保持默认 4.0', () => {
    const loops = [{ stage: 'ANALYZE' }, { stage: 'DECIDE' }] // 无时间字段
    const f = computeField(loops, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION)
    assert.equal(f.pulse, 4.0)
  })
})

/* ---------------------------- 确定性 ---------------------------- */

describe('computeField — 确定性', () => {
  it('相同输入 → 输出完全相同（纯函数无随机性）', () => {
    const inputs = [NORMAL_LOOPS, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION]
    const a = computeField(...inputs)
    const b = computeField(...inputs)
    assert.deepEqual(a, b)
  })

  it('多次调用相同结果（100 次）', () => {
    const inputs = [NORMAL_LOOPS, NORMAL_STATS, NORMAL_SUMMARY, NORMAL_COMPANION]
    const first = JSON.stringify(computeField(...inputs))
    for (let i = 0; i < 100; i++) {
      assert.equal(JSON.stringify(computeField(...inputs)), first)
    }
  })
})
