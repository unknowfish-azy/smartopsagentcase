import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  CLICK_WINDOW_MS,
  LONG_PRESS_MS,
  POKE_THRESHOLD,
  createClickClassifier,
  createIdleScheduler
} from '../src/components/persona/personaInteractions.js'

/**
 * 假时钟：替换工厂默认的 setTimeout/clearTimeout，测试逐段推进，
 * 期间产生的新到点任务按时间顺序继续执行（模拟真实定时器行为）。
 */
function createFakeClock() {
  const tasks = []
  let seq = 0
  const clock = {
    now: 0,
    schedule(fn, ms) {
      seq += 1
      tasks.push({ id: seq, at: clock.now + ms, fn })
      return seq
    },
    cancel(id) {
      const i = tasks.findIndex((t) => t.id === id)
      if (i >= 0) tasks.splice(i, 1)
    },
    /** 推进到 now + ms，把沿途所有到点任务按时间序跑完 */
    advance(ms) {
      const target = clock.now + ms
      for (;;) {
        const due = tasks.filter((t) => t.at <= target).sort((a, b) => a.at - b.at)
        if (!due.length) break
        const t = due[0]
        tasks.splice(tasks.findIndex((x) => x.id === t.id), 1)
        clock.now = Math.max(clock.now, t.at)
        t.fn()
      }
      clock.now = target
    },
    pending: () => tasks.length
  }
  return clock
}

function createRecorder() {
  const calls = []
  return {
    calls,
    onSingle: () => calls.push('single'),
    onDouble: () => calls.push('double'),
    onPoke: (n) => calls.push(`poke:${n}`),
    onStretch: () => calls.push('stretch'),
    onSleep: () => calls.push('sleep')
  }
}

describe('点击分级状态机（createClickClassifier）', () => {
  test('单击：判定窗到点才触发（延迟结算）', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const classifier = createClickClassifier(rec, { schedule: clock.schedule, cancel: clock.cancel })

    classifier.feed()
    assert.deepEqual(rec.calls, [], '窗口未到点不应触发')
    clock.advance(CLICK_WINDOW_MS - 1)
    assert.deepEqual(rec.calls, [])
    clock.advance(1)
    assert.deepEqual(rec.calls, ['single'])
  })

  test('双击：窗内第二击改判 double', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const classifier = createClickClassifier(rec, { schedule: clock.schedule, cancel: clock.cancel })

    classifier.feed()
    clock.advance(100)
    classifier.feed()
    clock.advance(CLICK_WINDOW_MS)
    assert.deepEqual(rec.calls, ['double'])
  })

  test(`连击 ≥ ${POKE_THRESHOLD}（戳）：触发 poke 且计数清零`, () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const classifier = createClickClassifier(rec, { schedule: clock.schedule, cancel: clock.cancel })

    for (let i = 0; i < POKE_THRESHOLD; i += 1) {
      classifier.feed()
      clock.advance(80)
    }
    clock.advance(CLICK_WINDOW_MS)
    assert.deepEqual(rec.calls, [`poke:${POKE_THRESHOLD}`])

    // 结算后再单击应回到 single，不会残留连击计数
    classifier.feed()
    clock.advance(CLICK_WINDOW_MS)
    assert.deepEqual(rec.calls, [`poke:${POKE_THRESHOLD}`, 'single'])
  })

  test('3 连击失手回落为单击反馈（不出现"点了没反应"）', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const classifier = createClickClassifier(rec, { schedule: clock.schedule, cancel: clock.cancel })

    for (let i = 0; i < 3; i += 1) {
      classifier.feed()
      clock.advance(80)
    }
    clock.advance(CLICK_WINDOW_MS)
    assert.deepEqual(rec.calls, ['single'])
  })

  test('dispose 丢弃累计且不触发回调；flushNow 立即结算', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const classifier = createClickClassifier(rec, { schedule: clock.schedule, cancel: clock.cancel })

    classifier.feed()
    classifier.feed()
    classifier.dispose()
    clock.advance(CLICK_WINDOW_MS * 2)
    assert.deepEqual(rec.calls, [], 'dispose 后不应有任何回调')

    classifier.feed()
    classifier.flushNow()
    assert.deepEqual(rec.calls, ['single'])
    assert.equal(clock.pending(), 0, 'flushNow 应撤销判定窗定时器')
  })

  test('常量口径：判定窗/长按/戳阈值与文档一致', () => {
    assert.equal(CLICK_WINDOW_MS, 320)
    assert.equal(LONG_PRESS_MS, 600)
    assert.equal(POKE_THRESHOLD, 4)
  })
})

describe('挂机彩蛋调度器（createIdleScheduler）', () => {
  test('时间轴：stretchMs → 伸懒腰(stage1)，再 sleepMs → 打瞌睡(stage2)并循环', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const scheduler = createIdleScheduler(rec, {
      stretchMs: 1000,
      sleepMs: 500,
      schedule: clock.schedule,
      cancel: clock.cancel
    })

    scheduler.reset()
    assert.equal(scheduler.stage, 0)
    clock.advance(1000)
    assert.deepEqual(rec.calls, ['stretch'])
    assert.equal(scheduler.stage, 1)

    clock.advance(500)
    assert.deepEqual(rec.calls, ['stretch', 'sleep'])
    assert.equal(scheduler.stage, 2)

    clock.advance(500)
    assert.deepEqual(rec.calls, ['stretch', 'sleep', 'sleep'], '瞌睡段应自循环')
  })

  test('reset 把时间轴拉回活跃段：下一站是伸懒腰而不是打瞌睡', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const scheduler = createIdleScheduler(rec, {
      stretchMs: 1000,
      sleepMs: 500,
      schedule: clock.schedule,
      cancel: clock.cancel
    })

    scheduler.reset()
    clock.advance(1000)
    assert.deepEqual(rec.calls, ['stretch'])

    scheduler.reset()
    clock.advance(500)
    assert.deepEqual(rec.calls, ['stretch'], 'reset 后 sleepMs 处不应触发 sleep')
    clock.advance(500)
    assert.deepEqual(rec.calls, ['stretch', 'stretch'])
  })

  test('stop 清空定时器且 stage 归零，不再触发', () => {
    const clock = createFakeClock()
    const rec = createRecorder()
    const scheduler = createIdleScheduler(rec, {
      stretchMs: 1000,
      sleepMs: 500,
      schedule: clock.schedule,
      cancel: clock.cancel
    })

    scheduler.reset()
    clock.advance(1000)
    scheduler.stop()
    assert.equal(scheduler.stage, 0)
    clock.advance(2000)
    assert.deepEqual(rec.calls, ['stretch'])
    assert.equal(clock.pending(), 0)
  })
})
