import assert from 'node:assert/strict'
import test from 'node:test'

import { routeMetaFor } from '../src/navigation/personalSystemNavigation.js'

test('assigns the execution trace to the Agent group and direct page flow', () => {
  assert.deepEqual(routeMetaFor('ExecutionTrace'), {
    personalGroup: 'agent',
    pageFlow: 'agent'
  })
})

test('keeps inspector detail outside the incomplete memory page flow', () => {
  assert.deepEqual(routeMetaFor('InspectorDetail'), {
    personalGroup: 'memory',
    pageFlow: null
  })
})

test('maps run history to Memory without borrowing inspector page flow', () => {
  assert.deepEqual(routeMetaFor('OperationRunHistory'), {
    personalGroup: 'memory',
    pageFlow: null
  })
})
