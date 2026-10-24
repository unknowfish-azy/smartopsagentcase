import assert from 'node:assert/strict'
import test from 'node:test'
import {
  CALL_TIERS,
  TOKEN_TIERS,
  buildAchievements,
  callMilestoneReached,
  DEMO_ACHIEVEMENTS
} from '../src/components/celebrate/achievements.js'
import {
  createCoin,
  createMotes,
  createRng,
  createWorld,
  fadeCoins,
  milestoneProgress,
  stepCoin,
  stepMotes,
  vesselGeometry
} from '../src/components/effects/milestoneRain.js'

test('createRng is deterministic and bounded', () => {
  const a = createRng(42)
  const b = createRng(42)
  const seqA = Array.from({ length: 50 }, a)
  const seqB = Array.from({ length: 50 }, b)
  assert.deepEqual(seqA, seqB)
  assert.equal(seqA.every(value => value >= 0 && value < 1), true)
  assert.notDeepEqual(Array.from({ length: 50 }, createRng(43)), seqA)
})

test('stepCoin integrates gravity and falls', () => {
  const world = createWorld({ width: 400, height: 800, floorY: 794 })
  const coin = createCoin(createRng(7), world, 'rain')
  const y0 = coin.y
  const vy0 = coin.vy
  stepCoin(coin, 0.016, world)
  assert.ok(coin.vy > vy0) // 重力加速
  assert.ok(coin.y > y0) // 位置下落
})

test('coins bounce on the floor and settle to rest', () => {
  const world = createWorld({ width: 400, height: 400, floorY: 394 })
  const coin = createCoin(createRng(3), world, 'rain')
  coin.x = 200
  coin.y = 0
  coin.vy = 600
  coin.vx = 0
  coin.vr = 0
  let bounced = false
  for (let i = 0; i < 600 && coin.state !== 'settled'; i += 1) {
    stepCoin(coin, 0.016, world)
    if (coin.vy < 0) bounced = true
  }
  assert.ok(bounced) // 确实发生过弹跳
  assert.equal(coin.state, 'settled')
  assert.equal(coin.resting, true)
  assert.equal(coin.y + coin.size, 394) // 停在地板上
})

test('funnel captures coins through the mouth and stacks them per column', () => {
  const vessel = vesselGeometry(400, 400)
  const world = createWorld({ width: 400, height: 400, vessel, floorY: 900 })
  const drop = () => {
    const coin = createCoin(createRng(11), world, 'funnel')
    coin.x = 200
    coin.y = vessel.mouthY - 4
    coin.vy = 300
    coin.vx = 0
    coin.vr = 0
    stepCoin(coin, 0.016, world)
    return coin
  }
  const first = drop()
  assert.equal(first.state, 'captured')
  assert.equal(world.vessel.pile.reduce((sum, count) => sum + count, 0), 1)
  const second = drop()
  assert.equal(second.state, 'captured')
  assert.equal(second.column, first.column)
  assert.ok(second.y < first.y) // 同列第二枚叠在上方
})

test('vessel capacity overflows instead of stacking infinitely', () => {
  const vessel = vesselGeometry(400, 400)
  const world = createWorld({ width: 400, height: 400, vessel, floorY: 900 })
  const rng = createRng(5)
  let escaped = 0
  for (let i = 0; i < 40; i += 1) {
    const coin = createCoin(rng, world, 'funnel')
    coin.x = 200
    coin.y = vessel.mouthY - 4
    coin.vy = 300
    coin.vx = 0
    stepCoin(coin, 0.016, world)
    if (coin.state === 'escape') escaped += 1
  }
  assert.ok(Math.max(...world.vessel.pile) <= vessel.capacity) // 每列不超容量
  assert.ok(escaped > 0) // 袋满后溢出逃逸，不无限堆叠
})

test('fadeCoins retires settled coins without re-applying gravity', () => {
  const world = createWorld({ width: 400, height: 400, floorY: 394 })
  const coin = createCoin(createRng(9), world, 'rain')
  coin.x = 200
  coin.y = 384
  coin.vy = 0
  coin.vx = 0
  coin.vr = 0
  coin.state = 'settled'
  coin.resting = true
  fadeCoins([coin])
  assert.equal(coin.state, 'escape')
  assert.equal(coin.life, 0.5)
  const y = coin.y
  stepCoin(coin, 0.1, world)
  assert.equal(coin.y, y) // 躺平的金币只淡出，不再受力
  assert.ok(coin.alpha < 1)
  for (let i = 0; i < 10; i += 1) stepCoin(coin, 0.1, world)
  assert.equal(coin.state, 'dead')
})

