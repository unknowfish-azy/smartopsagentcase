import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  PERSONA_GESTURES,
  PERSONA_GESTURE_EXPRESSIONS,
  PERSONA_GESTURE_NAMES,
  PERSONA_GESTURE_VOICES,
  PERSONA_GESTURE_VOICE_VARIANTS,
  gestureVoice,
  sampleGesture,
  sampleGestureExpressions,
  validateGestures
} from '../src/components/persona/personaGestures.js'
import { PERSONA_POSE_BASE } from '../src/components/persona/personaStates.js'

/** 渲染层实际持有的骨骼集合（useVrmModel.js 的 RIG_BONES 同源约定） */
const RIG_BONES = ['head', 'chest', 'leftUpperArm', 'rightUpperArm', 'neck', 'leftLowerArm', 'rightLowerArm', 'leftHand', 'rightHand']

/**
 * 回归护栏（2026-11-16）：手势增量叠加 PERSONA_POSE_BASE 后，上臂外展总角
 * 必须保持在"侧上 40° 以内"（|z| < 1.3 rad ≈ 74°），防止再出现 T-pose 时代
 * 绝对角旧值叠加后"直臂举过头顶"的诡异敬礼。
 * base：left +1.15 / right -1.15；外展方向 left 为 z 负增量、right 为 z 正增量，
 * 因此 left 总角 = 1.15 + delta（delta 应为负），right 总角 = -1.15 + delta（delta 应为正）。
 */
function assertArmWithinShoulderRange() {
  const STEP = 0.02
  for (const name of PERSONA_GESTURE_NAMES) {
    const gesture = PERSONA_GESTURES[name]
    for (let t = 0; t <= gesture.duration; t += STEP) {
      const pose = sampleGesture(gesture, t)
      for (const [bone, baseDelta] of [['leftUpperArm', 1.15], ['rightUpperArm', -1.15]]) {
        const delta = pose[bone]?.z ?? 0
        const total = baseDelta + delta
        assert.ok(
          Math.abs(total) < 1.3,
          `${name} t=${t.toFixed(2)}s ${bone} 外展总角 ${total.toFixed(2)} rad 越过肩线（base ${baseDelta} + 增量 ${delta}）`
        )
      }
    }
  }
}

