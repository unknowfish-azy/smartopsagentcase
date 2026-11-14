import assert from 'node:assert/strict'
import test from 'node:test'
import { knowledgeDomains, knowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { computeField, FIELD } from '../src/views/knowledge/space/useFieldLayout.js'

const NOW_MS = Date.parse('2026-11-14T00:00:00Z')

// ── 真实数据冒烟 ────────────────────────────────────────────

test('真实数据 10 域知识条目，三层 y 全部在合法区间', () => {
  const field = computeField(knowledgeEntries, knowledgeDomains, [], { now: NOW_MS })

  assert.ok(field.stats.atoms > 0, '知识原子数应大于 0')
  assert.equal(field.stats.insights, 0)

  for (const p of field.planes) {
    if (p.kind === 'knowledge') {
      assert.ok(p.y >= FIELD.knowledge.y0 && p.y < FIELD.knowledge.y0 + 1000,
        `知识平面 ${p.id} y=${p.y} 超出知识层范围 [${FIELD.knowledge.y0}, ...)`)
    }
    if (p.kind === 'insight') {
      assert.ok(p.y >= FIELD.insight.y0 && p.y < FIELD.insight.y0 + 200,
        `洞察平面 ${p.id} y=${p.y} 超出洞察层范围`)
    }
  }
})

// ── 确定性 ─────────────────────────────────────────────────

test('同输入两次调用结果完全一致（deepEqual）', () => {
  const threads = [
    { insightId: 'insight.x', atomId: 'atom.a', relation: 'derived', weight: 0.8, stale: false },
  ]
  const insights = [{ id: 'insight.x', badge: 'SERVERS', title: '服务器状态' }]
  const atoms = [
    { id: 'atom.a', domain: 'linux', platform: 'Linux', service: 'shell', type: 'ENGINEERING KNOWLEDGE',
      title: 'T', summary: 'S', source: 's', version: '1.0', tags: ['shell'] },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]

  const a = computeField(atoms, domains, insights, { now: NOW_MS, threads })
  const b = computeField(atoms, domains, insights, { now: NOW_MS, threads })
  assert.deepEqual(a, b, '两次 computeField 输出不相等——坐标不稳定')
})

// ── 三层 y 不越界 ─────────────────────────────────────────

test('三层 y 坐标严格在 FIELD 定义范围内', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 's1', type: 'RUNBOOK',
      title: 'T1', summary: 'S', source: 's', version: '1.0', tags: [] },
    { id: 'a2', domain: 'linux', platform: 'Linux', service: 's2', type: 'ENGINEERING KNOWLEDGE',
      title: 'T2', summary: 'S', source: 's', version: '1.0', tags: [] },
  ]
  const insights = [
    { id: 'i1', badge: 'ALERTS', title: '告警分布' },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]

  const field = computeField(atoms, domains, insights, { now: NOW_MS })

  const kPlanes = field.planes.filter(p => p.kind === 'knowledge')
  const iPlanes = field.planes.filter(p => p.kind === 'insight')
  assert.ok(kPlanes.length >= 2, '知识平面数应 >= 2')
  assert.ok(iPlanes.length >= 1, '洞察平面数应 >= 1')

  for (const p of kPlanes) {
    assert.ok(p.y >= FIELD.knowledge.y0, `知识平面 y=${p.y} < knowledge.y0=${FIELD.knowledge.y0}`)
    assert.ok(p.y <= FIELD.knowledge.y1, `知识平面 y=${p.y} > knowledge.y1=${FIELD.knowledge.y1}`)
    assert.ok(p.z >= FIELD.zHistoryMin, `z=${p.z} < zHistoryMin=${FIELD.zHistoryMin}`)
    assert.ok(p.z <= FIELD.zFutureMax, `z=${p.z} > zFutureMax=${FIELD.zFutureMax}`)
  }
  for (const p of iPlanes) {
    assert.ok(p.y >= FIELD.insight.y0, `洞察平面 y=${p.y} < insight.y0=${FIELD.insight.y0}`)
    assert.ok(p.y <= FIELD.insight.y1 + FIELD.insightLift,
      `洞察平面 y=${p.y} 超出 insight 层可浮动范围`)
  }
})

// ── evidenceRefs 规则 ───────────────────────────────────────

test('无 evidenceRefs 的原子不产生 evidenceBands', () => {
  // atoms 里没有任何 evidenceRefs
  const atoms = [
    { id: 'no-ev-1', domain: 'linux', platform: 'Linux', service: 's', type: 'ENGINEERING',
      title: 'T', summary: 'S', source: 's', version: '1.0', tags: [] },
    { id: 'no-ev-2', domain: 'linux', platform: 'Linux', service: 's2', type: 'RUNBOOK',
      title: 'T2', summary: 'S', source: 's', version: '1.0', tags: [] },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]
  const field = computeField(atoms, domains, [], { now: NOW_MS })
  assert.equal(field.evidenceBands.length, 0,
    `无 evidenceRefs 的原子不应产生 evidenceBands，实际 ${field.evidenceBands.length}`)
})

