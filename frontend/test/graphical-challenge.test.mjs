import assert from 'node:assert/strict'
import test from 'node:test'
import {
  CLICK_HINT,
  addClick,
  displayScene,
  isComplete,
  localChallengeOf,
  pendingClicks,
  progressLabel,
  resetClicks,
  toViewBox
} from '../src/security/graphicalChallenge.js'

const SCENE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200"><circle cx="50" cy="60" r="24" fill="#e2453c"/></svg>'

function policy (overrides = {}) {
  return {
    enabled: true,
    available: true,
    required: true,
    provider: 'local',
    siteKey: '',
    action: 'admin_login',
    challenge: 'a'.repeat(32),
    prompt: '请点击图中的 #e2453c A',
    targets: 1,
    tolerance: 18,
    scene: SCENE,
    ...overrides
  }
}

test('local challenge is only accepted for the local provider and complete payloads', () => {
  const parsed = localChallengeOf(policy())
  assert.deepEqual(parsed, {
    provider: 'local',
    nonce: 'a'.repeat(32),
    prompt: '请点击图中的 #e2453c A',
    scene: SCENE,
    targets: 1,
    tolerance: 18
  })
  // 回归：provider 必须随解析结果一起返回。HumanVerification.vue 用
  // `challenge.provider === 'local'` 判定是否渲染本地图形分支，
  // 一旦这里丢掉 provider，界面就永远不会渲染画布（曾真实发生过）。
  assert.equal(parsed.provider, 'local', 'parsed challenge must stay identifiable as the local provider')
  assert.equal(localChallengeOf(policy({ provider: 'turnstile' })), null)
  assert.equal(localChallengeOf(policy({ provider: 'none' })), null)
  assert.equal(localChallengeOf(null), null)
  assert.equal(localChallengeOf(policy({ challenge: '' })), null)
  assert.equal(localChallengeOf(policy({ scene: '' })), null)
  assert.equal(localChallengeOf(policy({ scene: 'not-a-scene' })), null)
  assert.equal(localChallengeOf(policy({ targets: 0 })), null)
  assert.equal(localChallengeOf(policy({ targets: 1.5 })), null)
  assert.equal(localChallengeOf(policy({ tolerance: 0 })), null)
  assert.equal(localChallengeOf(policy({ prompt: undefined })).prompt, '')
})

test('click state accumulates exactly the requested number of clicks and never overflows', () => {
  let state = { targets: 2, tolerance: 18, pending: [] }
  assert.equal(isComplete(state), false)
  assert.equal(progressLabel(state), '已点击 0/2')
  state = addClick(state, { x: 10, y: 20 })
  assert.equal(state.pending.length, 1)
  assert.equal(isComplete(state), false)
  state = addClick(state, { x: 30, y: 40 })
  assert.equal(isComplete(state), true)
  assert.equal(progressLabel(state), '已点击 2/2')
  const overflow = addClick(state, { x: 99, y: 99 })
  assert.equal(overflow.pending.length, 2, '超出目标数量的点击必须被忽略')
  assert.deepEqual(pendingClicks(state), [{ x: 10, y: 20 }, { x: 30, y: 40 }])
  assert.deepEqual(resetClicks(state).pending, [])
  assert.equal(resetClicks(null), null)
  assert.equal(addClick(null, { x: 1, y: 1 }), null)
  assert.equal(addClick(state, null), state)
})

test('pointer positions convert to the server viewBox coordinate system', () => {
  const box = { left: 100, top: 50, width: 300, height: 200 }
  assert.deepEqual(toViewBox(box, { x: 100, y: 50 }, { width: 300, height: 200 }), { x: 0, y: 0 })
  assert.deepEqual(toViewBox(box, { x: 400, y: 250 }, { width: 300, height: 200 }), { x: 300, y: 200 })
  assert.deepEqual(toViewBox(box, { x: 250, y: 150 }, { width: 300, height: 200 }), { x: 150, y: 100 })
  // 缩放到一半时同一点必须仍然落在同一 viewBox 位置。
  assert.deepEqual(toViewBox({ left: 0, top: 0, width: 150, height: 100 }, { x: 75, y: 50 }, { width: 300, height: 200 }), { x: 150, y: 100 })
  assert.equal(toViewBox(box, { x: 250, y: 150 }, { width: 0, height: 200 }), null)
  assert.equal(toViewBox({ left: 0, top: 0, width: 0, height: 0 }, { x: 1, y: 1 }, { width: 300, height: 200 }), null)
  assert.equal(toViewBox(null, { x: 1, y: 1 }, { width: 300, height: 200 }), null)
  assert.equal(toViewBox(box, null, { width: 300, height: 200 }), null)
  assert.equal(toViewBox(box, { x: 1, y: 1 }, null), null)
})

test('scene markup only gains a display size and keeps every geometry attribute', () => {
  const markup = displayScene(SCENE)
  assert.ok(markup.startsWith('<svg style="width:100%;height:100%;display:block"'))
  assert.ok(markup.includes('viewBox="0 0 300 200"'))
  assert.ok(markup.includes('cx="50" cy="60"'))
  assert.ok(markup.includes('fill="#e2453c"'))
  assert.equal(displayScene(''), '')
  assert.equal(displayScene(null), '')
  assert.equal(displayScene('div'), '')
  // 重复调用保持幂等，不会叠加样式。
  assert.equal(displayScene(markup), markup)
})

test('the hint constant stays user-facing and free of answer data', () => {
  assert.equal(typeof CLICK_HINT, 'string')
  assert.ok(CLICK_HINT.length > 0)
  assert.equal(/[#\d]/.test(CLICK_HINT.replace(/\s/g, '')), false, '提示文案不得包含色值或坐标')
})
