import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import {
  createFrameBudget,
  frameDeltaSeconds,
  SLOW_FRAME_MS,
  SLOW_INTERVAL_MS,
  SLOW_WINDOW_MS
} from '../src/components/persona/frameBudget.js'

/** 假时钟：完全确定，不依赖真实时间 */
function harness(start = 0) {
  let clock = start
  const budget = createFrameBudget({ now: () => clock })
  return {
    budget,
    at(time, cost, interval) {
      clock = time
      return budget.sample(cost, interval)
    }
  }
}

test('帧预算常量与文档一致', () => {
  assert.equal(SLOW_FRAME_MS, 20)
  assert.equal(SLOW_INTERVAL_MS, 60)
  assert.equal(SLOW_WINDOW_MS, 2000)
})

test('GPU 瓶颈回归：间隔 66ms、CPU 成本很低，连续 2s 后触发降级', () => {
  const { at, budget } = harness(1000)
  let triggeredAt = null
  for (let time = 1000; time <= 4000; time += 66) {
    if (at(time, 1.5, 66)) triggeredAt = time
  }
  assert.equal(budget.degraded, true)
  // 采样点按 66ms 步进，不会正好落在 3000ms 上；允许一个采样间隔的误差
  assert.ok(triggeredAt - 1000 >= SLOW_WINDOW_MS && triggeredAt - 1000 < SLOW_WINDOW_MS + 66)
})

test('回归对照：喂 rAF 间隔（16.7ms）永远不会触发，这正是修复前的盲区', () => {
  const { at, budget } = harness(0)
  for (let time = 0; time <= 6000; time += 16.7) at(time, 1.5, 16.7)
  assert.equal(budget.degraded, false)
})

test('CPU 成本门槛仍然保留：成本 > 20ms 持续 2s 也降级', () => {
  const { at, budget } = harness(500)
  assert.equal(at(500, 25, 16), false)
  assert.equal(at(2400, 25, 16), false)
  assert.equal(at(2500, 25, 16), true)
  assert.equal(budget.degraded, true)
})

test('任一样本回落到门槛内就清零计时，之后必须重新累计 2s', () => {
  const { at, budget } = harness(0)
  at(0, 25, 16)
  at(600, 25, 16)
  at(1200, 25, 16)
  at(1800, 25, 16)
  at(1900, 5, 16) // 成本回落，清零
  at(2500, 25, 16) // 重新开始累计
  assert.equal(budget.degraded, false)
  at(4300, 25, 16)
  assert.equal(budget.degraded, false)
  assert.equal(at(4500, 25, 16), true)
})

test('帧间隔门槛按 >=60ms 判定，59.9ms 不算慢帧', () => {
  const slow = harness(0)
  for (let time = 0; time <= 3000; time += 59.9) slow.at(time, 1, 59.9)
  assert.equal(slow.budget.degraded, false)

  const boundary = harness(0)
  for (let time = 0; time <= 3000; time += 60) boundary.at(time, 1, 60)
  assert.equal(boundary.budget.degraded, true)
})

test('只会在越过门槛的那一帧返回一次 true', () => {
  const { at, budget } = harness(0)
  assert.equal(at(0, 1, 66), false)
  assert.equal(at(2000, 1, 66), true)
  assert.equal(at(2100, 1, 66), false)
  assert.equal(at(2200, 90, 200), false)
  assert.equal(budget.degraded, true)
})

test('时钟从 0 开始时也能正确累计（哨兵不能是 0）', () => {
  const { at, budget } = harness(0)
  assert.equal(at(0, 30, 66), false)
  assert.equal(at(2000, 30, 66), true)
  assert.equal(budget.degraded, true)
})

test('frameDeltaSeconds：毫秒转秒，并封顶 100ms', () => {
  assert.equal(frameDeltaSeconds(16), 0.016)
  assert.ok(Math.abs(frameDeltaSeconds(66.7) - 0.0667) < 1e-9)
  assert.equal(frameDeltaSeconds(100), 0.1)
  assert.equal(frameDeltaSeconds(150), 0.1)
  assert.equal(frameDeltaSeconds(0), 0)
  assert.equal(frameDeltaSeconds(-5), 0)
})

test('舞台接线回归：dt 与看门狗都用真实渲染间隔，而非调度器回调参数', async () => {
  const source = await readFile(new URL('../src/components/persona/useVrmModel.js', import.meta.url), 'utf8')
  assert.match(source, /const interval = lastStepAt \? timestamp - lastStepAt : 16/)
  assert.match(source, /const dt = frameDeltaSeconds\(interval\)/)
  assert.match(source, /frameBudget\.sample\(cost, interval\)/)
  assert.doesNotMatch(source, /watchFrameBudget/)
})
