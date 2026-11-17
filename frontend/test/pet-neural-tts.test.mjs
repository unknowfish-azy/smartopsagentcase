import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { createPetNeuralTts } from '../src/components/persona/petNeuralTts.js'

/** 最小假播放器：记录 play/pause，允许手动触发 ended/error */
function createFakeAudio(url) {
  return {
    url,
    playCalls: 0,
    pauseCalls: 0,
    onended: null,
    onerror: null,
    play() {
      this.playCalls += 1
      return Promise.resolve()
    },
    pause() {
      this.pauseCalls += 1
    }
  }
}

function createHarness(overrides = {}) {
  const audios = []
  const revoked = []
  const events = []
  const calls = { synthesize: [] }
  const tts = createPetNeuralTts({
    fetchStatus: overrides.fetchStatus ?? (async () => ({ available: true, provider: 'voxcpm2' })),
    synthesize: overrides.synthesize ?? (async (text) => {
      calls.synthesize.push(text)
      return new Blob(['RIFF'])
    }),
    createAudio: (url) => {
      const audio = createFakeAudio(url)
      audios.push(audio)
      return audio
    },
    createObjectUrl: () => 'blob:fake-audio',
    revokeObjectUrl: (url) => revoked.push(url),
    onEnd: () => events.push('end'),
    onError: (reason) => events.push(`error:${reason}`)
  })
  return { tts, audios, revoked, events, calls }
}

describe('桌宠神经语音（petNeuralTts）', () => {
  test('可用时合成并播放 WAV，结束后释放 Blob URL', async () => {
    const { tts, audios, revoked, events, calls } = createHarness()

    const started = await tts.speak('你好，小鱼')

    assert.equal(started, true)
    assert.deepEqual(calls.synthesize, ['你好，小鱼'])
    assert.equal(audios.length, 1)
    assert.equal(audios[0].playCalls, 1)
    assert.equal(audios[0].url, 'blob:fake-audio')

    audios[0].onended()
    assert.deepEqual(events, ['end'])
    assert.deepEqual(revoked, ['blob:fake-audio'])
  })

  test('后端不可用：不合成、不播放，交给调用方回落', async () => {
    const { tts, audios, calls } = createHarness({
      fetchStatus: async () => ({ available: false, provider: null, reason: '未安装 voxcpm' })
    })

    const started = await tts.speak('你好')

    assert.equal(started, false)
    assert.deepEqual(calls.synthesize, [])
    assert.equal(audios.length, 0)
    assert.equal(tts.status.reason, '未安装 voxcpm')
  })

  test('状态查询失败不抛错，返回 false 并保留原因', async () => {
    const { tts } = createHarness({
      fetchStatus: async () => { throw new Error('连接被拒绝') }
    })

    assert.equal(await tts.speak('你好'), false)
    assert.match(tts.status.reason, /连接被拒绝/)
  })

  test('合成失败（如 503）返回 false，且不触发 onError（由调用方回落）', async () => {
    const { tts, events, revoked } = createHarness({
      synthesize: async () => { throw new Error('TTS 不可用：未配置权重') }
    })

    assert.equal(await tts.speak('你好'), false)
    assert.deepEqual(events, [])
    assert.match(tts.lastError, /未配置权重/)
    assert.deepEqual(revoked, [])
  })

  test('浏览器拦截自动播放时返回 false，并释放已创建的 URL', async () => {
    const revoked = []
    const tts = createPetNeuralTts({
      fetchStatus: async () => ({ available: true, provider: 'voxcpm2' }),
      synthesize: async () => new Blob(['RIFF']),
      createAudio: (url) => {
        const audio = createFakeAudio(url)
        audio.play = () => Promise.reject(new Error('NotAllowedError'))
        return audio
      },
      createObjectUrl: () => 'blob:fake-audio',
      revokeObjectUrl: (url) => revoked.push(url)
    })

    assert.equal(await tts.speak('你好'), false)
    assert.match(tts.lastError, /NotAllowedError/)
    assert.deepEqual(revoked, ['blob:fake-audio'])
  })

  test('播放中途出错：清理并回调 onError 如实收尾', async () => {
    const { tts, audios, events, revoked } = createHarness()

    await tts.speak('你好')
    audios[0].onerror()

    assert.deepEqual(events, ['error:神经语音播放失败'])
    assert.deepEqual(revoked, ['blob:fake-audio'])
  })

  test('空文本不请求状态也不合成', async () => {
    let probed = 0
    const { tts, calls } = createHarness({
      fetchStatus: async () => { probed += 1; return { available: true, provider: 'voxcpm2' } }
    })

    assert.equal(await tts.speak('   '), false)
    assert.equal(probed, 0)
    assert.deepEqual(calls.synthesize, [])
  })

  test('stop 暂停播放并释放 URL，之后 speak 仍可重新开始', async () => {
    const { tts, audios } = createHarness()

    await tts.speak('第一句')
    tts.stop()
    assert.equal(audios[0].pauseCalls, 1)
    assert.equal(await tts.speak('第二句'), true)
    assert.equal(audios.length, 2)
  })

  test('dispose 之后不再合成，也不重复探测', async () => {
    let probed = 0
    const { tts, calls } = createHarness({
      fetchStatus: async () => { probed += 1; return { available: true, provider: 'voxcpm2' } }
    })

    await tts.probe()
    tts.dispose()

    assert.equal(await tts.speak('你好'), false)
    assert.equal(probed, 1)
    assert.deepEqual(calls.synthesize, [])
  })
})
