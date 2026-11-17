import assert from 'node:assert/strict'
import { beforeEach, describe, test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import {
  PERSONA_PET_INSET,
  PERSONA_PET_SIZE,
  PERSONA_PET_SIZES,
  clampCustomPetSize,
  clampPersonaPetPosition,
  nearestPetSizeMode,
  resolvePetSize,
  usePersonaPetStore
} from '../src/stores/personaPet.js'
import { createLipSync, visemeTimeline, VISEMES } from '../src/components/persona/useLipSync.js'
import { createPetSpeech } from '../src/components/persona/petSpeech.js'

const VIEWPORT = { viewportWidth: 1200, viewportHeight: 900 }

describe('桌宠位置钳制', () => {
  test('出界位置拉回视口内（含安全边距）', () => {
    assert.deepEqual(
      clampPersonaPetPosition({ x: -50, y: -50 }, VIEWPORT),
      { x: PERSONA_PET_INSET, y: PERSONA_PET_INSET }
    )
    assert.deepEqual(
      clampPersonaPetPosition({ x: 5000, y: 5000 }, VIEWPORT),
      {
        x: VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.width,
        y: VIEWPORT.viewportHeight - PERSONA_PET_INSET - PERSONA_PET_SIZE.height
      }
    )
  })

  test('收起与展开互转时按各自尺寸重新钳制', () => {
    // 小球贴右下角（合法），展开成大窗后 x/y 双向越界，应拉回展开态合法位置
    const collapsedMax = VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.collapsed
    const expandedMaxX = VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.width
    const expandedMaxY = VIEWPORT.viewportHeight - PERSONA_PET_INSET - PERSONA_PET_SIZE.height
    const expanded = clampPersonaPetPosition(
      { x: collapsedMax, y: collapsedMax, collapsed: false },
      VIEWPORT
    )
    assert.equal(expanded.x, expandedMaxX)
    assert.equal(expanded.y, expandedMaxY)
    // 大窗在右下角（合法），收起成小球后 x/y 都仍在合法域，位置保持
    const collapsed = clampPersonaPetPosition(
      { x: expandedMaxX, y: expandedMaxY, collapsed: true },
      VIEWPORT
    )
    assert.deepEqual(collapsed, { x: expandedMaxX, y: expandedMaxY })
  })

  test('极小视口也不产生负坐标', () => {
    const tiny = { viewportWidth: 10, viewportHeight: 10 }
    const result = clampPersonaPetPosition({ x: 5, y: 5 }, tiny)
    assert.equal(result.x, PERSONA_PET_INSET)
    assert.equal(result.y, PERSONA_PET_INSET)
  })
})

describe('悬浮窗视口自适应缩放（resolvePetSize）', () => {
  test('大屏（≥900 高）三档均返回设计基准，不放大也不收敛', () => {
    const vp = { viewportWidth: 1200, viewportHeight: 900 }
    assert.deepEqual(resolvePetSize('compact', vp), PERSONA_PET_SIZES.compact)
    assert.deepEqual(resolvePetSize('regular', vp), PERSONA_PET_SIZES.regular)
    assert.deepEqual(resolvePetSize('large', vp), PERSONA_PET_SIZES.large)
    assert.deepEqual(resolvePetSize('unknown', vp), PERSONA_PET_SIZES.regular)
  })

  test('矮屏（笔记本 125% 缩放）regular 按视口高收敛，比例保持 2:3', () => {
    const resolved = resolvePetSize('regular', { viewportWidth: 1280, viewportHeight: 640 })
    // 0.40 × 640 = 256 < 基准 348 → 收敛到 256 高
    assert.equal(resolved.height, 256)
    assert.equal(resolved.width, Math.round(256 * 2 / 3))
  })

  test('large 在 800 高屏收敛到视口一半，compact 保持基准', () => {
    const vp = { viewportWidth: 1440, viewportHeight: 800 }
    assert.deepEqual(resolvePetSize('large', vp), { width: 267, height: 400 })
    // compact: 0.34 × 800 = 272 ≥ 300？272 < 300 → 也收敛
    const compact = resolvePetSize('compact', vp)
    assert.equal(compact.height, 272)
  })

  test('超窄屏受视口宽 36% 约束，且不低于可读性下限', () => {
    const resolved = resolvePetSize('regular', { viewportWidth: 380, viewportHeight: 800 })
    // 高度 320 → 宽 213；宽上限 max(150, 137) = 150 → 收敛到 150×225
    assert.deepEqual(resolved, { width: 150, height: 225 })
  })

  test('极矮视口触发高度下限 225（与宽度下限 150 自洽）', () => {
    const resolved = resolvePetSize('regular', { viewportWidth: 1200, viewportHeight: 300 })
    assert.deepEqual(resolved, { width: 150, height: 225 })
  })

  test('clamp 使用收敛后尺寸：矮屏右下角可贴得更近', () => {
    const vp = { viewportWidth: 1280, viewportHeight: 640 }
    const result = clampPersonaPetPosition({ x: 5000, y: 5000 }, vp, 'regular')
    assert.equal(result.x, 1280 - PERSONA_PET_INSET - Math.round(256 * 2 / 3))
    assert.equal(result.y, 640 - PERSONA_PET_INSET - 256)
  })
})

describe('自定义尺寸（自由拖拽，clampCustomPetSize）', () => {
  test('高度驱动、宽度按 2:3 回算', () => {
    assert.deepEqual(clampCustomPetSize({ height: 400 }, VIEWPORT), { width: 267, height: 400 })
    assert.deepEqual(clampCustomPetSize({ height: 450 }, VIEWPORT), { width: 300, height: 450 })
  })

  test('下限 150×225，上限视口高 60% 且不超视口宽 36%', () => {
    assert.deepEqual(clampCustomPetSize({ height: 50 }, VIEWPORT), { width: 150, height: 225 })
    // 900 × 0.6 = 540 高 → 360 宽；宽上限 432 不触发
    assert.deepEqual(clampCustomPetSize({ height: 5000 }, VIEWPORT), { width: 360, height: 540 })
    // 380 宽窄屏：宽上限 max(150, 137) = 150 → 收敛成 150×225
    assert.deepEqual(
      clampCustomPetSize({ height: 400 }, { viewportWidth: 380, viewportHeight: 800 }),
      { width: 150, height: 225 }
    )
  })

  test('非法高度回到下限，不产生 NaN', () => {
    assert.deepEqual(clampCustomPetSize({ height: Number.NaN }, VIEWPORT), { width: 150, height: 225 })
    assert.deepEqual(clampCustomPetSize({}, VIEWPORT), { width: 150, height: 225 })
  })

  test('resolvePetSize 优先使用自定义尺寸', () => {
    assert.deepEqual(
      resolvePetSize('compact', VIEWPORT, { height: 420 }),
      { width: 280, height: 420 }
    )
  })
})

describe('右下角拖拽缩放的档位吸附（nearestPetSizeMode）', () => {
  test('大屏按三档高度吸附到最近档位', () => {
    const vp = { viewportWidth: 1200, viewportHeight: 900 }
    // 三档高度：compact 300 / regular 348 / large 432
    assert.equal(nearestPetSizeMode(120, vp), 'compact')
    assert.equal(nearestPetSizeMode(340, vp), 'regular')
    assert.equal(nearestPetSizeMode(372, vp), 'regular')
    assert.equal(nearestPetSizeMode(400, vp), 'large')
    assert.equal(nearestPetSizeMode(2000, vp), 'large')
  })

  test('矮屏用收敛后的高度吸附，不会把 regular 判成 large', () => {
    const vp = { viewportWidth: 1280, viewportHeight: 640 }
    // 收敛后：compact 225 / regular 256 / large 320
    assert.equal(nearestPetSizeMode(230, vp), 'compact')
    assert.equal(nearestPetSizeMode(260, vp), 'regular')
    assert.equal(nearestPetSizeMode(300, vp), 'large')
  })
})

describe('桌宠形态状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installMockStorage()
  })

  /** Node 环境没有 localStorage：装一个极简 mock 让持久化链路可测 */
  function installMockStorage() {
    const backing = new Map()
    globalThis.localStorage = {
      getItem: (key) => (backing.has(key) ? backing.get(key) : null),
      setItem: (key, value) => backing.set(key, String(value)),
      removeItem: (key) => backing.delete(key),
      clear: () => backing.clear()
    }
  }

  test('默认关闭，开启后记忆选择', () => {
    const store = usePersonaPetStore()
    assert.equal(store.enabled, false)
    store.enable()
    assert.equal(store.enabled, true)
    const persisted = JSON.parse(globalThis.localStorage.getItem('smartops_persona_pet'))
    assert.equal(persisted.enabled, true)
    store.disable()
    assert.equal(store.enabled, false)
  })

  test('收起与展开按各自尺寸重新钳制并落盘', () => {
    const store = usePersonaPetStore()
    const expandedMaxX = VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.width
    // 小球先贴到右缘，展开后大窗越界，应被拉回展开态合法位置
    store.setCollapsed(true, VIEWPORT)
    store.setPosition({ x: 5000, y: 5000 }, VIEWPORT)
    assert.equal(
      store.position.x,
      VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.collapsed
    )
    store.setCollapsed(false, VIEWPORT)
    assert.equal(store.collapsed, false)
    assert.equal(store.position.x, expandedMaxX)
    assert.equal(
      store.position.y,
      VIEWPORT.viewportHeight - PERSONA_PET_INSET - PERSONA_PET_SIZE.height
    )
  })

  test('moveBy 拖拽只改内存，出界自动钳制', () => {
    const store = usePersonaPetStore()
    store.setPosition({ x: 100, y: 100 }, VIEWPORT)
    store.moveBy(40, -30, VIEWPORT)
    assert.deepEqual(store.position, { x: 140, y: 70 })
    store.moveBy(99999, 0, VIEWPORT)
    assert.equal(store.position.x, VIEWPORT.viewportWidth - PERSONA_PET_INSET - PERSONA_PET_SIZE.width)
  })

  test('自由拖拽：applyCustomSize 只改内存，setCustomSize 才落盘', () => {
    const store = usePersonaPetStore()
    store.applyCustomSize({ height: 400 }, VIEWPORT)
    assert.deepEqual(store.customSize, { width: 267, height: 400 })
    assert.equal(globalThis.localStorage.getItem('smartops_persona_pet'), null)

    store.setCustomSize({ height: 420 }, VIEWPORT)
    const persisted = JSON.parse(globalThis.localStorage.getItem('smartops_persona_pet'))
    assert.deepEqual(persisted.customSize, { width: 280, height: 420 })
  })

  test('自定义尺寸参与位置钳制：贴右下角后按新尺寸回拉', () => {
    const store = usePersonaPetStore()
    store.setPosition({ x: 5000, y: 5000 }, VIEWPORT)
    store.applyCustomSize({ height: 400 }, VIEWPORT)
    assert.equal(store.position.x, VIEWPORT.viewportWidth - PERSONA_PET_INSET - 267)
    assert.equal(store.position.y, VIEWPORT.viewportHeight - PERSONA_PET_INSET - 400)
  })

  test('切档清空自定义尺寸，并从最近档位继续循环', () => {
    const store = usePersonaPetStore()
    store.applyCustomSize({ height: 310 }, VIEWPORT)  // 最接近 compact(300)
    assert.equal(store.cycleSize(VIEWPORT), 'regular')
    assert.equal(store.sizeMode, 'regular')
    assert.equal(store.customSize, null)
    assert.equal(JSON.parse(globalThis.localStorage.getItem('smartops_persona_pet')).customSize, null)
  })
})

