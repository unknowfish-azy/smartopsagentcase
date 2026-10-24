import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { createFaultEvent, createInvestigationContext } from '../src/domain/investigation/faultEvent.js'
import { useInvestigationStore } from '../src/stores/investigation.js'

test('Fault Event requires evidence and never grants execution permission', () => {
  assert.throws(() => createFaultEvent({ title: '502' }), /至少一条证据/)
  const event = createFaultEvent({ title: '502 Bad Gateway', source: 'OCR', evidence: [{ source: 'OCR', content: '502 Bad Gateway', confidence: 1.4 }] })
  assert.equal(event.severity, 'MEDIUM')
  assert.equal(event.evidence[0].confidence, 1)
  assert.equal(event.executionAllowed, false)
})

test('Investigation Context keeps evidence and supports knowledge references without execution', () => {
  const event = createFaultEvent({ title: 'API 500', evidence: [{ source: 'API', content: 'status=500' }] })
  const context = createInvestigationContext(event)
  assert.equal(context.state, 'STARTING')
  assert.deepEqual(context.evidence, event.evidence)
  assert.equal(context.executionAllowed, false)
  setActivePinia(createPinia())
  const store = useInvestigationStore()
  store.detect({ title: 'API 500', evidence: [{ source: 'API', content: 'status=500' }] })
  store.addKnowledgeReference({ documentId: 'runbook-500', title: 'API 500 Runbook' })
  assert.equal(store.activeContext.knowledgeReferences[0].documentId, 'runbook-500')
  assert.equal(store.activeContext.executionAllowed, false)
})
