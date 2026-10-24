import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isPageStepperKeyEligible,
  nextPageStep,
  previousPageStep,
  resolvePageStep
} from '../src/navigation/pageFlow.js'

test('returns direct sibling routes instead of a browser-history target', () => {
  assert.deepEqual(nextPageStep('AgentCommandCenter'), {
    routeName: 'ExecutionTrace', to: '/agent/trace', label: 'EXECUTION TRACE'
  })
  assert.equal(previousPageStep('AgentCommandCenter'), null)
})

test('keeps inspector detail out of an incomplete operation flow', () => {
  assert.equal(resolvePageStep('InspectorDetail'), null)
})

test('does not capture arrow keys from editable or embedded controls', () => {
  assert.equal(isPageStepperKeyEligible({ tagName: 'INPUT', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'TEXTAREA', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'IFRAME', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'BUTTON', isContentEditable: false }), true)
})
