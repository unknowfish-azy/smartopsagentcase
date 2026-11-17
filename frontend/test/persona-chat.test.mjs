import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  CHAT_PHASE_LABELS,
  createSpeechPump,
  normalizeChatMessage,
  personaStateForChat
} from '../src/components/persona/personaChat.js'

describe('personaStateForChat', () => {
  test('把聊天阶段映射到人格状态', () => {
    assert.equal(personaStateForChat('idle'), 'idle')
    assert.equal(personaStateForChat('connecting'), 'thinking')
    assert.equal(personaStateForChat('streaming'), 'executing')
    assert.equal(personaStateForChat('error'), 'error')
    // 未知阶段不能把化身卡在说话态
    assert.equal(personaStateForChat('unknown'), 'idle')
  })

  test('渲染降级优先于聊天阶段', () => {
    assert.equal(personaStateForChat('streaming', { renderStatus: 'error' }), 'error')
    assert.equal(personaStateForChat('idle', { renderStatus: 'lost' }), 'warning')
  })

  test('每个阶段都有可读标签（状态不只靠颜色）', () => {
    for (const phase of ['idle', 'connecting', 'streaming', 'error']) {
      assert.equal(typeof CHAT_PHASE_LABELS[phase], 'string')
      assert.ok(CHAT_PHASE_LABELS[phase].length > 0)
    }
  })
})

describe('normalizeChatMessage', () => {
  test('空输入与纯空白被拦下', () => {
    assert.deepEqual(normalizeChatMessage(''), { ok: false, text: '', reason: 'empty' })
    assert.equal(normalizeChatMessage('   \n\t ').reason, 'empty')
  })

  test('去掉首尾空白与控制字符，保留换行', () => {
    const result = normalizeChatMessage('  nginx\u0000502\n怎么排查  ')
    assert.equal(result.ok, true)
    assert.equal(result.text, 'nginx502\n怎么排查')
  })

  test('超过 2000 字符不下发', () => {
    const result = normalizeChatMessage('a'.repeat(2001))
    assert.equal(result.ok, false)
    assert.equal(result.reason, 'too-long')
    assert.equal(normalizeChatMessage('a'.repeat(2000)).ok, true)
  })
})

describe('createSpeechPump', () => {
  function createPersona() {
    const calls = { speak: [], seek: [], stop: 0 }
    return {
      calls,
      speakText: (text, options) => calls.speak.push({ text, options }),
      seekSpeech: (index) => calls.seek.push(index),
      stopSpeaking: () => { calls.stop += 1 }
    }
  }

  test('首段直接起播，不 seek', () => {
    const persona = createPersona()
    const pump = createSpeechPump(persona, { cps: 6 })
    pump.push('正在排查 nginx。')

    assert.equal(persona.calls.speak.length, 1)
    assert.equal(persona.calls.speak[0].text, '正在排查 nginx。')
    assert.deepEqual(persona.calls.speak[0].options, { cps: 6 })
    assert.deepEqual(persona.calls.seek, [])
  })

  test('增量到达时重建时间线并跳到已播位置，避免从头动嘴', () => {
    const persona = createPersona()
    const pump = createSpeechPump(persona)
    pump.push('先看网关')
    pump.push('先看网关日志')

    assert.equal(persona.calls.speak.length, 2)
    assert.equal(persona.calls.speak[1].text, '先看网关日志')
    assert.deepEqual(persona.calls.seek, [4])
  })

  test('stop 之后重新从头发音，不沿用旧游标', () => {
    const persona = createPersona()
    const pump = createSpeechPump(persona)
    pump.push('第一段')
    pump.stop()
    pump.push('第二段')

    assert.equal(persona.calls.stop, 1)
    assert.deepEqual(persona.calls.seek, [])
  })

  test('空文本不触发口型', () => {
    const persona = createPersona()
    const pump = createSpeechPump(persona)
    pump.push('   ')
    assert.equal(persona.calls.speak.length, 0)
  })
})
