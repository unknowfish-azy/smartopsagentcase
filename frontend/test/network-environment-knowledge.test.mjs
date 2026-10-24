import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { knowledgeEntries, searchKnowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'

test('network initialization knowledge and artifacts can be retrieved through the existing catalog', () => {
  for (const [query, id] of [['HostIdentity', 'linux.identity.model'], ['NetworkManager', 'linux.network.networkmanager'], ['Chrony', 'linux.time.chrony'], ['RB-LINUX-BOOTSTRAP-001', 'RB-LINUX-BOOTSTRAP-001'], ['INC-NET-007', 'INC-NET-007'], ['INC-CLONE-IDENTITY-001', 'INC-CLONE-IDENTITY-001']]) {
    assert.ok(searchKnowledgeEntries({ query }).some(entry => entry.id === id), `Missing ${id}`)
  }
})

test('draft training samples reference existing knowledge and preserve provenance', () => {
  const ids = new Set(knowledgeEntries.map(entry => entry.id))
  const rows = readFileSync(new URL('../../SmartOps-Dataset/Linux/network_environment_initialization.jsonl', import.meta.url), 'utf8').trim().split('\n').map(line => JSON.parse(line))
  assert.equal(rows.length, 6)
  for (const row of rows) {
    assert.equal(row.status, 'DRAFT')
    assert.equal(row.attachmentVerified, false)
    assert.ok(row.knowledgeIds.every(id => ids.has(id)))
    assert.ok(row.response.risk && row.response.verification)
  }
})

test('new pack preserves provenance, related nodes and safe mutation command metadata', () => {
  const entries = knowledgeEntries.filter(entry => entry.packId === 'linux-network-environment')
  assert.ok(entries.length > 30)
  const ids = new Set(knowledgeEntries.map(entry => entry.id))
  assert.equal(ids.size, knowledgeEntries.length)
  for (const entry of entries) {
    assert.equal(entry.provenance.attachmentVerified, false)
    assert.ok(entry.source && entry.section && entry.content && entry.tags.length)
    for (const id of entry.relatedIds || []) assert.ok(ids.has(id), `Unknown relation ${id}`)
    for (const command of entry.commands || []) {
      assert.equal(command.executionAllowed, false)
      assert.ok(command.verification && command.risk_level)
      if (!command.read_only) assert.ok(command.requires_preview && command.approval_required)
    }
  }
  const nmcli = entries.find(entry => entry.id === 'linux.network.nmcli.change')
  assert.ok(nmcli.commands.filter(command => !command.read_only).every(command => command.remoteRisk === 'HIGH'))
  assert.equal(entries.filter(entry => entry.id === 'linux.time.chrony').length, 1)
})
