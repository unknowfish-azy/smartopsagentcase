import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { layoutRelationGraph, radarGraph, researchGraph, shortNodeLabel } from './relationGraph.js'

describe('relationGraph', () => {
  it('creates deterministic coordinates and connects only existing nodes', () => {
    const nodes = [{ id: 'root', label: 'root' }, { id: 'a', label: 'A' }, { id: 'b', label: 'B' }]
    const first = layoutRelationGraph(nodes, [{ from: 'root', to: 'a' }, { from: 'missing', to: 'b' }])
    const second = layoutRelationGraph(nodes, [{ from: 'root', to: 'a' }, { from: 'missing', to: 'b' }])

    assert.deepEqual(first, second)
    assert.equal(first.edges.length, 2)
    assert.equal(first.nodes[0].x, 380)
    assert.equal(first.nodes[0].y, 160)
    assert.equal(first.nodes.every(node => Number.isFinite(node.x) && Number.isFinite(node.y)), true)
  })

  it('returns an empty layout without inventing demo nodes', () => {
    assert.deepEqual(layoutRelationGraph([], []).nodes, [])
    assert.equal(researchGraph('', [], null).nodes.length, 1)
  })

  it('maps local runtime and real search evidence into the graph', () => {
    const graph = researchGraph('kubernetes', [{ id: 'web-1', title: 'Guide', site: 'example.com', kind: 'WEB' }], { available: true, model: 'qwen3:1.7b' })
    assert.deepEqual(graph.nodes.map(node => node.id), ['query', 'runtime', 'web-1'])
    assert.equal(graph.edges.length, 2)
  })

  it('marks changed radar sources without changing the source data', () => {
    const source = { id: 7, name: 'Docs', monitorEnabled: true, monitorIntervalMinutes: 60, pages: [{ changeType: 'UPDATED' }] }
    const graph = radarGraph([source])
    assert.equal(graph.nodes[1].status, 'changed')
    assert.equal(graph.edges[0].kind, 'changed')
    assert.equal(source.pages.length, 1)
  })

  it('bounds long labels', () => {
    assert.equal(shortNodeLabel('a'.repeat(40)).length <= 18, true)
  })
})
