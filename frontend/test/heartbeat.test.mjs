import test from 'node:test'
import assert from 'node:assert/strict'
import { heartbeatCells } from '../src/views/sentinel/heartbeat.js'
test('missing samples never imply healthy history', () => {
  assert.equal(heartbeatCells(null).length, 30)
  assert.ok(heartbeatCells([]).every(cell => cell.status === 'unknown'))
})
test('history keeps latest thirty samples and preserves unknown states', () => {
  const samples = Array.from({length:40}, (_, i) => ({status:'up', timestamp:String(i)}))
  samples[39].status = 'unexpected'
  const cells = heartbeatCells(samples)
  assert.equal(cells[0].label, '10 · 正常')
  assert.equal(cells[29].status, 'unknown')
})
