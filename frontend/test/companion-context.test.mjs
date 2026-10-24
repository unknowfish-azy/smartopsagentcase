import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { createCompanionContext, mergeCompanionContext, snapshotCompanionContext } from '../src/domain/companion/context.ts'
import { resolveAttention } from '../src/domain/companion/attention.ts'
import { useCompanionStore } from '../src/stores/companion.js'

test('companion context keeps a read-only execution boundary', () => {
  const context = createCompanionContext({ id: 'ctx-1', evidence: [{ source: 'OCR', content: '502' }] })
  assert.equal(context.executionAllowed, false)
  const merged = mergeCompanionContext(context, { executionAllowed: true, answers: [{ questionId: 'q1' }] })
  assert.equal(merged.executionAllowed, false)
  assert.equal(snapshotCompanionContext(merged).answers[0].questionId, 'q1')
})

test('attention policy suppresses low impact in quiet modes but preserves critical hint', () => {
  assert.equal(resolveAttention({ severity: 'LOW', userMode: 'QUIET' }), 'silent')
  assert.equal(resolveAttention({ severity: 'CRITICAL', userMode: 'QUIET' }), 'visual_hint')
})

test('companion store ingests faults through the investigation context', () => {
  setActivePinia(createPinia())
  const store = useCompanionStore()
  store.ingestFault({ title: '502 Bad Gateway', source: 'OCR', evidence: [{ source: 'OCR', content: '502' }] })
  assert.equal(store.context.faultEvent.title, '502 Bad Gateway')
  assert.equal(store.context.executionAllowed, false)
  assert.equal(store.states.spider, 'ANOMALY')
})
