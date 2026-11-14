import test from 'node:test'
import assert from 'node:assert/strict'

import { verdictText, verdictLevel, freshInfo } from '../src/components/diagnostics/conclusionState.js'

const FIVE_MIN = 5 * 60 * 1000

// ============================================================
// verdictText
// ============================================================

test('verdictText: null/undefined/empty 全返回 "尚未检查 · 没有证据"', () => {
  for (const arg of [null, undefined, {}, [], '']) {
    assert.equal(verdictText(arg), '尚未检查 · 没有证据', `输入 ${JSON.stringify(arg)} 失败`)
  }
})

test('verdictText: action 有值时无论 config/unknown/pass 如何都优先显示 action', () => {
  assert.equal(verdictText({ action: 1, pass: 99 }), '1 项需要处理')
  assert.equal(verdictText({ action: 5, config: 10, unknown: 10, pass: 10 }), '5 项需要处理')
  assert.equal(verdictText({ action: 1 }), '1 项需要处理')
})

test('verdictText: 无 action 有 config → 显示 config', () => {
  assert.equal(verdictText({ config: 1 }), '1 项等待配置')
  assert.equal(verdictText({ config: 3, pass: 5 }), '3 项等待配置')
  assert.equal(verdictText({ config: 3, unknown: 100, pass: 100 }), '3 项等待配置')
})

test('verdictText: 无 action/config 有 unknown → 显示 unknown', () => {
  assert.equal(verdictText({ unknown: 1 }), '1 项缺少证据')
  assert.equal(verdictText({ unknown: 4, pass: 6 }), '4 项缺少证据')
})

test('verdictText: 只有 pass → "全部通过 · X 项检查"', () => {
  assert.equal(verdictText({ pass: 7 }), '全部通过 · 7 项检查')
  assert.equal(verdictText({ pass: 1 }), '全部通过 · 1 项检查')
})

test('verdictText: counts 中带 forbidden 时不影响 verdict（不在四个主桶里）', () => {
  // forbidden 是第五组，verdictText 聚合 total 不包含它
  assert.equal(verdictText({ action: 1, forbidden: 3 }), '1 项需要处理')
  assert.equal(verdictText({ forbidden: 5 }), '尚未检查 · 没有证据')
  assert.equal(verdictText({ pass: 3, forbidden: 4 }), '全部通过 · 3 项检查')
})

test('verdictText: 计数值是字符串/布尔时，|| 0 兜底', () => {
  // counts 里的值理论上都是 number，但防御性编程：非 number falsy 统一当 0
  assert.equal(verdictText({ action: 0, config: undefined, unknown: null }), '尚未检查 · 没有证据')
})

// ============================================================
// verdictLevel
// ============================================================

test('verdictLevel: 与 verdictText 同优先级（action > config > unknown > pass > empty）', () => {
  assert.equal(verdictLevel({ action: 1, pass: 10 }), 'action')
  assert.equal(verdictLevel({ config: 2, unknown: 1 }), 'config')
  assert.equal(verdictLevel({ unknown: 3 }), 'unknown')
  assert.equal(verdictLevel({ pass: 7 }), 'pass')
  assert.equal(verdictLevel({}), 'empty')
})

test('verdictLevel: 空值/缺失 → empty', () => {
  assert.equal(verdictLevel(null), 'empty')
  assert.equal(verdictLevel({}), 'empty')
})

test('verdictLevel: 计数值为 0 或负数时不算存在', () => {
  assert.equal(verdictLevel({ action: 0, config: 0, unknown: 0, pass: 5 }), 'pass')
  assert.equal(verdictLevel({ action: -1, config: 1 }), 'config') // -1 被当成 falsy
})

// ============================================================
// freshInfo — checkedAt 解析
// ============================================================

test('freshInfo: checkedAt=null → ms=0 → 所有输出指向"尚未检查"', () => {
  const info = freshInfo({ checkedAt: null, now: 1_000_000, stale: false })
  assert.equal(info.ringDeg, 0)
  assert.equal(info.ringText, '过期')
  assert.equal(info.ringColorToken, '--ds-semantic-warning')
  assert.equal(info.label, '尚未检查')
  assert.equal(info.absolute, null)
  assert.ok(info.tooltip.includes('尚未执行检查'))
})

test('freshInfo: checkedAt=undefined → 同 null（== null 双重相等）', () => {
  const info = freshInfo({ checkedAt: undefined, now: 1_000_000 })
  assert.equal(info.label, '尚未检查')
})

