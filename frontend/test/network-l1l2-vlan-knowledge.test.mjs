import test from 'node:test'
import assert from 'node:assert/strict'
import {
  networkL1L2VlanEntries,
  networkL1L2VlanIncidents,
  networkL1L2VlanRunbooks,
  networkL1L2VlanQuestions,
  networkL1L2VlanWrongAnswers,
  networkL1L2VlanRules,
  networkDigitalTwinSchema
} from '../src/views/knowledge/knowledgeCatalog.js'

test('indexes physical, switching, VLAN and trunk knowledge by operational symptom', () => {
  for (const [query, id] of [
    ['Link UP', 'network.physical.link_state'],
    ['MAC Flapping', 'network.l2.mac_flapping'],
    ['802.1Q', 'network.vlan.8021q'],
    ['Allowed VLAN', 'network.trunk.allowed_vlans'],
    ['Inter-VLAN Routing', 'network.l3.inter_vlan_routing']
  ]) {
    assert.ok(networkL1L2VlanEntries.some(entry => entry.id === id && `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase())), id)
  }
})

test('network L1/L2 pack preserves graph relations and read-only boundaries', () => {
  assert.ok(networkL1L2VlanEntries.length >= 35)
  const ids = new Set(networkL1L2VlanEntries.map(entry => entry.id))
  assert.equal(ids.size, networkL1L2VlanEntries.length)
  for (const entry of networkL1L2VlanEntries) {
    assert.equal(entry.packId, 'network-l1l2-vlan')
    assert.equal(entry.executionAllowed, false)
    assert.ok(entry.provenance && entry.provenance.attachmentVerified === false)
    assert.ok(entry.relatedIds.every(id => ids.has(id) || id.startsWith('network.')))
    for (const command of entry.commands || []) {
      assert.equal(command.executionAllowed, false)
      assert.ok(command.risk_level && command.verification)
      if (!command.read_only) assert.ok(command.requires_preview && command.approval_required)
    }
  }
})

test('pack models incidents, runbooks, wrong answers and deterministic decision rules', () => {
  assert.ok(networkL1L2VlanIncidents.some(item => item.id === 'INC-L2-002' && item.tags.includes('MAC_FLAPPING')))
  assert.ok(networkL1L2VlanIncidents.some(item => item.id === 'INC-TRUNK-003'))
  assert.ok(networkL1L2VlanRunbooks.some(item => item.id === 'RB-L2-TRUNK-001' && item.steps.includes('verify allowed VLANs')))
  assert.ok(networkL1L2VlanWrongAnswers.some(item => item.wrong_reason_type === 'VLAN_SECURITY_OVERSIMPLIFICATION'))
  assert.ok(networkL1L2VlanQuestions.some(item => item.category === 'VLAN_ANALYSIS'))
  assert.ok(networkL1L2VlanRules.some(item => item.id === 'RULE-NET-LAYER-PROBE' && item.sequence[0] === 'identify symptom layer'))
})

test('digital twin schema links devices, interfaces, links, VLANs and observations', () => {
  assert.deepEqual(Object.keys(networkDigitalTwinSchema), ['NetworkNode', 'NetworkLink', 'MacObservation', 'SwitchBaseline'])
  assert.ok(networkDigitalTwinSchema.NetworkLink.fields.includes('allowedVlans'))
  assert.ok(networkDigitalTwinSchema.MacObservation.fields.includes('movement_count'))
})
