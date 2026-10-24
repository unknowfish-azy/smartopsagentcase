import { getKnowledgeNode, getKnowledgePath, getKnowledgeTree, knowledgeEntries, searchKnowledgeEntries } from './knowledgeCatalog.js'

export function knowledgeEntryView(entryId, entries = knowledgeEntries) {
  const currentIndex = entries.findIndex(entry => entry.id === entryId)
  if (currentIndex < 0) return null

  return {
    current: entries[currentIndex],
    previous: entries[currentIndex - 1] || null,
    next: entries[currentIndex + 1] || null
  }
}

// Read-only boundary for the agent: it can navigate and retrieve knowledge, but cannot mutate the catalog.
export const knowledgeReadApi = Object.freeze({
  tree: () => getKnowledgeTree(),
  node: nodeId => getKnowledgeNode(nodeId),
  path: nodeId => getKnowledgePath(nodeId),
  search: filters => searchKnowledgeEntries(filters)
})
