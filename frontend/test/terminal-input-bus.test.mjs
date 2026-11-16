import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasTerminalInput, registerTerminalInput, unregisterTerminalInput, writeToTerminal } from '../src/components/operations/terminalInputBus.js'

test('registered terminals receive INPUT through the real path', () => {
  const sent = []
  registerTerminalInput('rt-1', (type, extra) => sent.push({ type, ...extra }))
  assert.equal(hasTerminalInput('rt-1'), true)
  assert.equal(writeToTerminal('rt-1', 'ls -la\r'), true)
  assert.deepEqual(sent, [{ type: 'INPUT', data: 'ls -la\r' }])
  unregisterTerminalInput('rt-1')
  assert.equal(hasTerminalInput('rt-1'), false)
  assert.equal(writeToTerminal('rt-1', 'x'), false)
})

test('registration guards invalid input', () => {
  registerTerminalInput('', () => {})
  registerTerminalInput('rt-2', 'not-a-function')
  assert.equal(hasTerminalInput('rt-2'), false)
  assert.equal(writeToTerminal('rt-2', 'x'), false)
  assert.equal(writeToTerminal('rt-unknown', 'x'), false)
  assert.equal(writeToTerminal('rt-unknown', 42), false)
})
