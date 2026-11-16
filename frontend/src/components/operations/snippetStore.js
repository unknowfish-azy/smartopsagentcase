/**
 * 命令片段库（对标 MobaXterm macros/snippets）：localStorage 持久化。
 * 纯函数可测：校验、封顶 50 条、ID 生成由调用方传入。
 */

const STORAGE_KEY = 'smartops_ops_snippets:v1'
export const SNIPPETS_CAP = 50

export function loadSnippets(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
  if (!storage) return []
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isValidSnippet).map(normalize)
  } catch {
    return []
  }
}

export function saveSnippets(snippets, storage = typeof localStorage !== 'undefined' ? localStorage : null) {
  if (!storage) return false
  const valid = (Array.isArray(snippets) ? snippets : []).filter(isValidSnippet).map(normalize).slice(-SNIPPETS_CAP)
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(valid))
    return true
  } catch {
    return false
  }
}

export function upsertSnippet(snippets, snippet, idFactory = defaultId) {
  const next = { id: snippet.id || idFactory(), name: String(snippet.name || '').trim(), command: String(snippet.command || '') }
  if (!isValidSnippet(next)) return snippets
  const exists = snippets.findIndex(item => item.id === next.id)
  if (exists >= 0) {
    const copy = [...snippets]
    copy[exists] = next
    return copy
  }
  return [...snippets, next].slice(-SNIPPETS_CAP)
}

export function removeSnippet(snippets, id) {
  return snippets.filter(item => item.id !== id)
}

function isValidSnippet(snippet) {
  return snippet && typeof snippet === 'object'
    && typeof snippet.name === 'string' && snippet.name.trim().length > 0
    && typeof snippet.command === 'string' && snippet.command.trim().length > 0
}

function normalize(snippet) {
  return { id: String(snippet.id || ''), name: snippet.name.trim(), command: snippet.command }
}

function defaultId() {
  return `snippet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}
