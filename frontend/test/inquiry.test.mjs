import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { questionsForFault, normalizeAnswer } from '../src/domain/investigation/inquiry.ts'
import { createFaultEvent } from '../src/domain/investigation/faultEvent.ts'
import { useInvestigationStore } from '../src/stores/investigation.js'

test('502 faults produce a prioritized structured inquiry', () => {
  const questions = questionsForFault({ title: '502 Bad Gateway', evidence: [{ content: 'upstream unavailable' }] })
  assert.equal(questions.length, 3)
  assert.equal(questions[0].id, 'persistence')
  assert.ok(questions.every(question => question.prompt && question.why && question.options.length))
})

test('unknown faults start with impact scope question', () => {
  assert.equal(questionsForFault({ title: 'Worker stalled' })[0].id, 'scope')
})

test('answers preserve original value and normalized option', () => {
  const question = questionsForFault({ title: '502' })[0]
  const answer = normalizeAnswer(question, 'persistent')
  assert.equal(answer.original, 'persistent')
  assert.equal(answer.value, 'persistent')
  assert.equal(answer.confidence, 1)
})

test('investigation store keeps answers and knowledge references read-only', () => {
  setActivePinia(createPinia())
  const store = useInvestigationStore()
  store.$reset()
  const fault = createFaultEvent({ title: '502 Bad Gateway', evidence: [{ source: 'OCR', content: '502 Bad Gateway' }] })
  store.detect(fault)
  store.addAnswer({ questionId: 'persistence', original: '持续发生', normalized: { value: 'persistent' }, confidence: 0.6 })
  store.addKnowledgeReference({ documentId: 'nginx-502-diagnosis', title: '502 Runbook', source: 'local', section: 'Diagnosis' })
  assert.equal(store.activeContext.answers[0].questionId, 'persistence')
  assert.equal(store.activeContext.knowledgeReferences[0].documentId, 'nginx-502-diagnosis')
  assert.equal(store.activeContext.executionAllowed, false)
})
