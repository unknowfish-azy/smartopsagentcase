import test from 'node:test'
import assert from 'node:assert/strict'
import { orderOperationSessions, splitPane } from '../src/api/operationsState.js'

test('splitting one active terminal creates two panes without duplicating the session runtime', () => {
  const state = splitPane({ tabs: [{ runtimeId: 'r1' }], panes: [{ id: 'p1', runtimeId: 'r1' }] }, 'p1', 'vertical')
  assert.equal(state.panes.length, 2)
  assert.equal(new Set(state.panes.map((pane) => pane.runtimeId)).size, 1)
})

test('orders saved operation sessions by recent connection without mutating the source list', () => {
  const sessions = [
    { id: 1, lastConnectedAt: '2026-09-23T10:00:00' },
    { id: 2, lastConnectedAt: '2026-09-23T12:00:00' },
    { id: 3, lastConnectedAt: null }
  ]

  assert.deepEqual(orderOperationSessions(sessions).map(session => session.id), [2, 1, 3])
  assert.deepEqual(sessions.map(session => session.id), [1, 2, 3])
})
