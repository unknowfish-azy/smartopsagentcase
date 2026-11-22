import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  DEFAULT_MIN_CONFIDENCE,
  EMOTION_BLOCKED_STATES,
  EMOTION_LABELS,
  EMOTION_TO_EXPRESSION,
  emotionExpression,
  emotionLabelText,
  emotionSourceLabel,
  normalizeEmotionLabel,
  withEmotion
} from '../src/components/persona/emotionInput.js'
import { personaProfile } from '../src/components/persona/personaStates.js'

/** 造一个端点同形的情绪结果。 */
function emotion(overrides = {}) {
  return {
    available: true,
    ok: true,
    engine: 'composite+model',
    status: 'SUCCEEDED',
    label: 'happy',
    confidence: 0.8,
    ...overrides
  }
}

describe('EMOTION_TO_EXPRESSION', () => {
  test('只使用渲染层已有枚举', () => {
    const supported = ['relaxed', 'happy', 'sad', 'angry', 'surprised']
    for (const weights of Object.values(EMOTION_TO_EXPRESSION)) {
      for (const key of Object.keys(weights)) {
        assert.ok(supported.includes(key), `${key} 不是渲染层支持的表情`)
      }
    }
  })

  test('每个情绪标签都有映射', () => {
    for (const label of EMOTION_LABELS) {
      assert.ok(EMOTION_TO_EXPRESSION[label], `${label} 缺少映射`)
    }
  })
})

describe('emotionExpression', () => {
  test('可用结果返回权重', () => {
    assert.deepEqual(emotionExpression(emotion()), { happy: 0.6, relaxed: 0.2 })
  })

  test('引擎不可用（available=false）不返回权重', () => {
    assert.equal(emotionExpression(emotion({ available: false, label: 'neutral' })), null)
  })

  test('状态非 SUCCEEDED 不返回权重', () => {
    assert.equal(emotionExpression(emotion({ status: 'UNAVAILABLE' })), null)
    assert.equal(emotionExpression(emotion({ status: 'EMPTY' })), null)
  })

  test('未知标签不返回权重', () => {
    assert.equal(emotionExpression(emotion({ label: 'fearful' })), null)
  })

  test('置信度缺失不返回权重（不把未知当 0 用）', () => {
    assert.equal(emotionExpression(emotion({ confidence: null })), null)
  })

  test('低于阈值不返回权重', () => {
    assert.equal(emotionExpression(emotion({ confidence: DEFAULT_MIN_CONFIDENCE - 0.01 })), null)
    assert.equal(emotionExpression(emotion({ confidence: 0.45 })), null)
  })

  test('入参不是对象时不炸', () => {
    assert.equal(emotionExpression(null), null)
    assert.equal(emotionExpression('happy'), null)
  })
})

describe('withEmotion', () => {
  test('按 max 合并，不改入参', () => {
    const profile = personaProfile('idle') // expressions: { relaxed: 0.25 }
    const next = withEmotion(profile, emotion({ label: 'happy', confidence: 0.8 }))
    assert.notEqual(next, profile)
    assert.equal(next.expressions.happy, 0.6)
    assert.equal(next.expressions.relaxed, 0.25) // 状态原有权重保留
    assert.deepEqual(profile.expressions, { relaxed: 0.25 }) // 入参未被改
  })

  test('不覆盖状态里更高的一方', () => {
    const profile = personaProfile('error') // sad 0.55 / angry 0.2
    const next = withEmotion(profile, emotion({ label: 'sad', confidence: 0.9 }), { state: 'error' })
    assert.equal(next, profile) // error 态被拦下
    const idleNext = withEmotion(personaProfile('idle'), emotion({ label: 'sad', confidence: 0.9 }), {
      state: 'idle'
    })
    assert.equal(idleNext.expressions.sad, 0.55) // max(0, 0.55)
  })

  test('告警 / 故障态一律不叠加（状态主导）', () => {
    for (const state of EMOTION_BLOCKED_STATES) {
      const profile = personaProfile(state)
      const next = withEmotion(profile, emotion({ label: 'happy', confidence: 0.95 }), { state })
      assert.equal(next, profile, `${state} 态不应被情绪改变`)
    }
  })

  test('低置信度原样返回原对象（便于判等）', () => {
    const profile = personaProfile('idle')
    assert.equal(withEmotion(profile, emotion({ confidence: 0.4 })), profile)
  })

  test('引擎不可用原样返回', () => {
    const profile = personaProfile('idle')
    assert.equal(withEmotion(profile, emotion({ available: false, status: 'UNAVAILABLE' })), profile)
  })

  test('保留 profile 的其它字段', () => {
    const profile = personaProfile('thinking')
    const next = withEmotion(profile, emotion(), { state: 'thinking' })
    assert.equal(next.hint, profile.hint)
    assert.equal(next.glow, profile.glow)
    assert.equal(next.accent, profile.accent)
    assert.deepEqual(next.pose, profile.pose)
  })

  test('自定义阈值可放宽', () => {
    const profile = personaProfile('idle')
    const next = withEmotion(profile, emotion({ confidence: 0.45 }), { minConfidence: 0.4 })
    assert.equal(next.expressions.happy, 0.6)
  })

  test('profile 缺 expressions 时也能叠加', () => {
    const next = withEmotion({ hint: 'x' }, emotion())
    assert.deepEqual(next.expressions, { happy: 0.6, relaxed: 0.2 })
  })
})

describe('标注文案', () => {
  test('normalizeEmotionLabel 归一大小写与空白', () => {
    assert.equal(normalizeEmotionLabel('  Happy '), 'happy')
    assert.equal(normalizeEmotionLabel(null), '')
  })

  test('emotionSourceLabel 分三档', () => {
    assert.deepEqual(emotionSourceLabel(emotion({ engine: 'composite+model' })), {
      text: '本地模型',
      tone: 'model'
    })
    assert.deepEqual(emotionSourceLabel(emotion({ engine: 'composite+lexicon' })), {
      text: '词典兜底',
      tone: 'lexicon'
    })
    assert.deepEqual(emotionSourceLabel(emotion({ available: false, engine: 'none' })), {
      text: '情绪未识别',
      tone: 'none'
    })
    assert.equal(emotionSourceLabel(null).tone, 'none')
  })

  test('emotionLabelText 有中文且未知回退', () => {
    assert.equal(emotionLabelText('happy'), '开心')
    assert.equal(emotionLabelText('neutral'), '平静')
    assert.equal(emotionLabelText('fearful'), '未知')
  })
})
