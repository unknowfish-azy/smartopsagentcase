import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  FAULT_ALERT_CRITICAL_HOLD_MS,
  FAULT_ALERT_HOLD_MS,
  FAULT_ID_TRACK_LIMIT,
  FAULT_NOTIFY_GAP_MS,
  createFaultNotifier,
  isCriticalFault
} from '../src/components/persona/personaFaultNotify.js'

/**
 * 假时钟：替换工厂默认的 setTimeout/clearTimeout，测试逐段推进。
 * 与 persona-interactions.test.mjs 的假时钟同款。
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
    }
  }
  return clock
}

function createHarness({ isBusy = () => false, isMuted = () => false } = {}) {
  const clock = createFakeClock()
  const calls = { alerts: [], clears: 0, gestures: [], spoken: [] }
  const notifier = createFaultNotifier(
    {
      showAlert: (alert) => calls.alerts.push(alert),
      clearAlert: () => { calls.clears += 1 },
      playGesture: (name) => calls.gestures.push(name),
      speak: (text) => calls.spoken.push(text)
    },
    {
      now: () => clock.now,
      schedule: clock.schedule,
      cancel: clock.cancel,
      isBusy,
      isMuted
    }
  )
  return { clock, calls, notifier }
}

function fault(id, severity = 'MEDIUM', title = '服务异常') {
  return { id, severity, title }
}

describe('isCriticalFault', () => {
  test('HIGH/CRITICAL 为高危，其余不是', () => {
    assert.equal(isCriticalFault('CRITICAL'), true)
    assert.equal(isCriticalFault('HIGH'), true)
    assert.equal(isCriticalFault('MEDIUM'), false)
    assert.equal(isCriticalFault('INFO'), false)
    assert.equal(isCriticalFault(undefined), false)
  })
})

describe('createFaultNotifier · 基本展示', () => {
  test('正常告警：展示气泡 + pointUp 手势，低危不出声', () => {
    const { calls, notifier } = createHarness()
    const result = notifier.handleFault(fault('f1', 'MEDIUM', '磁盘偏高'))

    assert.equal(result.shown, true)
    assert.equal(result.spoke, false)
    assert.equal(calls.alerts.length, 1)
    assert.deepEqual(calls.alerts[0], { id: 'f1', critical: false, text: '发现异常「磁盘偏高」（MEDIUM）' })
    assert.deepEqual(calls.gestures, ['pointUp'])
    assert.deepEqual(calls.spoken, [])
  })

  test('气泡按等级定时消退：低危 8s，高危 12s', () => {
    const { clock, calls, notifier } = createHarness()
    notifier.handleFault(fault('f1', 'MEDIUM'))
    clock.advance(FAULT_ALERT_HOLD_MS)
    assert.equal(calls.clears, 1, '低危 8s 后消退')

    const { clock: clock2, calls: calls2, notifier: notifier2 } = createHarness()
    clock2.advance(FAULT_NOTIFY_GAP_MS + 1)
    notifier2.handleFault(fault('g1', 'CRITICAL'))
    clock2.advance(FAULT_ALERT_HOLD_MS)
    assert.equal(calls2.clears, 0, '高危不按低危时长消退')
    clock2.advance(FAULT_ALERT_CRITICAL_HOLD_MS - FAULT_ALERT_HOLD_MS)
    assert.equal(calls2.clears, 1, '高危 12s 后消退')
  })

  test('新告警到来时重置上一条的消退定时', () => {
    const { clock, calls, notifier } = createHarness()
    notifier.handleFault(fault('f1', 'MEDIUM'))
    clock.advance(FAULT_ALERT_HOLD_MS - 1000)
    notifier.dismiss() // 点气泡收起
    assert.equal(calls.clears, 1)
    clock.advance(2000)
    assert.equal(calls.clears, 1, '已取消的定时不再触发')
  })
})

describe('createFaultNotifier · 去重与节流', () => {
  test('同一 id 只报一次', () => {
    const { calls, notifier } = createHarness()
    notifier.handleFault(fault('f1'))
    const second = notifier.handleFault(fault('f1'))
    assert.equal(second.shown, false)
    assert.equal(second.reason, 'duplicate')
    assert.equal(calls.alerts.length, 1)
  })

  test('节流窗内第二条不同 id 不展示，窗后恢复', () => {
    const { clock, calls, notifier } = createHarness()
    notifier.handleFault(fault('f1'))
    clock.advance(FAULT_NOTIFY_GAP_MS - 1000)
    const throttled = notifier.handleFault(fault('f2'))
    assert.equal(throttled.shown, false)
    assert.equal(throttled.reason, 'throttled')
    assert.equal(calls.alerts.length, 1)

    clock.advance(1001) // 越过节流窗
    const next = notifier.handleFault(fault('f3'))
    assert.equal(next.shown, true)
    assert.equal(calls.alerts.length, 2)
  })

  test('节流窗被节流掉的 id 仍占用去重集合，窗后重放不展示', () => {
    const { clock, notifier } = createHarness()
    notifier.handleFault(fault('f1'))
    clock.advance(1000)
    notifier.handleFault(fault('f2')) // 被节流，但已记入集合
    clock.advance(FAULT_NOTIFY_GAP_MS)
    const replay = notifier.handleFault(fault('f2'))
    assert.equal(replay.shown, false)
    assert.equal(replay.reason, 'duplicate')
  })

  test('去重集合容量淘汰最旧 id，防长会话内存膨胀', () => {
    const { clock, notifier } = createHarness()
    clock.advance(FAULT_NOTIFY_GAP_MS)
    for (let i = 0; i <= FAULT_ID_TRACK_LIMIT; i += 1) {
      notifier.handleFault(fault(`k${i}`))
      clock.advance(FAULT_NOTIFY_GAP_MS) // 每条都过节流窗
    }
    // 最旧的 k0 已被淘汰：重新喂入应视为新事件并展示
    const replayed = notifier.handleFault(fault('k0'))
    assert.equal(replayed.shown, true)
  })
})

describe('createFaultNotifier · 出声决策', () => {
  test('高危且空闲且非静音：出声，文案含等级标签', () => {
    const { calls, notifier } = createHarness()
    const result = notifier.handleFault(fault('f1', 'CRITICAL', '主库宕机'))
    assert.equal(result.spoke, true)
    assert.equal(calls.spoken.length, 1)
    assert.match(calls.spoken[0], /高危/)
    assert.match(calls.spoken[0], /主库宕机/)
  })

  test('HIGH 报「较高级」', () => {
    const { calls, notifier } = createHarness()
    notifier.handleFault(fault('f1', 'HIGH'))
    assert.match(calls.spoken[0], /较高级/)
  })

  test('正在播报（isBusy）：气泡照常但不出声', () => {
    const { calls, notifier } = createHarness({ isBusy: () => true })
    const result = notifier.handleFault(fault('f1', 'CRITICAL'))
    assert.equal(result.shown, true)
    assert.equal(result.spoke, false)
    assert.deepEqual(calls.spoken, [])
  })

  test('听筒静音（isMuted）：不出声', () => {
    const { notifier } = createHarness({ isMuted: () => true })
    const result = notifier.handleFault(fault('f1', 'CRITICAL'))
    assert.equal(result.shown, true)
    assert.equal(result.spoke, false)
  })

  test('低危永远不出声', () => {
    const { calls, notifier } = createHarness()
    notifier.handleFault(fault('f1', 'INFO'))
    assert.deepEqual(calls.spoken, [])
  })
})

describe('createFaultNotifier · 健壮性', () => {
  test('缺 id 的无效事件直接忽略', () => {
    const { calls, notifier } = createHarness()
    assert.deepEqual(notifier.handleFault(null), { shown: false, spoke: false, reason: 'missing-id' })
    assert.deepEqual(notifier.handleFault({ severity: 'CRITICAL' }), { shown: false, spoke: false, reason: 'missing-id' })
    assert.deepEqual(calls.alerts, [])
  })

  test('title 缺失时降级为「未知异常」，不抛错', () => {
    const { calls, notifier } = createHarness()
    const result = notifier.handleFault({ id: 'f1', severity: 'MEDIUM' })
    assert.equal(result.shown, true)
    assert.match(calls.alerts[0].text, /未知异常/)
  })

  test('dismiss 幂等，可安全重复调用', () => {
    const { calls, notifier } = createHarness()
    notifier.dismiss()
    notifier.dismiss()
    assert.equal(calls.clears, 2) // 只是多触发一次 clearAlert 回调，无异常
  })
})