describe('手势动作库（personaGestures）', () => {
  test('三十四个手势全部注册且关键帧自洽', () => {
    assert.deepEqual(
      [...PERSONA_GESTURE_NAMES].sort(),
      [
        'angry', 'applaud', 'armsCrossed', 'bow', 'cheer', 'deepBow', 'facepalm',
        'greet', 'handOnHip', 'heart', 'laugh', 'leanBack', 'leanIn', 'lookAround',
        'nod', 'openArms', 'point', 'pointUp', 'radioCall', 'salute', 'shake',
        'shiver', 'shrug', 'shy', 'signalCover', 'signalStop', 'sleep', 'snap',
        'stretch', 'sway', 'think', 'thumbUp', 'tilt', 'wave'
      ]
    )
    for (const name of PERSONA_GESTURE_NAMES) {
      const gesture = PERSONA_GESTURES[name]
      assert.ok(gesture.duration > 0, `${name} duration 必须为正`)
      assert.ok(gesture.keys.length >= 2, `${name} 至少两个关键帧`)
    }
  })

  test('任意时刻上臂外展总角（base+增量）不越过肩线（防诡异敬礼回归）', () => {
    assertArmWithinShoulderRange()
  })

  test('validateGestures 对合法库零告警', () => {
    assert.deepEqual(validateGestures(PERSONA_GESTURES, RIG_BONES), [])
  })

  test('validateGestures 拦截未知骨骼与首尾非零增量', () => {
    const problems = validateGestures(
      {
        bad: {
          duration: 1,
          keys: [
            { t: 0, pose: { hips: { x: 0.1 } } },
            { t: 1, pose: { head: { x: 0.2 } } }
          ]
        }
      },
      RIG_BONES
    )
    assert.ok(problems.some((line) => line.includes('hips')), '未知骨骼应被拦截')
    assert.ok(problems.some((line) => line.includes('首关键帧')), '首帧非零应被拦截')
    assert.ok(problems.some((line) => line.includes('末关键帧')), '末帧非零/非 t=1 应被拦截')
  })

  test('sampleGesture：t=0 与播完返回空增量（无跳变起止）', () => {
    for (const name of PERSONA_GESTURE_NAMES) {
      assert.deepEqual(sampleGesture(PERSONA_GESTURES[name], 0), {}, `${name} 起点应为空`)
      assert.deepEqual(sampleGesture(PERSONA_GESTURES[name], PERSONA_GESTURES[name].duration), {}, `${name} 终点应为空`)
      assert.deepEqual(sampleGesture(PERSONA_GESTURES[name], PERSONA_GESTURES[name].duration + 5), {}, `${name} 越界应为空`)
    }
  })

  test('sampleGesture：中段给出有界骨骼增量（弧度不超过 ±3.2）', () => {
    for (const name of PERSONA_GESTURE_NAMES) {
      const gesture = PERSONA_GESTURES[name]
      const mid = sampleGesture(gesture, gesture.duration * 0.5)
      assert.ok(Object.keys(mid).length >= 1, `${name} 中段应有动作`)
      for (const [bone, delta] of Object.entries(mid)) {
        assert.ok(RIG_BONES.includes(bone), `${name} 引用了未知骨骼 ${bone}`)
        for (const axis of ['x', 'y', 'z']) {
          assert.ok(
            Math.abs(delta[axis]) <= 3.2,
            `${name}.${bone}.${axis} 增量越界：${delta[axis]}`
          )
        }
      }
    }
  })

  test('sampleGesture：同一手势两个相邻采样点差异连续（无跳变）', () => {
    const gesture = PERSONA_GESTURES.wave
    let previous = sampleGesture(gesture, 0.2)
    for (let seconds = 0.25; seconds <= 1.3; seconds += 0.05) {
      const next = sampleGesture(gesture, seconds)
      for (const bone of Object.keys(next)) {
        const before = previous[bone] ?? { x: 0, y: 0, z: 0 }
        for (const axis of ['x', 'y', 'z']) {
          assert.ok(
            Math.abs(next[bone][axis] - before[axis]) < 0.5,
            `wave 在 ${seconds}s 处 ${bone}.${axis} 出现跳变`
          )
        }
      }
      previous = next
    }
  })

  test('挥手至少两拍摆动：前臂 z 增量在时长内改变符号或至少两次跨越', () => {
    const gesture = PERSONA_GESTURES.wave
    const samples = []
    for (let i = 0; i <= 40; i += 1) {
      samples.push(sampleGesture(gesture, (gesture.duration * i) / 40))
    }
    const armValues = samples.filter((s) => s.rightLowerArm).map((s) => s.rightLowerArm.z)
    assert.ok(armValues.length >= 10, '右前臂应有持续动作区间')
    const min = Math.min(...armValues)
    const max = Math.max(...armValues)
    assert.ok(max - min > 0.3, `前臂摆幅过小：${min}~${max}`)
  })

  test('打瞌睡至少三拍点头且渐弱（idle 彩蛋语义）', () => {
    const gesture = PERSONA_GESTURES.sleep
    const peaks = gesture.keys.filter((k) => (k.pose.head?.x ?? 0) >= 0.15)
    assert.ok(peaks.length >= 3, `应有至少 3 个点头峰值，实际 ${peaks.length}`)
    const values = peaks.map((k) => k.pose.head.x)
    assert.ok(values[values.length - 1] < values[0], '峰值应渐弱（最后一拍小于第一拍）')
  })
})

