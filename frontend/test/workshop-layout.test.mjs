/**
 * test/workshop-layout.test.mjs
 *
 * Agent 工坊布局纯函数单测（T28，EXECUTION-PACK 验收）：
 * 工位不重叠、轨道四站闭合、iso 换算往返一致、窄屏退化阈值、
 * 真实闭环 → 工位映射、sparkline 提取、非法输入不抛错。
 */

import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildWorkshop,
  iso,
  inverseIso,
  isNarrowViewport,
  NARROW_VIEWPORT_MAX,
  deskActivity,
  sparklineFromLoops,
  loopDuration
} from '../src/views/agent/fable/workshop/workshopLayout.js'

/* ---------------------------- 夹具 ---------------------------- */

const TOOLS = Object.freeze([
  { cn: '混合检索', en: 'HYBRID RETRIEVAL', tone: 'sage' },
  { cn: '风险策略', en: 'RISK POLICY', tone: 'clay' },
  { cn: '人工审批', en: 'HUMAN GATE', tone: 'butter' },
  { cn: '安全执行', en: 'EXECUTOR', tone: 'apricot' },
  { cn: '结果核查', en: 'INSPECTOR', tone: 'gaze' },
  { cn: '审计留痕', en: 'AUDIT TRAIL', tone: 'plum' }
])

const LOOP_STEPS = Object.freeze([
  { cn: '感知', en: 'PERCEIVE' },
  { cn: '规划', en: 'PLAN' },
  { cn: '执行', en: 'ACT' },
  { cn: '核查', en: 'VERIFY' }
])

const dist = (a, b) => Math.hypot(a.sx - b.sx, a.sy - b.sy)

/* ---------------------------- 布局 ---------------------------- */

describe('buildWorkshop — 工位布局', () => {
  it('产出 6 张工位，2 行 × 3 列，id/tone/label 完整', () => {
    const w = buildWorkshop(TOOLS, LOOP_STEPS)
    assert.equal(w.desks.length, 6)
    const rows = new Set(w.desks.map(d => d.row))
    const cols = new Set(w.desks.map(d => d.col))
    assert.equal(rows.size, 2)
    assert.equal(cols.size, 3)
    for (const desk of w.desks) {
      assert.ok(desk.id, '缺少 id')
      assert.ok(desk.tone, '缺少 tone')
      assert.ok(desk.labelCn, '缺少中文标签')
      assert.ok(Number.isFinite(desk.sx) && Number.isFinite(desk.sy), '屏幕坐标非法')
    }
    assert.equal(w.desks[0].id, 'hybrid-retrieval')
    assert.equal(w.desks[5].id, 'audit-trail')
  })

  it('任意两张工位屏幕距离 ≥ 100（不重叠）', () => {
    const w = buildWorkshop(TOOLS, LOOP_STEPS)
    for (let i = 0; i < w.desks.length; i++) {
      for (let j = i + 1; j < w.desks.length; j++) {
        const d = dist(w.desks[i], w.desks[j])
        assert.ok(d >= 100, `工位 ${w.desks[i].id} 与 ${w.desks[j].id} 距离 ${d.toFixed(1)} < 100`)
      }
    }
  })

  it('轨道四站闭合：相邻站距在 [20, 160]，首尾相连', () => {
    const w = buildWorkshop(TOOLS, LOOP_STEPS)
    assert.equal(w.track.length, 4)
    for (let i = 0; i < w.track.length; i++) {
      const next = w.track[(i + 1) % w.track.length]
      const d = dist(w.track[i], next)
      assert.ok(d >= 20 && d <= 160, `第 ${i}→${(i + 1) % 4} 站间距 ${d.toFixed(1)} 越界`)
    }
  })

  it('轨道站与工位距离 ≥ 55（不压桌）', () => {
    const w = buildWorkshop(TOOLS, LOOP_STEPS)
    for (const desk of w.desks) {
      for (const station of w.track) {
        const d = dist(desk, station)
        assert.ok(d >= 55, `${desk.id} 与轨道站 ${station.en} 距离 ${d.toFixed(1)} < 55`)
      }
    }
  })

  it('所有锚点都落在 viewBox 内，宽高为正', () => {
    const w = buildWorkshop(TOOLS, LOOP_STEPS)
    const { x, y, width, height } = w.viewBox
    assert.ok(width > 0 && height > 0)
    const inside = p =>
      p.sx >= x - 1 && p.sx <= x + width + 1 && p.sy >= y - 1 && p.sy <= y + height + 1
    for (const p of [...w.desks, ...w.track, w.screen, w.cabinet, ...w.floor]) {
      assert.ok(inside(p), `锚点 (${p.sx}, ${p.sy}) 越出 viewBox`)
    }
  })

  it('空输入不抛错，返回空工位与有效 viewBox', () => {
    const w = buildWorkshop([], [])
    assert.equal(w.desks.length, 0)
    assert.ok(w.viewBox.width >= 0 && w.viewBox.height >= 0)
  })
})

