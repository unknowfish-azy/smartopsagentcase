import assert from 'node:assert/strict'
import test from 'node:test'

import { getProcessDiagnosticScenario, processDiagnosticScenarios } from '../src/views/operations/processDiagnostics.js'

test('provides the four read-only process diagnostic scenarios', () => {
  assert.deepEqual(processDiagnosticScenarios.map(scenario => scenario.id), ['server-slow', 'cpu-high', 'process-d-state', 'process-zombie'])
})

test('every process diagnostic command is read-only and observational', () => {
  const forbidden = /kill|renice|restart|shutdown|rm|drop/i
  for (const scenario of processDiagnosticScenarios) {
    for (const command of scenario.commands) {
      assert.equal(command.readOnly, true)
      assert.equal(forbidden.test(command.command), false, `${scenario.id}: ${command.command}`)
    }
  }
})

test('unknown process diagnostic scenarios return null', () => {
  assert.equal(getProcessDiagnosticScenario('missing'), null)
})
