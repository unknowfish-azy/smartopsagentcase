import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  formatBytes,
  formatRate,
  memPercentOf,
  netRate,
  pushHistory
} from '../src/components/operations/serverMonitor.js'

function sample(overrides = {}) {
  return {
    supported: true,
    cpuPercent: 42.5,
    memTotalKb: 1000000,
    memAvailableKb: 400000,
    netRxBytes: 1000,
    netTxBytes: 2000,
    sampledAt: '2026-11-16T08:00:00Z',
    ...overrides
  }
}

test('pushHistory caps at 60 and skips samples without cpu/mem', () => {
  let history = []
  for (let index = 0; index < 65; index += 1) {
    history = pushHistory(history, sample({ cpuPercent: index, sampledAt: `2026-11-16T08:00:${String(index % 60).padStart(2, '0')}Z` }))
  }
  assert.equal(history.length, 60)
  assert.equal(history[0].cpu, 5)
  assert.equal(history[59].cpu, 64)

  assert.equal(pushHistory(history, sample({ cpuPercent: null, memTotalKb: null, memAvailableKb: null })).length, 60)
})

test('memPercentOf derives used percent from total/available', () => {
  assert.equal(memPercentOf(sample()), 60)
  assert.equal(memPercentOf(sample({ memTotalKb: 0 })), null)
  assert.equal(memPercentOf(sample({ memAvailableKb: null })), null)
})

test('netRate diffs consecutive samples over real elapsed time', () => {
  const rate = netRate(
    sample({ sampledAt: '2026-11-16T08:00:00Z' }),
    sample({ netRxBytes: 7000, netTxBytes: 4000, sampledAt: '2026-11-16T08:00:03Z' })
  )
  assert.equal(rate.rxPerSec, 2000)
  assert.equal(rate.txPerSec, 666.6666666666666)

  assert.equal(netRate(null, sample()), null)
  assert.equal(netRate(sample(), sample({ netRxBytes: null, netTxBytes: null })), null)
  assert.equal(netRate(sample(), sample({ sampledAt: 'bad-time' })), null)
})

test('formatBytes and formatRate never invent values', () => {
  assert.equal(formatBytes(500), '500 B')
  assert.equal(formatBytes(2048), '2.0 KB')
  assert.equal(formatBytes(1536 * 1024), '1.5 MB')
  assert.equal(formatBytes(NaN), '—')
  assert.equal(formatRate(2048), '2.0 KB/s')
  assert.equal(formatRate(undefined), '—')
})
