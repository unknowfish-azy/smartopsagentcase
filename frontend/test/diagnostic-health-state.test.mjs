import assert from 'node:assert/strict'
import test from 'node:test'
import { ref } from 'vue'
import * as stateModule from '../src/components/diagnostics/healthState.js'

import {
  FIVE_MINUTES_MS,
  healthStateLabel,
  isFreshCheck,
  normalizeDiagnosticFailure
} from '../src/components/diagnostics/healthState.js'

test('health checks are fresh for exactly five minutes and unknown timestamps are stale', () => {
  const now = Date.parse('2026-10-02T00:05:00.000Z')
  assert.equal(FIVE_MINUTES_MS, 300000)
  assert.equal(isFreshCheck('2026-10-02T00:00:00.000Z', now), true)
  assert.equal(isFreshCheck('2026-10-01T23:59:59.999Z', now), false)
  assert.equal(isFreshCheck(null, now), false)
})

test('stale healthy results are never labelled as current health', () => {
  assert.equal(healthStateLabel('HEALTHY', false), '\u6b63\u5e38')
  assert.equal(healthStateLabel('HEALTHY', true), '\u7ed3\u679c\u53ef\u80fd\u5df2\u8fc7\u671f')
  assert.equal(healthStateLabel('UNCONFIGURED', false), '\u672a\u914d\u7f6e')
})

test('diagnostic failures normalize to stable categories', () => {
  assert.equal(normalizeDiagnosticFailure(new Error('connect timeout')).category, 'TIMEOUT')
  assert.equal(normalizeDiagnosticFailure(new Error('TLS connection refused')).category, 'NETWORK')
  assert.equal(normalizeDiagnosticFailure(new Error('assertion mismatch')).category, 'ASSERTION')
  assert.equal(normalizeDiagnosticFailure({ response: { data: { errorCategory: 'TIMEOUT' } } }).category, 'TIMEOUT')
})

test('refresh failure preserves results as stale and successful retry resets freshness', async () => {
  assert.equal(typeof stateModule.createDiagnosticState, 'function')
  const now = ref(1000000)
  let fail = false
  const previous = { checks: [{ status: 'HEALTHY' }] }
  const state = stateModule.createDiagnosticState(async () => {
    if (fail) throw { status: 403 }
    return previous
  }, now)
  await state.load()
  assert.equal(state.stale.value, false)
  now.value += 300001
  assert.equal(state.stale.value, true)
  await state.load()
  assert.equal(state.stale.value, false)
  fail = true
  await state.load()
  assert.deepEqual(state.status.value, previous)
  assert.equal(state.stale.value, true)
  assert.ok(state.error.value)
  fail = false
  await state.load()
  assert.equal(state.stale.value, false)
  assert.equal(state.error.value, '')
})

test('structured HTTP and wrapped timeout errors have safe stable labels', () => {
  assert.equal(normalizeDiagnosticFailure({ status: 403 }).category, 'AUTHORIZATION')
  assert.equal(normalizeDiagnosticFailure({ originalError: { code: 'ECONNABORTED' } }).category, 'TIMEOUT')
  assert.equal(normalizeDiagnosticFailure({ message: 'secret.internal: token=hidden' }).message.includes('hidden'), false)
})
