/**
 * L2 2D 动态兜底的映射层测试。
 * 只测纯函数：状态 → 视觉参数、口型权重 → 嘴型、手势名 → 动画类。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  build2DVisual,
  breathDurationSec,
  gestureClass,
  mouthShape,
  GESTURE_MS
} from '../src/components/persona/persona2d.js'
import { PERSONA_STATES } from '../src/components/persona/personaStates.js'

test('七状态都能映射出有限的 2D 视觉参数', () => {
  for (const state of PERSONA_STATES) {
    const visual = build2DVisual(state)
    assert.equal(visual.state, state)
    assert.match(String(visual.accent), /^#|^rgb/)
    for (const key of ['headTilt', 'headNod', 'headTurn', 'bodyShift', 'gazeX', 'gazeY', 'browLift', 'browAngle', 'eyeOpen', 'blush', 'mouthCurve']) {
      assert.equal(Number.isFinite(visual[key]), true, `${state}.${key} 必须是有限数`)
    }
    assert.ok(visual.breathDuration >= 1.8 && visual.breathDuration <= 5.5)
    assert.ok(visual.breathAmp >= 1 && visual.breathAmp <= 10)
    assert.ok(visual.eyeOpen >= 0.55 && visual.eyeOpen <= 1.15)
  }
})

test('警示/故障状态与待机在头部姿态上有可见差异', () => {
  const idle = build2DVisual('idle')
  for (const state of ['warning', 'error']) {
    const visual = build2DVisual(state)
    const delta = Math.abs(visual.headTilt - idle.headTilt) + Math.abs(visual.headNod - idle.headNod) + Math.abs(visual.headTurn - idle.headTurn)
    assert.ok(delta > 0.5, `${state} 与 idle 的头部姿态差过小：${delta}`)
  }
})

test('呼吸周期随速度收敛，且有上下限', () => {
  assert.ok(Math.abs(breathDurationSec(1.35) - 3.11) < 0.05)
  assert.equal(breathDurationSec(0.1), 5.25)
  assert.equal(breathDurationSec(9), 1.8)
})

test('口型权重映射为开口与宽度，且做边界收敛', () => {
  const closed = mouthShape({})
  assert.equal(closed.open, 0.08)
  assert.equal(closed.wide, 1)

  const aa = mouthShape({ aa: 1 })
  assert.ok(aa.open > 0.85)
  assert.equal(aa.wide, 1)

  const ou = mouthShape({ ou: 1 })
  assert.ok(ou.open < aa.open)
  assert.ok(ou.wide < 1)

  const ee = mouthShape({ ee: 1 })
  assert.ok(ee.wide > 1)

  const clamped = mouthShape({ aa: 3, ee: 3 })
  assert.ok(clamped.open <= 1)
  assert.ok(clamped.wide <= 1.28)
})

test('手势名归一：中英文关键词都能落到固定动画类', () => {
  assert.equal(gestureClass('wave'), 'wave')
  assert.equal(gestureClass('挥手致意'), 'wave')
  assert.equal(gestureClass('bow'), 'bow')
  assert.equal(gestureClass('point_at_poi'), 'point')
  assert.equal(gestureClass('think'), 'think')
  assert.equal(gestureClass('nod'), 'nod')
  assert.equal(gestureClass('shy'), 'shy')
  assert.equal(gestureClass(''), 'ack')
  assert.equal(gestureClass('unknown_motion'), 'ack')
  assert.equal(GESTURE_MS, 900)
})
