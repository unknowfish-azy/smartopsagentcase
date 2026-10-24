import assert from 'node:assert/strict'
import { test } from 'node:test'
import { tunnelStatusLabel, tunnelTypeLabel, canStartTunnel } from '../src/components/operations/tunnelWorkspace.js'

test('maps tunnel states to explicit operational labels', () => {
  assert.equal(tunnelStatusLabel('RUNNING'), 'RUNNING')
  assert.equal(tunnelStatusLabel('STOPPED'), 'STOPPED')
  assert.equal(tunnelStatusLabel('ERROR'), 'ERROR')
})

test('maps forwarding types without hiding the network direction', () => {
  assert.equal(tunnelTypeLabel('LOCAL'), 'LOCAL FORWARD')
  assert.equal(tunnelTypeLabel('REMOTE'), 'REMOTE FORWARD')
  assert.equal(tunnelTypeLabel('DYNAMIC'), 'SOCKS / DYNAMIC')
})

test('only an online SSH runtime can start a tunnel', () => {
  assert.equal(canStartTunnel({ runtimeOnline: true, protocol: 'SSH', status: 'STOPPED' }), true)
  assert.equal(canStartTunnel({ runtimeOnline: false, protocol: 'SSH', status: 'STOPPED' }), false)
  assert.equal(canStartTunnel({ runtimeOnline: true, protocol: 'RDP', status: 'STOPPED' }), false)
  assert.equal(canStartTunnel({ runtimeOnline: true, protocol: 'SSH', status: 'RUNNING' }), false)
})
