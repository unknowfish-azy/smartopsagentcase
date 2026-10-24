export function normalizeSourceLink(value, kind) {
  const url = new URL(value.trim())
  if (url.protocol !== 'https:' || url.username || url.password || url.port) throw new Error('请输入不含凭据或端口的公开 HTTPS 链接。')
  const host = url.hostname.toLowerCase()
  if (host === 'localhost' || host.endsWith('.local') || host.endsWith('.internal') || /^[\d.]+$/.test(host) || host.includes(':')) throw new Error('不支持本机或内网地址。')
  if (host === 'github.com') {
    const parts = url.pathname.split('/').filter(Boolean)
    if (parts.length < 2) throw new Error('请输入完整的 GitHub 仓库或文件链接。')
    const [owner, repo, mode, ref, ...path] = parts
    const filename = kind === 'skill' ? 'SKILL.md' : 'smartops-plugin.json'
    if (parts.length === 2) return `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/${filename}`
    if (!['blob', 'tree'].includes(mode) || !ref) throw new Error('支持 GitHub 仓库、blob 文件或 tree 目录链接。')
    return `https://raw.githubusercontent.com/${owner}/${repo}/${ref}/${[...path, ...(mode === 'tree' ? [filename] : [])].join('/')}`
  }
  url.hash = ''
  return url.href
}

export async function readRemoteSource(link, kind, signal) {
  const url = normalizeSourceLink(link, kind)
  const response = await fetch(url, { signal, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer' })
  if (!response.ok) throw new Error(`读取失败（HTTP ${response.status}）。请使用公开的原始文件链接。`)
  const limit = kind === 'skill' ? 65536 : 20000
  if (Number(response.headers.get('content-length')) > limit) throw new Error('远程文件过大。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let content = '', size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > limit) throw new Error('远程文件过大。')
      content += decoder.decode(value, { stream: true })
    }
    content += decoder.decode()
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  if (/^\s*(<!doctype html|<html)/i.test(content)) throw new Error('链接返回网页，请改用原始文件链接。')
  return { content, source: url }
}
