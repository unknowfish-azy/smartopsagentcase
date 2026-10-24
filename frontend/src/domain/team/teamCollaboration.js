export function teamToolGroups(tools = []) {
  const values = Array.isArray(tools) ? tools : []
  return [
    { id: 'diagnostics', label: '诊断工具', items: values.filter(tool => tool.readOnly) },
    { id: 'operations', label: '运维工具', items: values.filter(tool => !tool.readOnly) }
  ].filter(group => group.items.length)
}

export function teamWorkspaceState() {
  return {
    teamId: null,
    agentId: null,
    conversationId: null,
    selectTeam(teamId) {
      if (this.teamId === teamId) return
      this.teamId = teamId
      this.agentId = null
      this.conversationId = null
    },
    selectAgent(agentId) { this.agentId = agentId },
    selectConversation(conversationId) { this.conversationId = conversationId }
  }
}
