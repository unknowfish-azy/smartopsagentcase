import assert from 'node:assert/strict'
import test from 'node:test'

import { stepperView } from '../src/components/navigation/pageStepper.js'

test('disables the previous button at the first direct Agent step', () => {
  const view = stepperView('AgentCommandCenter')

  assert.equal(view.previous.disabled, true)
  assert.equal(view.next.label, 'EXECUTION TRACE')
})

test('hides a stepper view for routes without an implemented sibling flow', () => {
  assert.equal(stepperView('Knowledge'), null)
})