test('freshInfo: checkedAt 是 number timestamp 直接用', () => {
  const now = 1_000_000
  const checkedAt = now - 60_000 // 1 分钟前
  const info = freshInfo({ checkedAt, now, stale: false })
  assert.ok(info.absolute, 'absolute 必须有值')
  assert.match(info.absolute, /年|月|日|\d{2}:\d{2}/)
})

test('freshInfo: checkedAt 是 ISO string 被 Date.parse', () => {
  const checkedAt = '2025-06-01T12:00:00Z'
  const now = Date.parse('2025-06-01T12:03:00Z') // 3 分钟后
  const info = freshInfo({ checkedAt, now })
  assert.ok(info.ringDeg > 0, '3 分钟后仍应新鲜')
})

test('freshInfo: checkedAt 是无效字符串 → 按 0 处理', () => {
  const info = freshInfo({ checkedAt: 'not-a-date', now: 1_000_000 })
  assert.equal(info.label, '尚未检查')
  assert.equal(info.ringText, '过期')
})

test('freshInfo: now 缺省 → Date.now()', () => {
  const before = Date.now()
  const info = freshInfo({ checkedAt: before - 1000 })
  const after = Date.now()
  // fresh 必须是 true（刚检查过，没过期）
  assert.equal(info.ringText, '5′') // 刚检查过应该显示 5'
  assert.ok(info.ringDeg >= 0 && info.ringDeg <= 360)
})

// ============================================================
// freshInfo — ringDeg / ringText / ringColorToken
// ============================================================

test('freshInfo: 刚检查（age=1s）→ ringDeg≈360, ringText="5′", token=info', () => {
  const now = 1_000_000
  const info = freshInfo({ checkedAt: now - 1000, now, stale: false })
  assert.ok(info.ringDeg >= 358, `期望 ≈360，实际 ${info.ringDeg}`)
  assert.equal(info.ringText, '5′')
  assert.equal(info.ringColorToken, '--ds-semantic-info')
})

test('freshInfo: 正好 5 分钟 → remain=0 → ringDeg=0, ringText="过期"', () => {
  const now = 1_000_000
  const info = freshInfo({ checkedAt: now - FIVE_MIN, now, stale: false })
  assert.equal(info.ringDeg, 0)
  assert.equal(info.ringText, '过期')
  assert.equal(info.ringColorToken, '--ds-semantic-warning')
})

test('freshInfo: 超 5 分钟 → remain 被 Math.max 夹紧到 0 → ringDeg=0', () => {
  const now = 1_000_000
  const info = freshInfo({ checkedAt: now - FIVE_MIN - 60_000, now, stale: false })
  assert.equal(info.ringDeg, 0)
  assert.equal(info.ringText, '过期')
})

test('freshInfo: stale=true 即使 age=1s 也强制 ringText=过期 + warning token', () => {
  const now = 1_000_000
  const info = freshInfo({ checkedAt: now - 1000, now, stale: true })
  // stale=true 时 fresh=false → ringText="过期" + warning token
  assert.equal(info.ringText, '过期')
  assert.equal(info.ringColorToken, '--ds-semantic-warning')
  // 但 ringDeg 按 remainMs 正常算（remain=~4:59，ringDeg≈359）
  assert.ok(info.ringDeg > 0)
})

test('freshInfo: 剩余 2 分 30 秒 → ringDeg=180, ringText="3′"（ceil(150/60)=3）', () => {
  const now = 1_000_000
  const remain = 150_000 // 2.5 min
  const info = freshInfo({ checkedAt: now - (FIVE_MIN - remain), now, stale: false })
  assert.equal(info.ringDeg, 180)
  assert.equal(info.ringText, '3′')
})

// ============================================================
// freshInfo — fmtAgo 边界
// ============================================================

test('freshInfo: fmtAgo → "刚刚"（<30s）/ "N 分钟前" / "N 小时前"', () => {
  // Math.round(age/60000) 四舍五入：59999ms → round(0.9998)=1，60000ms → 1
  // 真正 <1 分钟的是 age < 30_000ms（round 后仍 <1）
  const cases = [
    [0, '刚刚'],
    [29_999, '刚刚'],
    [30_000, '1 分钟前'], // round(0.5)=1
    [3 * 60_000, '3 分钟前'],
    [59 * 60_000, '59 分钟前'],
    [60 * 60_000, '1 小时前'],
    [3 * 60 * 60_000, '3 小时前']
  ]
  for (const [age, want] of cases) {
    const info = freshInfo({ checkedAt: 100_000, now: 100_000 + age, stale: false })
    assert.ok(info.label.includes(want), `age=${age}ms → "${info.label}" 应含 "${want}"`)
  }
})

