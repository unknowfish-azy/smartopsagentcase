import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'
import {
  askAssistant,
  createVoiceInput,
  isVoiceInputAvailable
} from '../src/components/persona/personaVoice.js'

afterEach(() => {
  delete globalThis.SpeechRecognition
  delete globalThis.webkitSpeechRecognition
})

/**
 * 装一个可编程 mock 的 SpeechRecognition：
 * instances 记录每个实例，测试里手动触发 onresult/onerror/onend。
 */
function installMockRecognition() {
  const instances = []
  class MockRecognition {
    constructor() {
      this.lang = ''
      this.interimResults = true
      this.maxAlternatives = 1
      this.started = false
      instances.push(this)
    }
    start() {
      if (this.started) {
        const error = new Error('already started')
        error.name = 'InvalidStateError'
        throw error
      }
      this.started = true
    }
    stop() {
      this.started = false
      this.onend?.()
    }
  }
  globalThis.SpeechRecognition = MockRecognition
  return instances
}

describe('语音听写（createVoiceInput）', () => {
  test('环境不支持时 resolve unsupported，不抛错', async () => {
    const voice = createVoiceInput()
    const result = await voice.start()
    assert.deepEqual(result, { text: '', reason: 'unsupported' })
  })

  test('isVoiceInputAvailable 识别 webkit 前缀实现', () => {
    assert.equal(isVoiceInputAvailable(), false)
    globalThis.webkitSpeechRecognition = class {}
    assert.equal(isVoiceInputAvailable(), true)
  })

  test('拿到 finalResult 即 resolve 文本并 stop 识别器', async () => {
    const instances = installMockRecognition()
    const voice = createVoiceInput()
    const pending = voice.start()
    const recognition = instances[0]
    assert.equal(recognition.lang, 'zh-CN')
    assert.equal(recognition.interimResults, false)
    recognition.onresult({ results: [[{ transcript: ' 集群健康状态怎么样 ' }]] })
    assert.deepEqual(await pending, { text: '集群健康状态怎么样' })
    assert.equal(recognition.started, false, '结束后应调用 stop')
  })

  test('识别错误归一化为 reason（not-allowed）', async () => {
    const instances = installMockRecognition()
    const voice = createVoiceInput()
    const pending = voice.start()
    instances[0].onerror({ error: 'not-allowed' })
    assert.deepEqual(await pending, { text: '', reason: 'not-allowed' })
  })

  test('超时兜底：超时后不再受晚到的结果影响', async () => {
    const instances = installMockRecognition()
    const timers = []
    const voice = createVoiceInput({
      timeoutMs: 500,
      setTimeoutFn: (fn, ms) => { timers.push({ fn, ms }); return timers.length },
      clearTimeoutFn: (id) => { timers[id - 1] = null }
    })
    const pending = voice.start()
    // 模拟超时定时器触发
    timers[0].fn()
    assert.deepEqual(await pending, { text: '', reason: 'timeout' })
    // 超时后识别器才给出结果：应被忽略
    instances[0].onresult({ results: [[{ transcript: '太晚了' }]] })
  })

  test('onend 不带结果时 resolve no-result', async () => {
    const instances = installMockRecognition()
    const voice = createVoiceInput()
    const pending = voice.start()
    instances[0].onend()
    assert.deepEqual(await pending, { text: '', reason: 'no-result' })
  })

  test('用户 stop() 提前终止：resolve aborted-by-user，晚到结果无效', async () => {
    const instances = installMockRecognition()
    const voice = createVoiceInput()
    const pending = voice.start()
    voice.stop()
    assert.deepEqual(await pending, { text: '', reason: 'aborted-by-user' })
    instances[0].onresult({ results: [[{ transcript: '不该收到' }]] })
  })

  test('重复 start（InvalidStateError）安全归一化', async () => {
    // 模拟浏览器在识别器已在运行时 start 抛 InvalidStateError
    class BusyRecognition {
      start() {
        const error = new Error('already started')
        error.name = 'InvalidStateError'
        throw error
      }
      stop() {}
    }
    globalThis.SpeechRecognition = BusyRecognition
    const voice = createVoiceInput()
    const result = await voice.start()
    assert.equal(result.reason, 'already-started')
  })
})

describe('AI 回复聚合（askAssistant）', () => {
  test('签发令牌 → 流式聚合 → 返回完整回复', async () => {
    const calls = []
    const streamChatFn = async (prompt, handlers, options) => {
      calls.push({ prompt, runToken: options.runToken })
      handlers.onToken('集群')
      handlers.onToken('健康')
      handlers.onDone({ status: 'succeeded' })
    }
    const result = await askAssistant('集群怎么样', {
      streamChatFn,
      fetchToken: async () => ({ data: { runToken: 'token-1' } })
    })
    assert.deepEqual(result, { ok: true, text: '集群健康' })
    assert.deepEqual(calls[0], { prompt: '集群怎么样', runToken: 'token-1' })
  })

  test('done 携带完整 answer 且更长时优先采用', async () => {
    const streamChatFn = async (prompt, handlers) => {
      handlers.onToken('部')
      handlers.onDone({ answer: '完整的回答文本' })
    }
    const result = await askAssistant('问题', {
      streamChatFn,
      fetchToken: async () => ({ runToken: 't' })
    })
    assert.deepEqual(result, { ok: true, text: '完整的回答文本' })
  })

  test('令牌缺失时返回鉴权提示，不调用流式接口', async () => {
    let called = false
    const result = await askAssistant('问题', {
      streamChatFn: async () => { called = true },
      fetchToken: async () => ({ runToken: '' })
    })
    assert.equal(called, false)
    assert.equal(result.ok, false)
    assert.match(result.text, /令牌/)
  })

  test('空消息直接短路', async () => {
    const result = await askAssistant('   ', { streamChatFn: async () => {}, fetchToken: async () => ({ runToken: 't' }) })
    assert.deepEqual(result, { ok: false, text: '' })
  })

  test('流式异常归一化为失败 + 可读消息', async () => {
    const result = await askAssistant('问题', {
      streamChatFn: async () => { throw new Error('AI 服务返回 500') },
      fetchToken: async () => ({ runToken: 't' })
    })
    assert.equal(result.ok, false)
    assert.match(result.text, /AI 服务返回 500/)
  })

  test('流结束无内容时返回兜底文案', async () => {
    const result = await askAssistant('问题', {
      streamChatFn: async (prompt, handlers) => { handlers.onDone({ status: 'succeeded' }) },
      fetchToken: async () => ({ runToken: 't' })
    })
    assert.equal(result.ok, false)
    assert.match(result.text, /没有返回内容/)
  })
})
