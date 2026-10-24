import test from 'node:test'
import assert from 'node:assert/strict'
import * as workspace from '../src/components/operations/connectionWorkspace.js'

test('visible panes keep independent runtimes and limit split to four', () => {
  const tabs = Array.from({ length: 6 }, (_, i) => ({ runtimeId: `r${i}` }))
  assert.deepEqual(workspace.visibleRuntimeIds?.(tabs, 'r5', 'SINGLE'), ['r5'])
  assert.deepEqual(workspace.visibleRuntimeIds?.(tabs, 'r5', 'SPLIT_VERTICAL'), ['r5', 'r0', 'r1', 'r2'])
})

test('file paths reject names that escape the selected folder', () => {
  assert.equal(workspace.remoteChild?.('/tmp', 'a b.txt'), '/tmp/a b.txt')
  for (const name of ['../secret', '.', '..', 'a/b', 'a\\b', 'bad\u0000name']) {
    assert.throws(() => workspace.remoteChild('/tmp', name))
  }
})

test('WebSocket endpoint follows configured backend on every Vite port', () => {
  assert.equal(workspace.terminalEndpoint?.('', 'http://127.0.0.1:5173'), 'ws://127.0.0.1:5173/ws/operations/terminal')
  assert.equal(workspace.terminalEndpoint?.('http://localhost:8080', 'http://localhost:5175'), 'ws://localhost:8080/ws/operations/terminal')
  assert.equal(workspace.terminalEndpoint?.('/bridge', 'https://ops.example'), 'wss://ops.example/bridge/ws/operations/terminal')
})
