import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { useCompanionStore } from '../src/stores/companion.js'
import { useInvestigationStore } from '../src/stores/investigation.js'

const fault = { id: 'test-fault', title: '502 Bad Gateway', severity: 'HIGH', evidence: [{ source: 'OCR', content: '502' }] }
function setup() { setActivePinia(createPinia()); return useCompanionStore() }

test('full inquiry shares one owner, snapshots Vue proxies and retains answers on close/reopen', () => {
  const store = setup()
  store.ingestFault(fault)
  assert.equal(store.drawerOpen, false)
  store.openInvestigation()
  const questionId = store.contextSnapshot.questions[0].id
  store.recordAnswer({ questionId, original: 'persistent', normalized: { value: 'persistent' } })
  store.recordAnswer({ questionId, original: 'once', normalized: { value: 'once' } })
  const reference = { documentId: 'runbook', title: '502', source: 'local', section: 'Diagnosis', matchedText: 'Check upstream', risk: 'READ_ONLY' }
  store.addKnowledgeReference(reference)
  store.addKnowledgeReference(reference)
  assert.equal(store.contextSnapshot.answers.length, 1)
  assert.equal(store.contextSnapshot.knowledgeReferences.length, 1)
  assert.equal(useInvestigationStore().activeContext.answers[0].original, 'once')
  assert.throws(() => { store.contextSnapshot.answers[0].original = 'mutated' }, TypeError)
  const id = store.context.id
  store.closeInvestigation()
  store.openInvestigation()
  assert.equal(store.context.id, id)
  assert.equal(store.context.answers.length, 1)
  assert.equal(store.context.executionAllowed, false)
  assert.ok(store.events.some(event => event.type === 'KNOWLEDGE_REFERENCED'))
  for (const question of store.context.questions.slice(1)) store.recordAnswer({ questionId: question.id, original: 'unknown' })
  assert.equal(store.context.investigationState, 'READY')
  assert.equal(store.context.recommendations[0].documentId, reference.documentId)
  assert.equal(store.context.recommendations[0].kind, 'RECOMMENDATION')
  assert.equal(store.context.recommendations[0].executionAllowed, false)
})

test('invalid and repeated faults cannot erase a valid investigation', () => {
  const store = setup()
  store.ingestFault(fault)
  const id = store.context.id
  store.ingestFault(fault)
  for (const invalid of [{}, { evidence: [{ content: '  ' }] }, { ...fault, id: 'bad', payload: new Map() }]) assert.throws(() => store.ingestFault(invalid))
  assert.equal(store.context.id, id)
  assert.equal(store.events.filter(event => event.type === 'FAULT_DETECTED').length, 1)
})

test('attention modes actually react to severity and capability loss preserves local inquiry', () => {
  const store = setup()
  store.setInteractionMode('QUIET')
  store.ingestFault(fault)
  assert.equal(store.attentionPolicy, 'silent')
  store.ingestFault({ ...fault, id: 'critical', severity: 'CRITICAL' })
  assert.equal(store.attentionPolicy, 'visual_hint')
  assert.equal(store.drawerOpen, false)
  store.setCapabilityStatus('ai', 'degraded', 'Model unavailable')
  assert.equal(store.contextSnapshot.capabilityStatuses.find(item => item.name === 'ai').status, 'degraded')
  store.openInvestigation()
  store.recordAnswer({ questionId: store.context.questions[0].id, original: 'unknown' })
  assert.equal(store.context.answers.length, 1)
  assert.equal(store.states.whale, 'UNKNOWN')
  assert.equal(store.context.executionAllowed, false)
})

test('legacy bridge cleanup and separate Pinia sessions prevent duplicate or cross-session delivery', () => {
  const first = setup(), target = new EventTarget()
  const disconnect = first.connectLegacyEvents(target)
  target.dispatchEvent(new CustomEvent('smartops:fault-detected', { detail: fault }))
  assert.equal(first.context.faultEvent.id, fault.id)
  disconnect()
  target.dispatchEvent(new CustomEvent('smartops:fault-detected', { detail: { ...fault, id: 'ignored' } }))
  assert.equal(first.context.faultEvent.id, fault.id)
  const second = setup()
  assert.equal(second.context.faultEvent, null)
  let delivered = 0
  second.subscribe('ANSWER_RECORDED', () => delivered++)
  first.publish('ANSWER_RECORDED')
  assert.equal(delivered, 0)
})
