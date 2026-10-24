import assert from 'node:assert/strict'
import test from 'node:test'
import { validateConnection, connectionPayload, filterConnections } from '../src/components/model/modelConnectionForm.js'

const valid = { name: 'My model', provider: 'custom', baseUrl: 'https://gateway.example/v1', modelName: 'my-model', apiKey: 'secret-example', timeoutSeconds: 60, enabled: true }
test('connection validation rejects unsupported URLs, embedded credentials and invalid timeout', () => {
  assert.deepEqual(validateConnection(valid), {})
  for (const url of ['file:///tmp/key', 'javascript:alert(1)', 'https://user:password@example.com/v1', 'https://example.com/v1?api_key=secret']) {
    assert.ok(validateConnection({ ...valid, baseUrl: url }).baseUrl)
  }
  for (const timeoutSeconds of [0, 301, 5.5, NaN]) assert.ok(validateConnection({ ...valid, timeoutSeconds }).timeoutSeconds)
  assert.ok(validateConnection({ ...valid, name: ' ' }).name)
})
test('create requires a key while edit preserves the existing key when left empty', () => {
  assert.ok(validateConnection({ ...valid, apiKey: '' }).apiKey)
  assert.deepEqual(validateConnection({ ...valid, apiKey: '' }, true), {})
  const payload = connectionPayload({ ...valid, name: ' My model ', baseUrl: 'https://gateway.example/v1///', apiKey: '', apiKeyMasked: '****xxxx', id: 123 })
  assert.equal(payload.name, 'My model')
  assert.equal(payload.baseUrl, 'https://gateway.example/v1')
  assert.equal('apiKey' in payload, false)
  assert.equal('apiKeyMasked' in payload, false)
  assert.equal('id' in payload, false)
})
test('connection search combines name, model and provider with enabled filtering', () => {
  const items = [{ ...valid, id: 1 }, { ...valid, id: 2, name: '备用', provider: 'private', enabled: false }]
  assert.deepEqual(filterConnections(items, 'PRIVATE', 'disabled').map(x => x.id), [2])
  assert.deepEqual(filterConnections(items, 'my-model', 'enabled').map(x => x.id), [1])
  assert.equal(filterConnections(items, '', 'all').length, 2)
})