test('captured coins fade out and die instead of sticking as settled', () => {
  // 回归：落地分支曾把淡出中的 escape 金币改写为 settled，而 settled 跳过寿命递减，
  // 导致庆祝结束后金币永死不了、finished 事件永不发出（浏览器测试 15s 超时抓到的）
  const vessel = vesselGeometry(400, 400)
  const world = createWorld({ width: 400, height: 400, vessel, floorY: 900 })
  const coin = createCoin(createRng(21), world, 'funnel')
  coin.x = 200
  coin.y = vessel.mouthY - 4
  coin.vy = 300
  coin.vx = 0
  coin.vr = 0
  stepCoin(coin, 0.016, world)
  assert.equal(coin.state, 'captured')
  fadeCoins([coin])
  assert.equal(coin.state, 'escape')
  for (let i = 0; i < 120 && coin.state !== 'dead'; i += 1) stepCoin(coin, 0.016, world)
  assert.equal(coin.state, 'dead')
})

test('coins falling past the world are culled', () => {
  const world = createWorld({ width: 400, height: 400, floorY: 900 })
  const coin = createCoin(createRng(4), world, 'rain')
  coin.y = 500
  stepCoin(coin, 0.016, world)
  assert.equal(coin.state, 'dead')
})

test('reduced motion worlds settle coins without integrating', () => {
  const world = createWorld({ width: 400, height: 400, floorY: 394, reducedMotion: true })
  const coin = createCoin(createRng(8), world, 'rain')
  const y = coin.y
  stepCoin(coin, 0.5, world)
  assert.equal(coin.state, 'settled')
  assert.equal(coin.y, y) // 不积分，直接落定
})

test('milestoneProgress tiers values and refuses to guess unknowns', () => {
  assert.deepEqual(milestoneProgress(1234, CALL_TIERS), { reached: 1000, next: 5000, progress: 1234 / 5000 })
  assert.deepEqual(milestoneProgress(99999, CALL_TIERS), { reached: 10000, next: null, progress: 1 })
  assert.deepEqual(milestoneProgress(50, CALL_TIERS), { reached: null, next: 100, progress: 0.5 })
  assert.deepEqual(milestoneProgress(null, CALL_TIERS), { reached: null, next: 100, progress: 0 })
  assert.deepEqual(milestoneProgress('abc', CALL_TIERS), { reached: null, next: 100, progress: 0 })
  assert.deepEqual(milestoneProgress(10, []), { reached: null, next: null, progress: 0 })
  assert.equal(milestoneProgress(5, TOKEN_TIERS).next, 10000)
})

const reportFixture = {
  month: '2026-10',
  timezone: 'UTC',
  summary: { calls: 1234, successes: 1200, failures: 30, pendingCalls: 0, unknownUsageCalls: 4, knownTokens: 284100, successRate: 97.2 }
}

test('buildAchievements derives tiers and quality milestones from the real ledger', () => {
  const list = buildAchievements(reportFixture)
  assert.equal(list.length, 11)
  const byId = Object.fromEntries(list.map(item => [item.id, item]))
  assert.equal(byId['calls-100'].unlocked, true)
  assert.equal(byId['calls-500'].unlocked, true)
  assert.equal(byId['calls-1000'].unlocked, true)
  assert.equal(byId['calls-5000'].unlocked, false)
  assert.ok(Math.abs(byId['calls-5000'].progress - 1234 / 5000) < 1e-9)
  assert.equal(byId['calls-5000'].isNext, true) // 下一档 = 第一个未达成项
  assert.equal(byId['tokens-10000'].unlocked, true)
  assert.equal(byId['tokens-100000'].unlocked, true)
  assert.equal(byId['tokens-1000000'].unlocked, false)
  assert.equal(byId['stable-month'].unlocked, true) // 97.2% ≥ 95% 且 1234 ≥ 100
  assert.equal(byId['zero-pending'].unlocked, true)
  assert.equal(byId['fully-metered'].unlocked, false) // 4 次用量未知
  assert.ok(Math.abs(byId['fully-metered'].progress - (1 - 4 / 1234)) < 1e-9)
  assert.equal(list.filter(item => item.isNext).length, 1)
  assert.equal(byId['calls-100'].window, '2026-10')
  assert.match(byId['calls-100'].basis, /口径/)
})

