export function addEvidencePage(pages, selectedTaskIds, page) {
  if (!page?.taskId) return { pages, selectedTaskIds }
  const nextPages = [...pages.filter(item => item.taskId !== page.taskId), page].slice(-4)
  const available = new Set(nextPages.map(item => item.taskId))
  const retained = selectedTaskIds.filter(id => available.has(id) && id !== page.taskId)
  return { pages: nextPages, selectedTaskIds: [...retained, page.taskId].slice(-4) }
}

export function toggleEvidenceTask(pages, selectedTaskIds, taskId) {
  if (selectedTaskIds.includes(taskId)) return selectedTaskIds.filter(id => id !== taskId)
  if (selectedTaskIds.length >= 4 || !pages.some(page => page.taskId === taskId)) return selectedTaskIds
  return [...selectedTaskIds, taskId]
}