// ============================================================
// freshInfo — tooltip 分支
// ============================================================

test('freshInfo: tooltip 分支 — 正常剩余时间', () => {
  const now = 1_000_000
  const checkedAt = now - 60_000 // age=1min, remain=4min
  const info = freshInfo({ checkedAt, now, stale: false })
  assert.ok(info.tooltip.includes('最近获取'))
  assert.ok(info.tooltip.includes('4 分钟后过期'), `剩余 4 分钟应说"4 分钟后过期"，实际：${info.tooltip}`)
})

test('freshInfo: tooltip 分支 — 剩余 <60s 但 remainMs>0 → 走 "即将过期"（不再说"0 分钟后过期"）', () => {
  const now = 1_000_000
  const checkedAt = now - FIVE_MIN + 1000 // remain=1s，age≈4:59
  const info = freshInfo({ checkedAt, now, stale: false })
  // 优化后：remainMs < 60_000 时统一走"即将过期"，不再出现"0 分钟后过期"
  assert.ok(info.tooltip.includes('即将过期'),
    `remain=1s 应走"即将过期"，实际：${info.tooltip}`)
  assert.doesNotMatch(info.tooltip, /0 分钟后过期/)
})

test('freshInfo: tooltip 分支 — 正好 5 分钟 remainMs=0 → 走 "即将过期"', () => {
  const now = 1_000_000
  const checkedAt = now - FIVE_MIN // 正好 5min，remainMs=0（Math.max 夹紧）
  const info = freshInfo({ checkedAt, now, stale: false })
  // remainMs=0 → 不 stale 不 >0 → 走 "即将过期"
  assert.ok(info.tooltip.includes('即将过期'), `remainMs=0 应走"即将过期"，实际：${info.tooltip}`)
})

test('freshInfo: tooltip 分支 — stale=true → "已过期 N 分钟"', () => {
  const now = 1_000_000
  const checkedAt = now - FIVE_MIN - 3 * 60_000 // 总共过期 3 min
  const info = freshInfo({ checkedAt, now, stale: true })
  assert.ok(info.tooltip.includes('已过期'), `stale=true 应含"已过期"，实际：${info.tooltip}`)
  // Math.max(1, ...) 保证过期分钟数最小为 1（不会出现 0 分钟已过期）
  assert.ok(/已过期 \d+ 分钟/.test(info.tooltip), `过期分钟数必须是正整数，实际：${info.tooltip}`)
})

test('freshInfo: tooltip — checkedAt=null → 只说"尚未执行检查"', () => {
  const info = freshInfo({ checkedAt: null, now: 1_000_000 })
  assert.equal(info.tooltip, '尚未执行检查')
})

// ============================================================
// freshInfo — 返回值形状（不破坏现有消费方）
// ============================================================

test('freshInfo 返回值有且只有 6 个字段，且语义正确', () => {
  const info = freshInfo({ checkedAt: Date.now() - 1000, stale: false })
  const keys = Object.keys(info).sort()
  assert.deepEqual(keys, ['absolute', 'label', 'ringColorToken', 'ringDeg', 'ringText', 'tooltip'])

  assert.strictEqual(typeof info.ringDeg, 'number')
  assert.strictEqual(typeof info.ringText, 'string')
  assert.strictEqual(typeof info.ringColorToken, 'string')
  assert.strictEqual(typeof info.tooltip, 'string')
  assert.strictEqual(typeof info.label, 'string')
  // absolute: 有 ms 时是 string，否则 null
  assert.ok(info.absolute === null || typeof info.absolute === 'string')
})

test('freshInfo: absolute 不是 Date 对象（是 toLocaleString 结果字符串）', () => {
  const now = 1_000_000
  const info = freshInfo({ checkedAt: now - 1000, now })
  assert.strictEqual(typeof info.absolute, 'string')
  // 和 null 分支形成对照
  const info2 = freshInfo({ checkedAt: null, now })
  assert.strictEqual(info2.absolute, null)
})
