import test from 'node:test'
import assert from 'node:assert/strict'
import { teamToolGroups, teamWorkspaceState } from '../src/domain/team/teamCollaboration.js'

test('team collaboration groups only the server returned tools', () => {
  const tools = [
    { toolId: 'host-health', readOnly: true, riskLevel: 'LOW' },
    { toolId: 'alerts-suppress', readOnly: false, riskLevel: 'HIGH' }
  ]
  assert.deepEqual(teamToolGroups(tools).map(group => [group.id, group.items.map(item => item.toolId)]), [
    ['diagnostics', ['host-health']],
    ['operations', ['alerts-suppress']]
  ])
})

test('team collaboration resets agent and conversation when team changes', () => {
  const state = teamWorkspaceState()
  state.selectTeam(10)
  state.selectAgent(8)
  state.selectConversation('conversation-1')
  state.selectTeam(20)
  assert.equal(state.teamId, 20)
  assert.equal(state.agentId, null)
  assert.equal(state.conversationId, null)
})
