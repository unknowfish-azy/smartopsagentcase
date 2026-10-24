// 蜘蛛巡网引擎单测：蛛网生成（确定性/结构/连通）、蜘蛛行走（推进/择路/边界）、
// 步态换脚、restPose 静态姿态、长时间模拟无 NaN。
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  chooseNextSegment,
  createRng,
  createSpider,
  createWeb,
  legsStepping,
  restPose,
  stepSpider
} from '../src/components/effects/spiderCrawler.js'

test('createRng is deterministic for the same seed', () => {
  const a = createRng(42)
  const b = createRng(42)
  const seqA = [a(), a(), a(), a()]
  const seqB = [b(), b(), b(), b()]
  assert.deepEqual(seqA, seqB)
  assert.notEqual(seqA[0], seqA[1])
})

test('createWeb is deterministic and has the expected structure', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42, spokes: 10, rings: 4 })
  const again = createWeb({ width: 800, height: 400, seed: 42, spokes: 10, rings: 4 })
  assert.equal(web.segments.length, again.segments.length)
  assert.deepEqual(web.segments.map(s => [s.ax, s.ay, s.bx, s.by]), again.segments.map(s => [s.ax, s.ay, s.bx, s.by]))
  // 辐条段 + 环段 = spokes*rings*2
  assert.equal(web.segments.length, 10 * 4 * 2)
  // 所有端点都在画布内
  for (const seg of web.segments) {
    assert.ok(seg.ax >= 0 && seg.ax <= 800 && seg.ay >= 0 && seg.ay <= 400)
    assert.ok(seg.bx >= 0 && seg.bx <= 800 && seg.by >= 0 && seg.by <= 400)
    assert.ok(seg.length >= 1)
  }
})

test('web adjacency connects every segment end and includes the center', () => {
  const web = createWeb({ width: 800, height: 400, seed: 7, spokes: 8, rings: 3 })
  assert.ok(web.adjacency.has('center'))
  assert.ok(web.adjacency.get('center').length >= 8, 'center connects all spokes')
  // 每个节点：内圈环节点 = 2 根辐条 + 2 条环线 = 4；最外圈 = 1 根辐条 + 2 条环线 = 3
  for (const [key, links] of web.adjacency) {
    if (key === 'center') continue
    const [, ring] = key.split(':').map(Number)
    assert.equal(links.length, ring === web.ringCount - 1 ? 3 : 4, `ring node ${key} link count`)
  }
})

test('spider starts on a segment with 8 planted legs', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42 })
  const spider = createSpider(web, createRng(99))
  assert.equal(spider.legs.length, 8)
  assert.ok(spider.t > 0 && spider.t < 1)
  assert.ok(web.segments[spider.segIndex], 'segIndex valid')
  for (const leg of spider.legs) {
    assert.ok(Number.isFinite(leg.footX) && Number.isFinite(leg.footY))
    assert.equal(leg.stepping, false)
    const dist = Math.hypot(leg.footX - spider.bodyX, leg.footY - spider.bodyY)
    assert.ok(dist <= leg.hipDist + leg.reach + 2, 'initial foot within leg span')
  }
})

test('stepSpider advances the body along the web', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42 })
  const spider = createSpider(web, createRng(99))
  const rng = createRng(5)
  const x0 = spider.bodyX
  const y0 = spider.bodyY
  for (let i = 0; i < 30; i += 1) stepSpider(spider, web, 1 / 30, rng)
  const moved = Math.hypot(spider.bodyX - x0, spider.bodyY - y0)
  assert.ok(moved > 10, `body moved ${moved}px after 1s at 34px/s`)
})

test('spider stays on the web and never produces NaN over a long crawl', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42 })
  const spider = createSpider(web, createRng(99))
  const rng = createRng(5)
  for (let i = 0; i < 60 * 120; i += 1) { // 模拟 2 分钟
    stepSpider(spider, web, 1 / 60, rng)
    assert.ok(Number.isFinite(spider.bodyX) && Number.isFinite(spider.bodyY), `NaN at frame ${i}`)
    assert.ok(spider.t >= 0 && spider.t <= 1, 't stays within segment')
    const onWeb = spider.bodyX >= -1 && spider.bodyX <= web.width + 1 && spider.bodyY >= -1 && spider.bodyY <= web.height + 1
    assert.ok(onWeb, 'body stays within canvas bounds')
  }
  assert.ok(web.segments[spider.segIndex], 'segIndex valid after transitions')
})

test('chooseNextSegment returns a connected segment, never the current one', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42 })
  const spider = createSpider(web, createRng(99))
  const rng = createRng(11)
  for (let i = 0; i < 40; i += 1) {
    const seg = web.segments[spider.segIndex]
    const next = chooseNextSegment(web, spider, rng)
    assert.notEqual(next.segIndex, seg.index, 'does not pick the segment it is on')
    assert.ok(web.segments[next.segIndex], 'next segment exists')
    assert.ok(next.dir === 1 || next.dir === -1)
    // 模拟走到头并换段，驱动择路覆盖更多节点
    spider.segIndex = next.segIndex
    spider.dir = next.dir
    spider.t = next.dir > 0 ? 0.95 : 0.05
  }
})

test('legs step while walking and settle on restPose', () => {
  const web = createWeb({ width: 800, height: 400, seed: 42 })
  const spider = createSpider(web, createRng(99))
  const rng = createRng(5)
  const feetBefore = spider.legs.map(leg => [leg.footX, leg.footY])
  let stepped = false
  for (let i = 0; i < 60; i += 1) {
    stepSpider(spider, web, 1 / 60, rng)
    if (legsStepping(spider) > 0) stepped = true
  }
  assert.ok(stepped, 'legs engage stepping during locomotion')
  const moved = spider.legs.some((leg, index) => Math.hypot(leg.footX - feetBefore[index][0], leg.footY - feetBefore[index][1]) > 4)
  assert.ok(moved, 'feet relocated while walking')
  restPose(spider, web)
  assert.equal(legsStepping(spider), 0)
  for (const leg of spider.legs) {
    const dist = Math.hypot(leg.footX - spider.bodyX, leg.footY - spider.bodyY)
    assert.ok(dist <= leg.hipDist + leg.reach + 2, 'rested foot within leg span')
  }
})

test('different seeds place spiders and webs differently', () => {
  const webA = createWeb({ width: 800, height: 400, seed: 1 })
  const webB = createWeb({ width: 800, height: 400, seed: 2 })
  assert.notDeepEqual(webA.segments, webB.segments)
})
