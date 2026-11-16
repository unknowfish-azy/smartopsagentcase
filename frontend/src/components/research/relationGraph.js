export function shortNodeLabel(value, max = 18) {
  const text = String(value || '').trim()
  if (!text) return '未命名节点'
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text
}

/** 以中心节点为原点生成确定性的椭圆拓扑，不引入随机布局或持续物理模拟。 */
export function layoutRelationGraph(nodes = [], edges = [], width = 760, height = 320) {
  const safeNodes = nodes.filter(node => node && node.id != null).slice(0, 10)
  if (!safeNodes.length) return { nodes: [], edges: [] }
  const centerId = safeNodes[0].id
  const positioned = safeNodes.map((node, index) => {
    if (index === 0) return { ...node, x: width / 2, y: height / 2 }
    const count = Math.max(1, safeNodes.length - 1)
    const angle = -Math.PI / 2 + ((index - 1) * Math.PI * 2) / count
    return {
      ...node,
      x: width / 2 + Math.cos(angle) * width * 0.37,
      y: height / 2 + Math.sin(angle) * height * 0.34,
    }
  })
  const byId = new Map(positioned.map(node => [node.id, node]))
  const positionedEdges = edges.map((edge, index) => {
    const from = byId.get(edge.from) || byId.get(centerId)
    const to = byId.get(edge.to)
    if (!from || !to || from.id === to.id) return null
    const bend = index % 2 === 0 ? -0.07 : 0.07
    const controlX = (from.x + to.x) / 2 + (to.y - from.y) * bend
    const controlY = (from.y + to.y) / 2 - (to.x - from.x) * bend
    return { ...edge, id: edge.id || `${from.id}-${to.id}-${index}`, from, to, controlX, controlY }
  }).filter(Boolean)
  return { nodes: positioned, edges: positionedEdges }
}

export function researchGraph(query, results = [], runtime = null) {
  const nodes = [{ id: 'query', label: query || '等待检索', type: 'QUERY', status: 'active' }]
  const edges = []
  if (runtime) {
    nodes.push({ id: 'runtime', label: runtime.model || 'Ollama', type: 'LOCAL MODEL', status: runtime.available ? 'ready' : 'offline' })
    edges.push({ from: 'runtime', to: 'query', kind: 'runtime' })
  }
  results.slice(0, 8).forEach(result => {
    nodes.push({ id: result.id, label: result.site || result.title, type: result.kind || 'WEB', status: 'ready', result })
    edges.push({ from: 'query', to: result.id, kind: 'evidence' })
  })
  return { nodes, edges }
}

export function radarGraph(sources = []) {
  const nodes = [{ id: 'radar', label: '时效雷达', type: 'RADAR', status: 'active' }]
  const edges = []
  sources.slice(0, 8).forEach(source => {
    const changed = (source.pages || []).some(page => ['ADDED', 'UPDATED'].includes(page.changeType))
    nodes.push({
      id: `source-${source.id}`,
      label: source.name,
      type: source.monitorEnabled ? `${source.monitorIntervalMinutes} MIN` : 'MANUAL',
      status: source.lastStatus === 'FAILED' ? 'offline' : changed ? 'changed' : source.monitorEnabled ? 'ready' : 'idle',
      source,
    })
    edges.push({ from: 'radar', to: `source-${source.id}`, kind: changed ? 'changed' : 'watch' })
  })
  return { nodes, edges }
}
