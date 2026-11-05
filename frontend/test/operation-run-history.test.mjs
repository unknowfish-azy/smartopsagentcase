import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { findRunHistoryGuide, runPageWithGuides } from '../src/components/operations/runHistoryGuides.js'
import {
  cleanRunQuery,
  candidateStatusLabel,
  formatDuration,
  outputState,
  runStatusLabel,
  visibleOutput,
  normalizeDateTime,
  validateRunTimeRange
} from '../src/components/operations/operationRunHistory.js'

test('maps persisted run statuses to clear Chinese labels', () => {
  assert.equal(runStatusLabel('SUCCESS'), '执行成功')
  assert.equal(runStatusLabel('FAILED'), '执行失败')
  assert.equal(runStatusLabel('RUNNING'), '执行中')
  assert.equal(runStatusLabel('CUSTOM'), 'CUSTOM')
})

test('formats duration and command output without inventing content', () => {
  assert.equal(formatDuration('2026-09-27T00:00:00Z', '2026-09-27T00:00:01.250Z'), '1.25 秒')
  assert.equal(formatDuration('2026-09-27T00:00:00Z', null), '执行中')
  assert.equal(visibleOutput(''), '')
  assert.equal(visibleOutput(null), '')
  assert.equal(outputState(0), 'success')
  assert.equal(outputState(2), 'failed')
  assert.equal(outputState(null), 'unknown')
})

test('normalizes valid local dates and rejects incomplete dates', () => {
  assert.equal(normalizeDateTime('2026-10-17T15:30'), new Date('2026-10-17T15:30').toISOString())
  assert.equal(normalizeDateTime('2026-10-17T15'), '')
  assert.deepEqual(validateRunTimeRange('2026-10-17T16:00', '2026-10-17T15:00'), {
    startedFrom: '结束时间必须晚于开始时间。'
  })
  assert.deepEqual(validateRunTimeRange('', ''), {})
})

test('cleans empty filters and normalizes paging', () => {
  assert.deepEqual(cleanRunQuery({ traceId: '  abc ', toolId: '', status: null, page: 0, pageSize: 500 }), {
    traceId: 'abc', page: 1, pageSize: 100
  })
})

test('labels generated knowledge candidates as pending human review', () => {
  assert.equal(candidateStatusLabel('PENDING_REVIEW'), '待人工审核')
  assert.equal(candidateStatusLabel('CUSTOM'), 'CUSTOM')
})

async function readRunHistorySources() {
  const files = [
    '../src/views/operations/RunHistoryView.vue',
    '../src/components/operations/RunHistoryDetailPanel.vue',
    '../src/composables/useRunHistory.js'
  ]
  const chunks = await Promise.all(files.map(file => readFile(new URL(file, import.meta.url), 'utf8')))
  return chunks.join('\n')
}

test('run detail exposes a reviewed knowledge candidate action without direct publishing', async () => {
  const source = await readRunHistorySources()
  assert.match(source, /沉淀为知识候选/)
  assert.match(source, /createKnowledgeCandidateFromRun/)
  assert.doesNotMatch(source, /直接发布|publishKnowledge/)
})

test('empty unfiltered run history shows read-only examples without affecting totals', () => {
  const guided = runPageWithGuides({ items: [], total: 0, page: 1, pageSize: 20 }, { page: 1 })
  assert.equal(guided.guideMode, true)
  assert.equal(guided.total, 4)
  assert.equal(guided.items.length, 4)
  for (const item of guided.items) {
    assert.equal(item.isGuide, true)
    const detail = findRunHistoryGuide(item.id)
    assert.equal(detail.run.id, item.id)
    assert.ok(detail.outputs.length > 0)
    assert.ok(detail.evidence.length > 0)
  }
})

test('real runs and active filters never mix with examples', () => {
  const real = { id: 7, traceId: 'real-trace' }
  assert.deepEqual(runPageWithGuides({ items: [real], total: 1 }, {}).items, [real])
  assert.equal(runPageWithGuides({ items: [], total: 0 }, { status: 'FAILED' }).items.length, 0)
  assert.equal(runPageWithGuides({ items: [], total: 0 }, { page: 2 }).items.length, 0)
  assert.equal(findRunHistoryGuide(7), null)
})

test('run examples cannot create knowledge candidates', async () => {
  const source = await readRunHistorySources()
  assert.match(source, /v-if="!detail\.run\.isGuide"/)
  assert.match(source, /detail\.value\.run\.isGuide/)
  assert.match(source, /findRunHistoryGuide\(id\)/)
})
