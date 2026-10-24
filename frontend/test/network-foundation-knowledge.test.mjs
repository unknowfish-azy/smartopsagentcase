import test from 'node:test'
import assert from 'node:assert/strict'
import { knowledgeEntries, searchKnowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'

test('network foundations are searchable and linked to operational knowledge', () => {
  for (const [query, id] of [['CIDR', 'network.ipv4.subnet'], ['ARP', 'network.arp.next_hop'], ['TIME-WAIT', 'network.tcp.state'], ['Next Best Evidence', 'network.reasoning.next_evidence'], ['INC-NET-SUBNET', 'INC-NET-SUBNET']]) {
    assert.ok(searchKnowledgeEntries({ query }).some(entry => entry.id === id), id)
  }
})

test('foundation pack keeps provenance, historical labeling and resolvable references', () => {
  const entries = knowledgeEntries.filter(entry => entry.packId === 'network-foundation')
  assert.ok(entries.length >= 40)
  const ids = new Set(knowledgeEntries.map(entry => entry.id))
  assert.equal(ids.size, knowledgeEntries.length)
  for (const entry of entries) {
    assert.equal(entry.executionAllowed, false)
    assert.equal(entry.provenance.attachmentVerified, false)
    assert.ok(entry.source && entry.section && entry.tags.length)
    assert.ok(entry.relatedIds.every(id => ids.has(id)), entry.id)
  }
  assert.equal(entries.find(entry => entry.id === 'network.ipv4.classful').knowledge_type, 'historical_fundamentals')
  const subnet = entries.find(entry => entry.id === 'network.ipv4.subnet')
  assert.equal(subnet.examples.find(example => example.address === '192.168.10.64/26').broadcast, '192.168.10.127')
  assert.ok(subnet.content.includes('/31') && subnet.content.includes('/32'))
})
