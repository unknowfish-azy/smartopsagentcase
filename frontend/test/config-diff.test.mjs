import test from 'node:test'
import assert from 'node:assert/strict'
import { compareConfigTexts } from '../src/domain/diagnostics/configDiff.js'
import { redactConfigText } from '../src/domain/diagnostics/redactConfig.js'

test('local diff preserves Chinese, whitespace and added/deleted line evidence', () => {
  assert.equal(compareConfigTexts('', '').rows.length, 0)
  const result = compareConfigTexts('名称=旧\r\nport=80', '名称=新\nport=80\nemoji=🐋')
  assert.equal(result.added, 2)
  assert.equal(result.removed, 1)
  assert.equal(result.rows.filter(row => row.type === 'equal').length, 1)
  assert.equal(compareConfigTexts('hello ', 'hello').removed, 1)
  assert.equal(compareConfigTexts('hello ', 'hello', { ignoreTrailingWhitespace: true }).removed, 0)
})
test('secrets are masked but a changed secret still counts as a change', () => {
  const result = compareConfigTexts('password=old-secret\nport=80', 'password=new-secret\nport=80')
  assert.equal(result.added, 1)
  assert.equal(result.removed, 1)
  assert.equal(JSON.stringify(result).includes('old-secret'), false)
  assert.equal(JSON.stringify(result).includes('new-secret'), false)
  const text = redactConfigText('api_key: abcdef\nAuthorization: Bearer danger\n-----BEGIN PRIVATE KEY-----\nmy-key\n-----END PRIVATE KEY-----\nvalue=ok')
  for (const value of ['abcdef', 'danger', 'my-key']) assert.equal(text.includes(value), false)
  assert.equal(text.includes('value=ok'), true)
  assert.equal(redactConfigText('password: |\n  keep-secret\n  also-secret\nport: 80').includes('keep-secret'), false)
})
test('diff limits input size and work rather than allocating unbounded matrices', () => {
  assert.throws(() => compareConfigTexts('中'.repeat(90000), ''), /256/)
  assert.throws(() => compareConfigTexts('line\n'.repeat(5001), ''), /5000/)
  const left = Array.from({ length: 2000 }, (_, index) => `left-${index}`).join('\n')
  const right = Array.from({ length: 2000 }, (_, index) => `right-${index}`).join('\n')
  assert.throws(() => compareConfigTexts(left, right), /计算/)
  assert.equal(compareConfigTexts('<img src=x onerror=alert(1)>', '').rows[0].text, '<img src=x onerror=alert(1)>')
})
