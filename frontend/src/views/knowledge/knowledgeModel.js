const aliases = {
  '镜像拉不下来': ['imagepullbackoff', '镜像拉取失败'],
  '镜像拉取失败': ['imagepullbackoff', '镜像拉取失败'],
  '容器反复重启': ['crashloopbackoff', '反复重启'],
  '磁盘满了': ['disk full', '磁盘空间'],
  '域名解析': ['dns', '域名解析']
}

export function normalizeKnowledgeEntry(entry) {
  return {
    ...entry,
    id: String(entry.id), title: String(entry.title || ''), summary: String(entry.summary || ''),
    content: String(entry.content || entry.summary || ''), source: String(entry.source || '来源未注明'),
    tags: Array.isArray(entry.tags) ? entry.tags.map(String) : [],
    version: String(entry.version || '未标注'), applicableVersion: String(entry.applicableVersion || '未注明适用组件版本'),
    reviewStatus: 'UNVERIFIED', lastVerifiedAt: null, visibility: 'BUILTIN'
  }
}

export function rankKnowledgeEntries(entries, filters = {}) {
  const query = String(filters.query || '').trim().toLowerCase().slice(0, 300)
  const groups = query.split(/\s+/).filter(Boolean).slice(0, 16).map(term => aliases[term] || [term])
  const filtered = entries.filter(entry => ['service', 'platform', 'domain', 'reviewStatus'].every(field =>
    !filters[field] || String(entry[field] || '').toLowerCase() === String(filters[field]).trim().toLowerCase()))
  if (!groups.length) return filtered
  return filtered.map(entry => {
    const title = entry.title.toLowerCase()
    const metadata = [entry.summary, entry.service, entry.platform, entry.type, ...entry.tags].join(' ').toLowerCase()
    const content = entry.content.toLowerCase()
    const matchedTerms = groups.map(group => group.find(term => title.includes(term) || metadata.includes(term) || content.includes(term)))
    if (matchedTerms.some(term => !term)) return null
    const titleHits = matchedTerms.filter(term => title.includes(term)).length
    const score = matchedTerms.reduce((total, term) => total + (title.includes(term) ? 12 : 0) + (metadata.includes(term) ? 4 : 0) + (content.includes(term) ? 1 : 0), 0) + (title.includes(query) ? 10 : 0)
    return { ...entry, score, matchedTerms, matchReason: `${titleHits ? '标题优先' : '正文或元数据'} · 命中 ${matchedTerms.join('、')}` }
  }).filter(Boolean).sort((left, right) => right.score - left.score)
}

export function catalogProjection(entries) {
  const projected = entries.map(normalizeKnowledgeEntry).map(entry => ({
    id: entry.id, title: entry.title, summary: entry.summary, content: entry.content,
    source: entry.source, version: entry.version, applicableVersion: entry.applicableVersion,
    reviewStatus: entry.reviewStatus, lastVerifiedAt: entry.lastVerifiedAt, visibility: entry.visibility,
    domain: entry.domain || '', platform: entry.platform || '', service: entry.service || '', tags: entry.tags
  })).sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0)
  if (new Set(projected.map(entry => entry.id)).size !== projected.length) throw new Error('Duplicate knowledge IDs')
  return projected
}