test('有 evidenceRefs 的原子产生对应 evidenceBands', () => {
  const atoms = [
    { id: 'with-ev', domain: 'linux', platform: 'Linux', service: 's', type: 'ENGINEERING',
      title: 'T', summary: 'S', source: 's', version: '1.0', tags: [],
      evidenceRefs: [
        { evidenceId: 'e1', chunkId: 'c1', source: 'runbook.md', version: '1.0', capturedAt: '2025-01-01T00:00:00Z' },
      ],
    },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]
  const field = computeField(atoms, domains, [], { now: NOW_MS })
  assert.equal(field.evidenceBands.length, 1, `应有 1 条 evidenceBand，实际 ${field.evidenceBands.length}`)
  assert.ok(field.evidenceBands[0].y >= FIELD.evidence.y0,
    `evidenceBand.y=${field.evidenceBands[0].y} 应在 evidence 层`)
})

// ── threads 长度与传入一致 ────────────────────────────────────

test('threads.length === 传入 threads.length（两端都能在平面中找到）', () => {
  const atoms = [
    { id: 'atom.a', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'Nginx 502 Runbook', summary: 'S', source: 'nginx.md', version: '1.24+', tags: ['502', 'nginx'] },
    { id: 'atom.b', domain: 'linux', platform: 'Linux', service: 'docker', type: 'ENGINEERING',
      title: 'Docker 网络', summary: 'S', source: 'docker.md', version: '25', tags: ['docker', 'network'] },
  ]
  const insights = [
    { id: 'insight.a', badge: 'ALERTS', title: 'Nginx 502 告警' },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]
  const threads = [
    { insightId: 'insight.a', atomId: 'atom.a', relation: 'derived', weight: 0.8, stale: false },
    { insightId: 'insight.a', atomId: 'atom.b', relation: 'derived', weight: 0.4, stale: false },
  ]
  const field = computeField(atoms, domains, insights, { now: NOW_MS, threads })
  assert.equal(field.threads.length, 2,
    `threads.length 应为 2（传入值），实际 ${field.threads.length}`)
})

// ── now 必须显式传入 ────────────────────────────────────────

test('不传 now 时抛 TypeError（强制显式时间）', () => {
  assert.throws(
    () => computeField([], [], []),
    /now must be explicitly provided/,
    '未传 now 时应抛 TypeError'
  )
})

// ── 空输入安全 ──────────────────────────────────────────────

test('空输入返回空结构', () => {
  const field = computeField([], [], [], { now: NOW_MS })
  assert.deepEqual(field.planes, [])
  assert.deepEqual(field.evidenceBands, [])
  assert.deepEqual(field.threads, [])
  assert.ok(field.axes.domains.length === 0)
  assert.equal(field.stats.atoms, 0)
  assert.equal(field.stats.insights, 0)
})

// ── insight.anchor 逻辑 ──────────────────────────────────────

test('insight 有绑定时取知识平面 x 均值；无绑定时用域锚点 x', () => {
  const atoms = [
    { id: 'a1', domain: 'linux', platform: 'Linux', service: 'nginx', type: 'RUNBOOK',
      title: 'T1', summary: 'S', source: 's', version: '1.0', tags: [] },
    { id: 'a2', domain: 'linux', platform: 'Linux', service: 'mysql', type: 'ENGINEERING',
      title: 'T2', summary: 'S', source: 's', version: '1.0', tags: [] },
  ]
  const domains = [{ id: 'linux', label: 'LINUX', detail: '' }]
  const insights = [
    { id: 'i-bound', badge: 'KNOWLEDGE', title: '绑定的洞察' },
    { id: 'i-op', badge: 'ALERTS', title: 'operational 洞察' },
  ]
  const threads = [
    { insightId: 'i-bound', atomId: 'a1', relation: 'derived', weight: 0.9, stale: false },
    { insightId: 'i-bound', atomId: 'a2', relation: 'derived', weight: 0.3, stale: false },
  ]

  const field = computeField(atoms, domains, insights, { now: NOW_MS, threads })
  const planes = new Map(field.planes.map(p => [p.id, p]))

  const bound = planes.get('ip-i-bound')
  const op    = planes.get('ip-i-op')
  assert.ok(bound && op, '两个洞察平面都应存在')

  // bound 洞察的 x 应 = a1、a2 两个知识平面 x 的均值
  const a1 = field.planes.find(p => p.atomId === 'a1')
  const a2 = field.planes.find(p => p.atomId === 'a2')
  const expectedX = Math.round((a1.x + a2.x) / 2)
  assert.equal(bound.x, expectedX,
    `绑定洞察 x=${bound.x} 应为知识原子 x 均值 ${expectedX}`)
})
