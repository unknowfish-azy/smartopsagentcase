import assert from 'node:assert/strict'
import test from 'node:test'
import { parseFunctionCallResponse } from '../src/domain/agent/functionCallParser.js'

const tools = [{ id: 'host-health', readOnly: true }, { id: 'service-restart', readOnly: false, requireConfirm: true }]

test('parses standard and fenced model function calls', () => {
  assert.equal(parseFunctionCallResponse('{"name":"host-health","arguments":{}}', tools).ok, true)
  const result = parseFunctionCallResponse('```json\n{"tool_call":{"tool_id":"host-health","parameters":{"scope":"local"}}}\n```', tools)
  assert.equal(result.toolId, 'host-health')
  assert.equal(result.parameters.scope, 'local')
})

test('rejects unknown tools and malformed arguments without execution', () => {
  assert.match(parseFunctionCallResponse('{"name":"shell","arguments":{}}', tools).error, /未被允许/)
  assert.match(parseFunctionCallResponse('{"name":"host-health","arguments":[]}', tools).error, /必须是对象/)
  assert.equal(parseFunctionCallResponse('not json', tools).ok, false)
})

test('preserves mutating tool metadata for the confirmation gate', () => {
  const result = parseFunctionCallResponse({ function_call: { name: 'service-restart', arguments: { service: 'nginx' } } }, tools)
  assert.equal(result.ok, true)
  assert.equal(result.tool.requireConfirm, true)
})
