import test from 'node:test'
import assert from 'node:assert/strict'
import {
  networkRoutingEntries,
  networkRoutingIncidents,
  networkRoutingRunbooks,
  networkRoutingQuestions,
  networkRoutingWrongAnswers,
  networkRoutingRules,
  networkRoutingSchemas,
  resolveRoute,
  explainRoute
} from '../src/views/knowledge/knowledgeCatalog.js'

const routes = [
  { destination: '10.0.0.0/8', nextHop: '192.0.2.1', exitInterface: 'eth0', source: 'STATIC', administrativeDistance: 1, metric: 10 },
  { destination: '10.1.0.0/16', nextHop: '192.0.2.2', exitInterface: 'eth1', source: 'OSPF', administrativeDistance: 110, metric: 20 },
  { destination: '10.1.2.0/24', nextHop: '192.0.2.3', exitInterface: 'eth2', source: 'STATIC', administrativeDistance: 1, metric: 5 },
  { destination: '0.0.0.0/0', nextHop: '192.0.2.254', exitInterface: 'eth9', source: 'STATIC', administrativeDistance: 1, metric: 100 }
]

test('resolves the longest matching prefix before route preference', () => {
  const selected = resolveRoute('10.1.2.100', routes)
  assert.equal(selected.destination, '10.1.2.0/24')
  assert.equal(selected.nextHop, '192.0.2.3')
  assert.equal(resolveRoute('10.9.1.1', routes).destination, '10.0.0.0/8')
  assert.equal(resolveRoute('203.0.113.10', routes).destination, '0.0.0.0/0')
  assert.equal(resolveRoute('198.51.100.10', routes).source, 'STATIC')
})

test('explains route lookup matches and selected forwarding path', () => {
  const explanation = explainRoute('10.1.2.100', routes)
  assert.deepEqual(explanation.matchingRoutes.map(route => route.destination), ['10.1.2.0/24', '10.1.0.0/16', '10.0.0.0/8', '0.0.0.0/0'])
  assert.equal(explanation.selected.destination, '10.1.2.0/24')
  assert.equal(explanation.reason, 'longest_prefix_match')
  assert.equal(explanation.nextHop, '192.0.2.3')
  assert.equal(explanation.exitInterface, 'eth2')
})

test('indexes routing foundations, incidents and safe operational artifacts', () => {
  for (const [query, id] of [
    ['Connected Route', 'network.routing.connected'],
    ['Longest Prefix Match', 'network.routing.longest_prefix_match'],
    ['Return Path', 'network.routing.return_path'],
    ['show ip route', 'network.command.show_ip_route'],
    ['Route Explain', 'network.routing.route_explain']
  ]) assert.ok(networkRoutingEntries.some(entry => entry.id === id && `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase())), id)

  assert.ok(networkRoutingEntries.length >= 30)
  const ids = new Set(networkRoutingEntries.map(entry => entry.id))
  assert.equal(ids.size, networkRoutingEntries.length)
  for (const entry of networkRoutingEntries) {
    assert.equal(entry.packId, 'network-routing')
    assert.equal(entry.executionAllowed, false)
    assert.equal(entry.provenance.attachmentVerified, false)
    assert.ok(entry.relatedIds.every(id => ids.has(id) || id.startsWith('network.')))
    for (const command of entry.commands || []) {
      assert.equal(command.executionAllowed, false)
      assert.ok(command.risk_level && command.verification)
      if (!command.read_only) assert.ok(command.requires_preview && command.approval_required)
    }
  }
})

test('models return path, blackhole, loop, drift and decision safety', () => {
  for (const id of ['INC-L3-008', 'INC-L3-009', 'INC-L3-010', 'INC-L3-011', 'INC-L3-013']) assert.ok(networkRoutingIncidents.some(item => item.id === id), id)
  assert.ok(networkRoutingRunbooks.some(item => item.id === 'RB-L3-ROUTING-001' && item.steps.includes('verify return route')))
  assert.ok(networkRoutingRunbooks.some(item => item.id === 'RB-L3-ROUTE-002' && item.steps.includes('select best match')))
  assert.ok(networkRoutingQuestions.some(item => item.category === 'LONGEST_PREFIX'))
  assert.ok(networkRoutingWrongAnswers.some(item => item.wrong_reason_type === 'RETURN_PATH_ERROR'))
  assert.ok(networkRoutingRules.some(item => item.id === 'RULE-NET-ROUTE-DECISION' && item.sequence.includes('resolve next hop')))
  assert.deepEqual(Object.keys(networkRoutingSchemas), ['RouteEntry', 'RoutePath', 'RouteBaseline', 'TraceEvidence'])
})
