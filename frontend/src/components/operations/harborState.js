const labels = {
  UNCHECKED: '尚未检查读取能力', CHECKING: '正在检查', STALE: '检查结果已过期',
  READABLE: '项目读取成功', UNCONFIGURED: '尚未配置', CONFIGURATION: '配置不完整',
  AUTHENTICATION: '认证失败', AUTHORIZATION: '读取权限不足', TLS: '证书校验失败',
  NETWORK: '网络不可达', TIMEOUT: '请求超时', INVALID_RESPONSE: '响应格式异常',
  RATE_LIMIT: '上游限流', UPSTREAM: '上游响应异常', FAILED: '检查失败'
}

export function connectionPresentation(check, loading, now = Date.now()) {
  let state = loading ? 'CHECKING' : check?.state || 'UNCHECKED'
  if (state === 'READABLE' && (!Number.isFinite(Date.parse(check.checkedAt)) || now - Date.parse(check.checkedAt) >= 300000)) state = 'STALE'
  return { state, label: labels[state] || labels.FAILED, healthy: state === 'READABLE' }
}

export function createRequestGate() {
  let sequence = 0
  return { begin: () => ++sequence, current: ticket => ticket === sequence, invalidate: () => ++sequence }
}

export function repositoryWithinProject(project, name) {
  if (!name.startsWith(`${project}/`)) return ''
  const repository = name.slice(project.length + 1)
  return /^[a-z0-9][a-z0-9._-]*(\/[a-z0-9][a-z0-9._-]*)*$/.test(repository) ? repository : ''
}

export function filterArtifacts(items, query) {
  const needle = query.trim().toLowerCase()
  return items.filter(item => [item.digest, ...(item.tags || [])].some(value => String(value).toLowerCase().includes(needle)))
}
