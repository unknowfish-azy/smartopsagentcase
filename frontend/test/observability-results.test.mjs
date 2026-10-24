import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizePrometheusResult } from '../src/components/operations/observabilityResults.js'

test('summarizes the latest real sample from each Prometheus series', () => {
  const response = { status: 'success', data: { resultType: 'matrix', result: [
    { metric: { job: 'windows', volume: 'C:' }, values: [[100, '12.1'], [115, '10.5']] },
    { metric: { job: 'windows', volume: 'D:' }, values: [[100, '20.25']] }
  ] } }
  assert.deepEqual(summarizePrometheusResult(response, 'GiB'), [
    { labels: 'job=windows, volume=C:', value: '10.5 GiB', timestamp: 115 },
    { labels: 'job=windows, volume=D:', value: '20.25 GiB', timestamp: 100 }
  ])
})

test('keeps empty or invalid upstream results empty instead of inventing samples', () => {
  assert.deepEqual(summarizePrometheusResult({ status: 'success', data: { result: [] } }), [])
  assert.deepEqual(summarizePrometheusResult({ status: 'success', data: { result: [{ metric: {}, values: [] }] } }), [])
  assert.deepEqual(summarizePrometheusResult(null), [])
})
