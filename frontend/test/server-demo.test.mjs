import test from 'node:test'
import assert from 'node:assert/strict'
import { demoServers, isDemoServer, serverRowsForMode, findDemoServer } from '../src/views/server/serverDemo.js'

test('six explicitly fictional immutable servers cover online, warning and offline cases', () => {
  assert.equal(demoServers.length, 6)
  assert.equal(new Set(demoServers.map(server => server.id)).size, 6)
  assert.deepEqual([...new Set(demoServers.map(server => server.status))].sort(), ['OFFLINE', 'ONLINE', 'WARNING'])
  for (const server of demoServers) {
    assert.ok(server.id.startsWith('demo:'))
    assert.equal(server.demo, true)
    assert.ok(Object.isFrozen(server))
    assert.ok(Object.isFrozen(server.metrics))
    assert.ok(!('password' in server))
  }
  assert.equal(demoServers.find(server => server.status === 'OFFLINE').metrics.cpu, null)
})

test('real and demo data never merge or mutate the real store', () => {
  const real = [{ id: 7, name: 'real-node' }]
  assert.equal(serverRowsForMode('real', real), real)
  assert.equal(serverRowsForMode('demo', real), demoServers)
  assert.equal(serverRowsForMode('unexpected', real), real)
  assert.deepEqual(real, [{ id: 7, name: 'real-node' }])
})

test('fake identities are recognizable even without the demo marker and cannot become real detail IDs', () => {
  assert.equal(isDemoServer({ id: 'demo:unknown' }), true)
  assert.equal(isDemoServer({ id: 7, demo: true }), true)
  assert.equal(isDemoServer({ id: 7 }), false)
  assert.equal(findDemoServer('demo:unknown'), null)
  assert.equal(findDemoServer(demoServers[0].id), demoServers[0])
})
