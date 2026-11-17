import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { maskSciverseKey, validateSciverseKey } from './sciverseKey.js'

describe('sciverseKey', () => {
  it('accepts a well-formed sci_ key', () => {
    const result = validateSciverseKey('  sci_i_wNCwoRC139rw5fW5LDueRwr21Beov4tvbWSFe_7fg \n')
    assert.equal(result.ok, true)
    assert.equal(result.value, 'sci_i_wNCwoRC139rw5fW5LDueRwr21Beov4tvbWSFe_7fg')
    assert.equal(result.reason, null)
  })

  it('rejects sk- prefixed keys with an actionable reason', () => {
    const result = validateSciverseKey('sk-Vm1ANv0PpgXhoKRgncu1UMqBvWaDjF07M2DqnuWh3GcjDcRX')
    assert.equal(result.ok, false)
    assert.match(result.reason, /sci_ 开头/)
  })

  it('rejects blank input', () => {
    assert.equal(validateSciverseKey('   ').ok, false)
    assert.equal(validateSciverseKey(null).reason, '密钥不能为空')
  })

  it('rejects truncated keys and whitespace-contaminated copies', () => {
    assert.match(validateSciverseKey('sci_i_short').reason, /长度异常/)
    assert.match(validateSciverseKey('sci_i_wNCw oRC139rw5fW5LDue').reason, /空白字符/)
  })

  it('masks preview without leaking the middle segment', () => {
    const masked = maskSciverseKey('sci_i_wNCwoRC139rw5fW5LDueRwr21Beov4tvbWSFe_7fg')
    assert.match(masked, /^sci_i_…/)
    assert.ok(masked.length < 20)
    assert.equal(maskSciverseKey(''), null)
    assert.equal(maskSciverseKey(null), null)
  })
})