describe('口型时间线 boundary 校正（seek）', () => {
  test('seek 跳到对应字符音段，update 输出该音段主口型', () => {
    const lip = createLipSync()
    // 文本「你好，世界」：标点前 2 个音段，标点后 2 个音段
    lip.speak('你好，世界', { cps: 5 })
    // charIndex=3（「世」的 UTF-16 索引）应跳到第 3 个音段起点
    lip.seek(3)
    const weights = lip.update(1 / 60)
    // 前两段 + 标点停顿已跳过：当前音段是「世」的主口型，应非零
    const active = VISEMES.filter((name) => weights[name] > 0.01)
    assert.ok(active.length >= 1, `seek 后应有口型权重，实际 ${JSON.stringify(weights)}`)
    lip.dispose()
  })

  test('seek 越过末尾清空时间线，权重归零', () => {
    const lip = createLipSync()
    lip.speak('测试', { cps: 5 })
    lip.seek(999)
    const weights = lip.update(1 / 60)
    for (const name of VISEMES) assert.equal(weights[name], 0)
    assert.equal(lip.isActive().text, false)
    lip.dispose()
  })

  test('无时间线时 seek 安全空操作', () => {
    const lip = createLipSync()
    lip.seek(0)
    lip.dispose()
  })
})

describe('桌宠语音（petSpeech）', () => {
  function installMockSpeechSynthesis() {
    const utterances = []
    const mock = {
      speak(u) {
        utterances.push(u)
        u.onstart?.()
      },
      cancel() {
        utterances.splice(0).forEach((u) => u.onend?.())
      },
      __utterances: utterances,
      __end(index) {
        utterances[index]?.onend?.()
      },
      __boundary(index, charIndex) {
        utterances[index]?.onboundary?.({ charIndex })
      }
    }
    globalThis.speechSynthesis = mock
    globalThis.SpeechSynthesisUtterance = class {
      constructor(text) {
        this.text = text
      }
    }
    return mock
  }

  test('播报成功并把 boundary 转发为 charIndex', () => {
    const mock = installMockSpeechSynthesis()
    const seen = []
    let ended = false
    const speech = createPetSpeech({
      onBoundary: (index) => seen.push(index),
      onEnd: () => { ended = true }
    })
    try {
      assert.equal(speech.speak('你好世界'), true)
      mock.__boundary(0, 2)
      assert.deepEqual(seen, [2])
      mock.__end(0)
      assert.equal(ended, true)
    } finally {
      speech.dispose()
    }
  })

  test('stop 后 onend 清理，再次 speak 不串场', () => {
    const mock = installMockSpeechSynthesis()
    let endedCount = 0
    const speech = createPetSpeech({ onEnd: () => { endedCount += 1 } })
    try {
      speech.speak('第一句')
      speech.stop()
      assert.equal(endedCount, 1, 'cancel 触发 onend 清理')
      assert.equal(speech.speak('第二句'), true)
      // cancel 已清空上一条，当前只剩第二句
      assert.equal(mock.__utterances.length, 1)
      assert.equal(mock.__utterances[0].text, '第二句')
    } finally {
      speech.dispose()
    }
  })

  test('环境不支持时 speak 返回 false，不抛错', () => {
    const original = globalThis.speechSynthesis
    delete globalThis.speechSynthesis
    try {
      const speech = createPetSpeech()
      try {
        assert.equal(speech.speak('测试'), false)
      } finally {
        speech.dispose()
      }
    } finally {
      if (original) globalThis.speechSynthesis = original
    }
  })

  test('空文本不启动播报', () => {
    const mock = installMockSpeechSynthesis()
    const speech = createPetSpeech()
    try {
      assert.equal(speech.speak('   '), false)
      assert.equal(mock.__utterances.length, 0)
    } finally {
      speech.dispose()
    }
  })
})

