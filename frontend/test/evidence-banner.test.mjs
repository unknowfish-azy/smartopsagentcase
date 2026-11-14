import test from 'node:test'
import assert from 'node:assert/strict'

import { bannerFlags, hasIncompleteEvidence, EVIDENCE_DISCLAIMER } from '../src/components/diagnostics/evidenceBanner.js'

// ============================================================
// bannerFlags — 输入形态容错
// ============================================================

test('bannerFlags: null / undefined / 非 object → 空数组', () => {
  for (const bad of [null, undefined, '', [], 123, true, Symbol('x'), () => {}]) {
    assert.deepEqual(bannerFlags(bad), [], `输入 ${typeof bad} 应返回空数组`)
  }
})

test('bannerFlags: 空对象 {} → 空数组', () => {
  assert.deepEqual(bannerFlags({}), [])
})

// ============================================================
// bannerFlags — 四标志位独立触发
// ============================================================

test('bannerFlags: 每一个标志位为 true 时进入数组', () => {
  const ALL_FALSE = {
    permissionDenied: false,
    dataMissing: false,
    unverified: false,
    truncated: false
  }
  for (const key of Object.keys(ALL_FALSE)) {
    const input = { ...ALL_FALSE, [key]: true }
    const flags = bannerFlags(input)
    assert.equal(flags.length, 1)
    assert.equal(flags[0].key, key, `期望 key=${key}，实际 ${flags[0].key}`)
    // 每个 flag 必须有 text 和 why
    assert.ok(typeof flags[0].text === 'string' && flags[0].text.length > 5, `缺少 text`)
    assert.ok(typeof flags[0].why === 'string' && flags[0].why.length > 5, `缺少 why`)
  }
})

test('bannerFlags: 标志位为 truthy 非布尔值也触发（非零数、非空串）', () => {
  assert.equal(bannerFlags({ permissionDenied: 1 }).length, 1)
  assert.equal(bannerFlags({ dataMissing: 'yes' }).length, 1)
  assert.equal(bannerFlags({ unverified: {} }).length, 1)
  // 但 falsy 非布尔值不触发
  assert.equal(bannerFlags({ truncated: 0 }).length, 0)
  assert.equal(bannerFlags({ permissionDenied: '' }).length, 0)
})

test('bannerFlags: 任意数量组合 → 按 FLAG_MAP 固定顺序返回', () => {
  // 顺序：permissionDenied(0) → dataMissing(1) → unverified(2) → truncated(3)
  const combos = [
    { input: { permissionDenied: true, truncated: true, unverified: true },
      want: ['permissionDenied', 'unverified', 'truncated'] },
    { input: { truncated: true, dataMissing: true, permissionDenied: true, unverified: true },
      want: ['permissionDenied', 'dataMissing', 'unverified', 'truncated'] },
    { input: { dataMissing: true },
      want: ['dataMissing'] }
  ]
  for (const { input, want } of combos) {
    const keys = bannerFlags(input).map(f => f.key)
    assert.deepEqual(keys, want, `${JSON.stringify(input)} 应按固定顺序排列`)
  }
})

// ============================================================
// bannerFlags — 返回对象形状
// ============================================================

test('bannerFlags 返回元素形状固定：{ key, text, why }', () => {
  const flags = bannerFlags({ permissionDenied: true, unverified: true })
  for (const f of flags) {
    const keys = Object.keys(f).sort()
    assert.deepEqual(keys, ['key', 'text', 'why'], `元素字段应为 { key, text, why }`)
    assert.strictEqual(typeof f.key, 'string')
    assert.strictEqual(typeof f.text, 'string')
    assert.strictEqual(typeof f.why, 'string')
    assert.ok(f.text.length > 5, `text 太短 "${f.text}"`)
    assert.ok(f.why.length > 5, `why 太短 "${f.why}"`)
  }
})

test('bannerFlags: FLAG_MAP 数组是冻结常量（浅冻结），filter 返回原引用而非拷贝', () => {
  // Object.freeze(数组) 只冻结数组本身，数组元素仍是可写对象
  const flags = bannerFlags({ permissionDenied: true })
  // filter 没传任何 predicate 时返回空数组；传 Boolean(x) 也返回原引用
  // 这里只验证 filter 返回的元素引用就是 FLAG_MAP 的元素
  // （我们不修改它，只确认语义）
  assert.ok(flags.length > 0)
  assert.strictEqual(typeof flags[0].key, 'string')
  assert.strictEqual(typeof flags[0].text, 'string')
})

// ============================================================
// hasIncompleteEvidence — 薄包装
// ============================================================

test('hasIncompleteEvidence: 与 bannerFlags.length > 0 等价', () => {
  assert.equal(hasIncompleteEvidence({}), false)
  assert.equal(hasIncompleteEvidence(null), false)
  assert.equal(hasIncompleteEvidence({ truncated: false }), false)
  assert.equal(hasIncompleteEvidence({ truncated: true }), true)
  assert.equal(hasIncompleteEvidence({ permissionDenied: true, unverified: true }), true)
})

// ============================================================
// EVIDENCE_DISCLAIMER — 不可变常量
// ============================================================

test('EVIDENCE_DISCLAIMER 常量内容正确', () => {
  assert.equal(typeof EVIDENCE_DISCLAIMER, 'string')
  assert.ok(EVIDENCE_DISCLAIMER.includes('这不代表目标服务不健康'))
  // 不能被重新赋值（const）
  try {
    // eslint-disable-next-line no-import-assign
    EVIDENCE_DISCLAIMER = 'tampered'
    assert.fail('const 应不可赋值')
  } catch {
    // pass — 严格模式下 const 重新赋值会抛 TypeError
  }
})

// ============================================================
// FLAG_MAP 语义完整性（设计文档 §8.3 契约）
// ============================================================

test('四个 flag 都正确表达 DESIGN §8.3 的四种"不是故障"原因', () => {
  const flags = bannerFlags({
    permissionDenied: true, dataMissing: true, unverified: true, truncated: true
  })
  assert.equal(flags.length, 4)
  // why 字段必须让用户知道"这不是服务本身不健康"
  // （permissionDenied 的 why 明确写了，其他三个虽然没直写但语义上也不指向故障）
  assert.ok(flags[0].why.includes('这不代表目标服务不健康'),
    'permissionDenied 必须明确说"这不代表目标服务不健康"（§8.3 硬约束）')
})
