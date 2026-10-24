import assert from 'node:assert/strict'
import test from 'node:test'
import { advanceToolCallPlan, canExecuteToolCall, createToolCallPlan } from '../src/domain/agent/toolCallPlan.js'

test('creates a read-only plan at preview without granting execution yet', () => {
  const plan = createToolCallPlan({ task: '检查主机负载', tool: { id: 'host-health', readOnly: true, riskLevel: 'LOW' } })
  assert.equal(plan.phase, 'PREVIEW')
  assert.equal(plan.requiresConfirmation, false)
  assert.equal(canExecuteToolCall(plan), false)
  assert.equal(advanceToolCallPlan(plan).phase, 'RISK_CHECK')
})

test('stops mutating tools at confirmation and requires an explicit event', () => {
  const plan = createToolCallPlan({ task: '抑制告警', tool: { id: 'alerts-suppress', readOnly: false, requireConfirm: true, riskLevel: 'HIGH' } })
  assert.equal(plan.phase, 'AWAIT_CONFIRMATION')
  assert.equal(advanceToolCallPlan(plan).phase, 'AWAIT_CONFIRMATION')
  assert.equal(advanceToolCallPlan(plan, { type: 'CONFIRM' }).phase, 'EXECUTE')
  assert.equal(canExecuteToolCall(advanceToolCallPlan(plan, { type: 'CONFIRM' })), true)
})

test('propagates trace and evidence through verification', () => {
  let plan = createToolCallPlan({ task: '诊断 Service', tool: { id: 'k8s-diagnose', readOnly: true }, traceId: 'trace-1' })
  plan = advanceToolCallPlan(plan)
  plan = advanceToolCallPlan(plan)
  assert.equal(plan.phase, 'EXECUTE')
  plan = advanceToolCallPlan(plan, { traceId: 'trace-2', evidence: ['Endpoint 为空'] })
  assert.equal(plan.phase, 'VERIFY')
  plan = advanceToolCallPlan(plan, { ok: true, evidence: ['Endpoint 已恢复'] })
  assert.equal(plan.phase, 'COMPLETED')
  assert.deepEqual(plan.evidence, ['Endpoint 已恢复'])
})
