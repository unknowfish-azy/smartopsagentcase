import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'

import {
  VOICE_ACTIONS,
  HAZARD_LEVELS,
  actionBlockedBubble,
  actionConfirmBubble,
  actionExecuteBubble,
  createVoiceActionBus,
  resetGlobalActionBusForTests,
  resolveVoiceActionIntent,
  useVoiceActionBus,
} from '../src/components/persona/voiceActionRegistry.js'

afterEach(() => { resetGlobalActionBusForTests() })

describe('voiceActionRegistry', () => {
  describe('HAZARD_LEVELS', () => {
    test('四个等级必须全部存在且不可变', () => {
      assert.ok(Object.isFrozen(HAZARD_LEVELS))
      for (const key of ['critical', 'high', 'medium', 'low']) {
        assert.ok(HAZARD_LEVELS[key])
        assert.ok('label' in HAZARD_LEVELS[key])
        assert.ok('blocks' in HAZARD_LEVELS[key])
        assert.ok('requiresConfirm' in HAZARD_LEVELS[key])
      }
      assert.equal(HAZARD_LEVELS.critical.blocks, true)
      assert.equal(HAZARD_LEVELS.low.blocks, false)
      assert.equal(HAZARD_LEVELS.low.requiresConfirm, false)
    })
  })

  describe('resolveVoiceActionIntent', () => {
    test('匹配 low 危险级别 → matched + blocked=false', () => {
      const hit = resolveVoiceActionIntent('刷新服务器列表', 'ServerList')
      assert.equal(hit.matched, true)
      assert.equal(hit.actionId, 'servers.refresh')
      assert.equal(hit.hazard, 'low')
      assert.equal(hit.blocked, false)
    })

    test('匹配 high 危险级别 → requiresConfirm=true', () => {
      const hit = resolveVoiceActionIntent('确认这个告警', 'AlertCenter')
      assert.equal(hit.matched, true)
      assert.equal(hit.actionId, 'sentinel.alerts.acknowledge')
      assert.equal(hit.hazard, 'high')
      assert.equal(hit.blocked, false)
      assert.ok(hit.confirm.length > 0)
    })

    test('匹配 critical → blocked=true', () => {
      const blocked = resolveVoiceActionIntent('执行脚本', 'Connections')
      assert.equal(blocked.matched, true)
      assert.equal(blocked.actionId, 'operations.snippets.run')
      assert.equal(blocked.hazard, 'critical')
      assert.equal(blocked.blocked, true)
    })

    test('路由不匹配 → 不命中（让上层继续尝试导航/AI）', () => {
      const no = resolveVoiceActionIntent('刷新服务器列表', 'Chat')
      assert.equal(no.matched, false)
      assert.ok(no.reason.startsWith('route-mismatch'))
    })

    test('路由名包含即算匹配（宽松匹配，不用严格 ===）', () => {
      const hit = resolveVoiceActionIntent('刷新服务器列表', 'ServerListDetail')
      assert.equal(hit.matched, true)
    })

    test('空文本 → 不命中', () => {
      assert.equal(resolveVoiceActionIntent('', 'Chat').matched, false)
      assert.equal(resolveVoiceActionIntent(null, 'Chat').matched, false)
    })

    test('所有 action 必须有 id、label、hazard、routes', () => {
      for (const action of VOICE_ACTIONS) {
        assert.ok(action.id, `${action.id} 缺 id`)
        assert.ok(action.label, `${action.id} 缺 label`)
        assert.ok(['critical', 'high', 'medium', 'low'].includes(action.hazard), `${action.id} hazard 非法`)
        assert.ok(action.routes, `${action.id} 缺 routes`)
        assert.ok(Array.isArray(action.keywords) && action.keywords.length > 0, `${action.id} 缺 keywords`)
        // high / critical 必须有 confirm 文本
        if (['critical', 'high', 'medium'].includes(action.hazard)) {
          assert.ok(action.confirm, `${action.id} 有 ${action.hazard} 但缺 confirm 文案`)
        }
      }
    })
  })

  describe('action bus', () => {
    test('register → dispatch → unregister 生命周期', async () => {
      const bus = createVoiceActionBus()
      let called = 0
      const unregister = bus.register('servers.refresh', () => { called += 1 })

      assert.equal(bus._debug.handlerCount('servers.refresh'), 1)
      const fired = await bus.dispatch('servers.refresh')
      assert.equal(fired, 1)
      assert.equal(called, 1)

      unregister()
      assert.equal(bus._debug.handlerCount('servers.refresh'), 0)
      // unregister 后再 dispatch，不报错但 fired=0
      assert.equal(await bus.dispatch('servers.refresh'), 0)
    })

    test('多个组件可注册同一 action，dispatch 全部触发', async () => {
      const bus = createVoiceActionBus()
      let a = 0, b = 0
      bus.register('chat.copy', () => { a += 1 })
      bus.register('chat.copy', () => { b += 1 })

      const fired = await bus.dispatch('chat.copy')
      assert.equal(fired, 2)
      assert.equal(a, 1)
      assert.equal(b, 1)
    })

    test('handler 抛错不影响其他 handler', async () => {
      const bus = createVoiceActionBus()
      let ok = false
      bus.register('chat.clear', () => { throw new Error('boom') })
      bus.register('chat.clear', () => { ok = true })

      const fired = await bus.dispatch('chat.clear')
      assert.equal(fired, 2)
      assert.equal(ok, true)
    })

    test('dispatch 不存在的 actionId 返回 0', async () => {
      const bus = createVoiceActionBus()
      assert.equal(await bus.dispatch('does.not.exist'), 0)
    })

    test('createVoiceActionBus 不污染全局', () => {
      const a = createVoiceActionBus()
      const b = createVoiceActionBus()
      a.register('shared', () => {})
      assert.equal(b._debug.handlerCount('shared'), 0)
    })

    test('useVoiceActionBus 全局兜底可用', async () => {
      const bus = useVoiceActionBus()
      let called = false
      bus.register('global.test', () => { called = true })
      await bus.dispatch('global.test')
      assert.equal(called, true)
    })
  })

  describe('播报文案', () => {
    test('actionBlockedBubble 包含 label、原因和"手动"', () => {
      const bubble = actionBlockedBubble('执行脚本片段', 'critical')
      assert.ok(bubble.includes('执行脚本片段'))
      assert.ok(bubble.includes('手动'))
    })
    test('actionConfirmBubble 包含 confirm 文本', () => {
      const bubble = actionConfirmBubble('忽略告警', '请再说一次确认')
      assert.ok(bubble.includes('请再说一次确认'))
    })
    test('actionExecuteBubble 包含 label', () => {
      const bubble = actionExecuteBubble('刷新告警')
      assert.ok(bubble.includes('刷新告警'))
    })
  })
})