describe('手势表情轨道（PERSONA_GESTURE_EXPRESSIONS）', () => {
  test('只登记真实手势，权重在 0~1，首尾回归 0', () => {
    for (const [name, track] of Object.entries(PERSONA_GESTURE_EXPRESSIONS)) {
      assert.ok(PERSONA_GESTURE_NAMES.includes(name), `表情轨道引用了未登记手势 ${name}`)
      assert.ok(track.length >= 2, `${name} 表情轨道至少两个关键帧`)
      assert.deepEqual(track[0].weights, {}, `${name} 首帧必须无表情增量`)
      assert.deepEqual(track[track.length - 1].weights, {}, `${name} 末帧必须回零`)
      for (const key of track) {
        assert.ok(key.t >= 0 && key.t <= 1, `${name} 关键帧 t 越界：${key.t}`)
        for (const [channel, weight] of Object.entries(key.weights)) {
          assert.ok(weight > 0 && weight <= 1, `${name}.${channel} 权重非法：${weight}`)
        }
      }
    }
  })

  test('情绪类动作的表情与语义一致（笑是 happy、生气是 angry、瞌睡闭眼）', () => {
    const peak = (name) => {
      const gesture = PERSONA_GESTURES[name]
      let best = {}
      for (let s = 0; s <= gesture.duration; s += 0.02) {
        const sample = sampleGestureExpressions(name, s)
        if ((sample.happy ?? 0) + (sample.angry ?? 0) + (sample.blink ?? 0) >
            (best.happy ?? 0) + (best.angry ?? 0) + (best.blink ?? 0)) {
          best = sample
        }
      }
      return best
    }
    assert.ok((peak('laugh').happy ?? 0) > 0.5, 'laugh 应有明显的 happy')
    assert.ok((peak('angry').angry ?? 0) > 0.5, 'angry 应有明显的 angry')
    assert.ok((peak('sleep').blink ?? 0) > 0.9, 'sleep 应闭眼')
  })

  test('未登记手势与首尾时刻返回空对象（渲染层静默降级）', () => {
    assert.deepEqual(sampleGestureExpressions('not-exist', 0.5), {})
    assert.deepEqual(sampleGestureExpressions('laugh', 0), {})
    assert.deepEqual(sampleGestureExpressions('laugh', PERSONA_GESTURES.laugh.duration), {})
  })
})

describe('手势口播文案（PERSONA_GESTURE_VOICES）', () => {
  test('与动作库一一对应：新增手势必须同步补文案', () => {
    assert.deepEqual(
      Object.keys(PERSONA_GESTURE_VOICES).sort(),
      [...PERSONA_GESTURE_NAMES].sort()
    )
  })

  test('文案均为 ≤20 字、无首尾空白的短句，且不重复', () => {
    const seen = new Set()
    for (const name of PERSONA_GESTURE_NAMES) {
      const line = gestureVoice(name, () => 0)
      assert.ok(line.length > 0, `${name} 缺少文案`)
      assert.ok(line.length <= 20, `${name} 文案过长（${line.length} 字）：${line}`)
      assert.equal(line, line.trim(), `${name} 文案含首尾空白`)
      assert.ok(!seen.has(line), `${name} 文案与其他手势重复：${line}`)
      seen.add(line)
    }
  })

  test('未登记的手势返回空串（调用方静默降级）', () => {
    assert.equal(gestureVoice('not-exist'), '')
    assert.equal(gestureVoice(), '')
  })

  test('变体覆盖全部手势，首句与主文案一致，句句短且不重复', () => {
    // 全量覆盖：新增手势必须同步补变体，否则只会有唯一一句台词
    assert.deepEqual(
      Object.keys(PERSONA_GESTURE_VOICE_VARIANTS).sort(),
      [...PERSONA_GESTURE_NAMES].sort()
    )
    const allLines = new Set(Object.values(PERSONA_GESTURE_VOICES))
    for (const [name, variants] of Object.entries(PERSONA_GESTURE_VOICE_VARIANTS)) {
      assert.ok(PERSONA_GESTURE_NAMES.includes(name), `变体引用了未登记手势 ${name}`)
      assert.ok(variants.length >= 2, `${name} 至少 2 句变体`)
      assert.equal(variants[0], PERSONA_GESTURE_VOICES[name], `${name} 首句必须等于主文案`)
      for (const [index, line] of variants.entries()) {
        assert.ok(line.length > 0 && line.length <= 20, `${name} 变体过长/为空：${line}`)
        assert.equal(line, line.trim(), `${name} 变体含首尾空白`)
        // 首句就是主文案本身（已在全局集合里），只校验新增变体是否撞车
        if (index === 0) continue
        assert.ok(!allLines.has(line), `${name} 变体与其他文案重复：${line}`)
        allLines.add(line)
      }
    }
  })

  test('gestureVoice 按注入的随机源取变体，且不越界', () => {
    assert.equal(gestureVoice('signalStop', () => 0), '先停一下。')
    assert.equal(gestureVoice('signalStop', () => 0.99), '暂停，听我说。')
    assert.equal(gestureVoice('signalStop', () => 1), '暂停，听我说。')
    // 全部手势都有变体：wave 随机取到末句
    assert.equal(gestureVoice('wave', () => 0.99), '我在这儿呢，挥个手。')
    // 未登记名仍走主文案表（空串）
    assert.equal(gestureVoice('unknown', () => 0.99), '')
  })
})