describe('口型 timeline 模式（后端词级时间戳）', () => {
  test('visemeTimeline 按词的真实起止时间摊到字符上', () => {
    const text = '你好，世界'
    const planned = visemeTimeline(text, [
      { text: '你好', offset_ms: 0, duration_ms: 400 },
      { text: '世界', offset_ms: 600, duration_ms: 400 }
    ])

    assert.ok(planned)
    // 4 个可发音字符（标点不占口型时间）
    assert.equal(planned.entries.length, 4)
    assert.equal(planned.duration, 1000)
    // 第一个词的字符均分 400ms
    assert.equal(planned.entries[0].start, 0)
    assert.equal(planned.entries[0].end, 200)
    // 第二个词从真实 offset 起步，不是紧跟上一段
    assert.equal(planned.entries[2].start, 600)
    assert.equal(planned.entries[2].end, 800)
    assert.equal(planned.entries[2].charIndex, text.indexOf('世'))
  })

  test('服务端给出真实 viseme 时优先采用，缺省才按字符近似', () => {
    const planned = visemeTimeline('你好', [
      // piper-plus 的音节级时间戳：每个字一条，并带真实韵母
      { text: '你', offset_ms: 0, duration_ms: 120, viseme: 'ih' },
      { text: '好', offset_ms: 120, duration_ms: 160, viseme: 'aa' }
    ])

    assert.ok(planned)
    assert.deepEqual(
      planned.entries.map((entry) => entry.primary),
      ['ih', 'aa']
    )
    // 非法 viseme 不能污染口型：退回字符近似映射
    const fallback = visemeTimeline('好', [
      { text: '好', offset_ms: 0, duration_ms: 100, viseme: 'not-a-viseme' }
    ])
    assert.notEqual(fallback.entries[0].primary, 'not-a-viseme')
  })

  test('timing 为空或全部非法时返回 null，绝不伪造时间线', () => {
    assert.equal(visemeTimeline('你好', []), null)
    assert.equal(visemeTimeline('你好', null), null)
    assert.equal(
      visemeTimeline('你好', [
        { text: '你好', offset_ms: -1, duration_ms: 0 },
        { text: '，', offset_ms: 100, duration_ms: 200 }
      ]),
      null
    )
  })

  test('speakTimeline 成功后按时间戳推进口型，并如实报告 mode', () => {
    const lip = createLipSync()
    const aligned = lip.speakTimeline('你好世界', [
      { text: '你好世界', offset_ms: 0, duration_ms: 1000 }
    ])

    assert.equal(aligned, true)
    assert.equal(lip.isActive().mode, 'timeline')
    const weights = lip.update(0.1)
    assert.ok(VISEMES.some((name) => weights[name] > 0.01))
    lip.dispose()
  })

  test('speakTimeline 没有时间戳时退回匀速近似，mode 标记为 text', () => {
    const lip = createLipSync()
    const aligned = lip.speakTimeline('你好世界', [])

    assert.equal(aligned, false)
    assert.equal(lip.isActive().mode, 'text')
    lip.dispose()
  })
})
