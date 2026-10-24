import assert from 'node:assert/strict'
import test from 'node:test'

import {
  resolveExpandedGroupIds,
  sanitizeExpandedGroupIds,
  toggleExpandedGroupId
} from '../src/navigation/navigationState.js'
import { personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

test('forces the active Agent parent open when persisted state is empty', () => {
  assert.deepEqual(
    resolveExpandedGroupIds('ExecutionTrace', [], personalSystemGroups),
    ['agent']
  )
})

test('drops malformed and stale persisted navigation groups', () => {
  assert.deepEqual(
    sanitizeExpandedGroupIds(['agent', 'question-bank', 42, 'agent'], personalSystemGroups),
    ['agent']
  )
})

test('does not collapse the group that owns the current route', () => {
  assert.deepEqual(
    toggleExpandedGroupId('memory', ['memory'], personalSystemGroups, 'InspectorCenter'),
    ['memory']
  )
})
