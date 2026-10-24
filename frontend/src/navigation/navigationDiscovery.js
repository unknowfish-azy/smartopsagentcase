export function navigationEntries(groups) {
  const seen = new Set()
  return groups.flatMap(group => [group, ...(group.children || [])].map(item => ({
    to: item.to, title: item.cn || item.label, label: item.label || '', group: group.cn || group.label
  }))).filter(item => {
    if (!item.to || seen.has(item.to)) return false
    seen.add(item.to)
    return true
  })
}
export function searchEntries(entries, query) {
  const tokens = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return entries.filter(item => tokens.every(token => `${item.title} ${item.label} ${item.group} ${item.to}`.toLocaleLowerCase().includes(token)))
}
export function restoreRecentPaths(raw, entries, limit = 5) {
  const allowed = new Set(entries.map(item => item.to))
  try {
    const paths = JSON.parse(raw)
    return Array.isArray(paths) ? [...new Set(paths.filter(path => typeof path === 'string' && allowed.has(path)))].slice(0, limit) : []
  } catch { return [] }
}
export function rememberRecentPath(raw, path, entries, limit = 5) {
  const paths = restoreRecentPaths(raw, entries, limit).filter(item => item !== path)
  return JSON.stringify([path, ...paths].slice(0, limit))
}
export function restoreTabPaths(raw, titles) {
  try {
    const paths = JSON.parse(raw)
    return [...new Set(['/admin', ...(Array.isArray(paths) ? paths : []).filter(path => typeof path === 'string' && Object.hasOwn(titles, path))])].slice(0, 24)
  } catch { return ['/admin'] }
}
