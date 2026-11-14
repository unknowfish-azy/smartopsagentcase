import assert from 'node:assert/strict'
import { beforeEach, describe, test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import {
  PERSONA_PET_INSET,
  PERSONA_PET_SIZE,
  clampPersonaPetPosition,
  usePersonaPetStore
} from '../src/stores/personaPet.js'
import { createLipSync, VISEMES } from '../src/components/persona/useLipSync.js'
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