test('buildAchievements never guesses on missing or empty ledgers', () => {
  for (const input of [null, undefined, {}, { month: '2026-09' }, { summary: {} }]) {
    const list = buildAchievements(input)
    assert.equal(list.length, 11)
    assert.equal(list.every(item => !item.unlocked && item.progress === 0), true)
    assert.equal(list.filter(item => item.isNext).length, 1)
    assert.equal(list[0].window, input?.month || '未知月份')
  }
})

test('callMilestoneReached reports the highest reached tier only', () => {
  assert.equal(callMilestoneReached(50), null)
  assert.equal(callMilestoneReached(100), 100)
  assert.equal(callMilestoneReached(1234), 1000)
  assert.equal(callMilestoneReached(99999), 10000)
  assert.equal(callMilestoneReached(null), null)
})

test('DEMO_ACHIEVEMENTS stays isolated from the real ledger', () => {
  // 演示实例是固定样例：不进 buildAchievements、不参与下一档推导、id 不与真实项冲突
  const real = buildAchievements(reportFixture)
  const realIds = new Set(real.map(item => item.id))
  assert.equal(DEMO_ACHIEVEMENTS.length, 3)
  for (const item of DEMO_ACHIEVEMENTS) {
    assert.equal(item.demo, true)
    assert.equal(item.window, '演示')
    assert.match(item.basis, /演示数据/)
    assert.equal(item.isNext, false) // 永远不抢占真实「下一档」高亮
    assert.equal(realIds.has(item.id), false)
    assert.ok(item.progress >= 0 && item.progress <= 1)
  }
  // 三种卡片状态各至少一例，保证演示覆盖已达成 / 进行中 / 未解锁
  assert.equal(DEMO_ACHIEVEMENTS.some(item => item.unlocked), true)
  assert.equal(DEMO_ACHIEVEMENTS.some(item => !item.unlocked && item.progress > 0), true)
  assert.equal(DEMO_ACHIEVEMENTS.some(item => !item.unlocked && item.progress < 0.5), true)
  // 真实推导不受演示实例影响：任何输入下都只有 11 项、只有 1 个下一档
  for (const input of [null, reportFixture]) {
    const list = buildAchievements(input)
    assert.equal(list.length, 11)
    assert.equal(list.filter(item => item.isNext).length, 1)
    assert.equal(list.some(item => item.demo), false)
  }
})

// ── 持续动态演示（ambient）微尘粒子 ──

test('createMotes is deterministic and bounded', () => {
  const a = createMotes(createRng(7), 16, 400, 300)
  const b = createMotes(createRng(7), 16, 400, 300)
  assert.equal(a.length, 16)
  assert.deepEqual(a, b)
  for (const mote of a) {
    assert.ok(mote.x >= 0 && mote.x <= 400 && mote.y >= 0 && mote.y <= 300)
    assert.ok(mote.vy > 0 && mote.size > 0)
  }
  // 数量钳制：0..64
  assert.equal(createMotes(createRng(7), 999, 400, 300).length, 64)
  assert.equal(createMotes(createRng(7), -3, 400, 300).length, 0)
})

test('stepMotes floats upward and wraps at the top', () => {
  const fixed = createMotes(createRng(7), 4, 400, 300)
  // 抬高一颗到顶部附近，验证回卷
  fixed[0].y = 2
  const before = fixed[0].y
  stepMotes(fixed, 1, 300) // 1s：上浮 vy（6..20px）
  assert.ok(fixed[0].y > before, 'wrapped from top to bottom')
  const other = fixed[1]
  const y0 = other.y
  stepMotes(fixed, 0.5, 300)
  assert.ok(other.y < y0, 'mote rises over time')
  assert.ok(fixed.every(m => m.y <= 300 + 8), 'motes stay within vertical bounds after wrap')
  // dt 无效时不动的
  const frozen = fixed[2].y
  stepMotes(fixed, 0, 300)
  stepMotes(fixed, -1, 300)
  assert.equal(fixed[2].y, frozen)
})
