import test from 'node:test'
import assert from 'node:assert/strict'
import { canConnect, capabilityLabel } from '../src/api/operationsState.ts'

test('deferred protocols remain non-connectable from session tree data', () => {
  assert.equal(canConnect({ protocol: 'RDP', status: 'REQUIRES_NATIVE_BRIDGE' }), false)
  assert.equal(capabilityLabel({ protocol: 'RDP', status: 'REQUIRES_NATIVE_BRIDGE' }), 'REQUIRES NATIVE BRIDGE')
})
