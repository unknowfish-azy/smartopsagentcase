import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DENSITY,
  LANE_GAP_X,
  LANE_PAD_X,
  LANE_WIDTH,
  ROW_HEIGHT,
  buildReviewGraph,
  laneCenter,
  laneSegments,
  rejectReasonOf,
  sortCandidates
} from '../src/views/knowledge/reviewGraph/useReviewGraph.js'

const entries = [
  {
    id: 11,
    libraryId: 1,
    title: 'K8s Service 排障',
    version: 1,
    verificationStatus: 'UNVERIFIED',
    sourceRef: 'trace-a',
    createdAt: '2026-03-02T02:00:00Z'
  },
  {
    id: 12,
    libraryId: 1,
    title: 'MySQL 连接池',
    version: 1,
    verificationStatus: 'UNVERIFIED',
    sourceRef: null,
    createdAt: '2026-03-01T02:00:00Z'
  }
]

const candidates = [
  {
    id: 101,
    traceId: 'trace-a',
    toolId: 'k8s.service.diagnose',
    title: 'Service 无可用 Endpoint',
    status: 'PROMOTED',
    createdAt: '2026-03-01T09:00:00Z',
    summary: '已采纳'
  },
  {
    id: 102,
    traceId: 'trace-b',
    toolId: 'mysql.connection.diagnose',
    title: '连接池耗尽',
    status: 'PENDING_REVIEW',
    createdAt: '2026-03-03T09:00:00Z',
    summary: '待审'
  },
  {
    id: 103,
    traceId: 'trace-c',
    toolId: 'k8s.service.diagnose',
    title: 'Endpoint 抖动',
    status: 'REJECTED',
    createdAt: '2026-03-04T09:00:00Z',
    summary: '原结论\n驳回原因：证据不足（缺上游日志）'
  }
]

test('promoted candidate is attached to its entry lane through source_ref', () => {
  const graph = buildReviewGraph({ candidates, entries })

  const promoted = graph.nowRows.find(row => row.id === 'candidate-101')
  assert.ok(promoted, 'promoted candidate row exists')
  assert.equal(promoted.entry.id, 11)
  assert.equal(promoted.lane, 0)
  assert.equal(graph.lanes[0].kind, 'entry')
  assert.equal(graph.lanes[0].name, 'K8s Service 排障')
})

test('candidates without an entry fall back to the last unassigned lane', () => {
  const graph = buildReviewGraph({ candidates, entries })
  const last = graph.lanes[graph.lanes.length - 1]

  assert.equal(last.kind, 'unassigned')
  assert.equal(last.name, '待归类')
  assert.equal(graph.nowRows.find(row => row.id === 'candidate-102').lane, last.index)
  assert.equal(graph.nowRows.find(row => row.id === 'candidate-103').lane, last.index)
  assert.equal(graph.stats.pending, 1)
  assert.equal(graph.stats.promoted, 1)
  assert.equal(graph.stats.rejected, 1)
  assert.equal(graph.stats.entryLanes, 1)
  assert.equal(graph.stats.unassigned, 2)
})

test('rows are continuous: every y equals previous y plus previous height', () => {
  const graph = buildReviewGraph({ candidates, entries })

  let cursor = 0
  for (const row of graph.nowRows) {
    assert.equal(row.y, cursor, `row ${row.id} starts where the previous one ended`)
    cursor += row.h
  }
  assert.equal(graph.nowHeight, cursor)

  let historyCursor = 0
  for (const row of graph.histRows) {
    assert.equal(row.y, historyCursor)
    historyCursor += row.h
  }
  assert.equal(graph.histHeight, historyCursor)
})

test('rows use the fixed row heights and same-lane rows share one x coordinate', () => {
  const graph = buildReviewGraph({ candidates, entries })
  const entryRow = graph.nowRows.find(row => row.id === 'entry-11')
  const candidateRow = graph.nowRows.find(row => row.id === 'candidate-101')
  const gap = graph.nowRows.find(row => row.kind === 'gap')

  assert.equal(entryRow.h, ROW_HEIGHT.entry)
  assert.equal(candidateRow.h, ROW_HEIGHT.cand)
  assert.equal(gap.h, ROW_HEIGHT.gap)
  assert.equal(laneCenter(entryRow.lane), laneCenter(candidateRow.lane))
  assert.equal(graph.padLeft, LANE_PAD_X + graph.lanes.length * LANE_WIDTH + LANE_GAP_X)
})

test('pending rows sort before promoted and rejected rows inside one lane', () => {
  const sorted = sortCandidates(candidates).map(candidate => candidate.id)
  assert.deepEqual(sorted, [102, 101, 103])
})

test('history keeps only review events, newest first', () => {
  const graph = buildReviewGraph({ candidates, entries })

  assert.deepEqual(graph.histRows.map(row => row.event.id), ['event-103', 'event-101'])
  assert.equal(graph.histRows[0].event.kind, 'reject')
  assert.equal(graph.histRows[1].event.kind, 'adopt')
  assert.equal(graph.histRows[1].event.entry.id, 11)
})

test('rejection reason is read from the summary tail appended by the backend', () => {
  assert.equal(rejectReasonOf(candidates[2].summary), '证据不足（缺上游日志）')
  assert.equal(rejectReasonOf('没有原因'), '')
})

test('no verified trunk lane is drawn because no backend endpoint sets VERIFIED', () => {
  const graph = buildReviewGraph({ candidates, entries })
  assert.equal(graph.lanes.some(lane => lane.kind === 'trunk'), false)
})

test('an empty workspace yields no rows instead of placeholder state', () => {
  const graph = buildReviewGraph({ candidates: [], entries: [] })
  assert.deepEqual(graph.nowRows, [])
  assert.deepEqual(graph.histRows, [])
  assert.equal(graph.nowHeight, 0)
  assert.equal(graph.stats.total, 0)
})

test('compact density shrinks every row and the avatar, without changing lane geometry', () => {
  const comfortable = buildReviewGraph({ candidates, entries })
  const compact = buildReviewGraph({ candidates, entries, density: 'compact' })

  const compactCand = compact.nowRows.find(row => row.kind === 'cand')
  assert.equal(compactCand.h, DENSITY.compact.cand)
  assert.equal(compact.avatarSize, DENSITY.compact.avatar)
  assert.equal(comfortable.avatarSize, DENSITY.comfortable.avatar)
  assert.ok(compact.nowHeight < comfortable.nowHeight)
  assert.equal(compact.padLeft, comfortable.padLeft)
  assert.equal(laneCenter(compactCand.lane), laneCenter(comfortable.nowRows.find(row => row.kind === 'cand').lane))
})

test('lane line is dashed through pending rows and solid once a decision exists', () => {
  const graph = buildReviewGraph({ candidates, entries })
  const promotedLane = graph.lanes[0].index
  const unassignedLane = graph.lanes[graph.lanes.length - 1].index

  // 该泳道只有已采纳事件：整段实线。
  const decided = laneSegments(graph.nowRows, promotedLane)
  assert.equal(decided.length, 1)
  assert.equal(decided[0].dashed, false)

  // 待归类泳道：待审 → 已驳回，前段虚线、后段实线，且两段共用分界点。
  const mixed = laneSegments(graph.nowRows, unassignedLane)
  assert.equal(mixed.length, 2)
  assert.equal(mixed[0].dashed, true)
  assert.equal(mixed[1].dashed, false)
  assert.equal(mixed[0].bottom, mixed[1].top)

  // 演化史没有待审行，全是实线。
  assert.equal(laneSegments(graph.histRows, unassignedLane).every(segment => !segment.dashed), true)
})
