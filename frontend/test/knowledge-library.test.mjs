import assert from 'node:assert/strict'
import test from 'node:test'

import { knowledgeEntryView } from '../src/views/knowledge/knowledgeLibrary.js'

test('returns a selected knowledge entry with adjacent references', () => {
  const view = knowledgeEntryView('cloud-operations-kubernetes')

  assert.equal(view.current.id, 'cloud-operations-kubernetes')
  assert.equal(view.previous.id, 'cloud-operations-containers')
  assert.equal(view.next.id, 'cloud-operations-learning-path')
})

test('returns null for an unknown knowledge entry', () => {
  assert.equal(knowledgeEntryView('missing-entry'), null)
})