/* ---------------------------- iso 换算 ---------------------------- */

describe('iso / inverseIso — 2:1 轴测', () => {
  it('往返一致（z = 0/1/2.4 抽样）', () => {
    for (const z of [0, 1, 2.4]) {
      for (const [x, y] of [[0, 0], [6, 4], [11.2, 0.4], [2.4, 6.6]]) {
        const p = iso(x, y, z)
        const back = inverseIso(p.sx, p.sy, z)
        assert.ok(Math.abs(back.x - x) < 1e-9, `x 往返失配: ${back.x} ≠ ${x}`)
        assert.ok(Math.abs(back.y - y) < 1e-9, `y 往返失配: ${back.y} ≠ ${y}`)
      }
    }
  })

  it('2:1 特性：dx = −dy 时 sy 增量为 0（水平等距线）', () => {
    const a = iso(2, 2, 0)
    const b = iso(3, 1, 0)
    assert.equal(b.sx - a.sx, 64)
    assert.equal(b.sy - a.sy, 0)
  })
})

/* ---------------------------- 窄屏阈值 ---------------------------- */

describe('isNarrowViewport — 门禁 4', () => {
  it('768 及以上不退化，767 以下退化', () => {
    assert.equal(isNarrowViewport(NARROW_VIEWPORT_MAX), false)
    assert.equal(isNarrowViewport(1280), false)
    assert.equal(isNarrowViewport(767), true)
    assert.equal(isNarrowViewport(360), true)
    assert.equal(isNarrowViewport(undefined), true)
  })
})

/* ---------------------------- 真实闭环映射 ---------------------------- */

describe('deskActivity — stage → 工位映射（禁假繁忙的数据基座）', () => {
  it('ANALYZE→混合检索；MEMORIZE→审计留痕；REVIEW→结果核查；LEARNED→审计留痕', () => {
    const act = deskActivity([
      { id: 'L1', stage: 'ANALYZE' },
      { id: 'L2', stage: 'MEMORIZE' },
      { id: 'L3', stage: 'REVIEW' },
      { id: 'L4', stage: 'LEARNED' }
    ])
    const byDesk = Object.fromEntries(act.map(a => [a.deskId, a.loopId]))
    assert.equal(byDesk['hybrid-retrieval'], 'L1')
    assert.equal(byDesk['audit-trail'], 'L2')
    assert.equal(byDesk['inspector'], 'L3')
    // LEARNED 与 MEMORIZE 都映射审计留痕，只保留先到的一条（byDesk 去重）
    assert.equal(act.filter(a => a.deskId === 'audit-trail').length, 1)
  })

  it('DECIDE + requiresHuman → 风险策略 + 人工审批', () => {
    const act = deskActivity([{ id: 'L9', stage: 'DECIDE', requiresHuman: true }])
    const ids = act.map(a => a.deskId).sort()
    assert.deepEqual(ids, ['human-gate', 'risk-policy'])
  })

  it('DECIDE 已出决策 → 风险策略 + 安全执行', () => {
    const act = deskActivity([{ id: 'L8', stage: 'DECIDE', decision: '扩容' }])
    const ids = act.map(a => a.deskId).sort()
    assert.deepEqual(ids, ['executor', 'risk-policy'])
  })

  it('非法输入不抛错', () => {
    assert.deepEqual(deskActivity(null), [])
    assert.deepEqual(deskActivity('x'), [])
    assert.deepEqual(deskActivity([null, 42, {}]), [])
  })
})

/* ---------------------------- sparkline ---------------------------- */

describe('sparklineFromLoops — 墙屏折线（E4，真实数据）', () => {
  it('按创建时间从旧到新，取近 N 条，单位秒', () => {
    const loops = Array.from({ length: 16 }, (_, i) => ({
      id: `L${i}`,
      createdAt: `2026-11-14T10:0${i % 10}:00Z`,
      updatedAt: `2026-11-14T10:0${i % 10}:30Z` // 30s
    }))
    const line = sparklineFromLoops(loops, 12)
    assert.equal(line.length, 12)
    for (const v of line) assert.equal(v, 30)
  })

  it('跳过无效记录；全无效返回空数组', () => {
    assert.deepEqual(
      sparklineFromLoops([{ id: 'L1' }, { createdAt: '2026-11-14T10:00:00Z' }, null]),
      []
    )
    assert.deepEqual(sparklineFromLoops(null), [])
  })

  it('loopDuration：负值/缺失返回 null', () => {
    assert.equal(loopDuration({ createdAt: '2026-11-14T10:00:00Z', updatedAt: '2026-11-14T09:00:00Z' }), null)
    assert.equal(loopDuration({ updatedAt: '2026-11-14T10:00:00Z' }), null)
    const ok = loopDuration({ createdAt: '2026-11-14T10:00:00Z', updatedAt: '2026-11-14T10:01:00Z' })
    assert.equal(ok, 60000)
  })
})
