export function validateConnection(form, editing = false) {
  const errors = {}
  for (const [key, label] of Object.entries({ name: '连接名称', provider: '服务商', modelName: '模型 ID' })) {
    if (!String(form[key] || '').trim()) errors[key] = `请填写${label}`
  }
  try {
    const url = new URL(String(form.baseUrl || '').trim())
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error()
  } catch { errors.baseUrl = '请输入 HTTP/HTTPS 服务地址，不包含密钥、查询参数或片段' }
  if (!editing && !String(form.apiKey || '').trim()) errors.apiKey = '首次接入请填写 API Key'
  const timeout = Number(form.timeoutSeconds)
  if (!Number.isInteger(timeout) || timeout < 5 || timeout > 300) errors.timeoutSeconds = '超时需为 5–300 秒的整数'
  return errors
}

export function connectionPayload(form) {
  const payload = {
    name: form.name.trim(), provider: form.provider.trim(), baseUrl: form.baseUrl.trim().replace(/\/+$/, ''),
    modelName: form.modelName.trim(), enabled: Boolean(form.enabled), timeoutSeconds: Number(form.timeoutSeconds),
  }
  if (String(form.apiKey || '').trim()) payload.apiKey = form.apiKey.trim()
  return payload
}

export function filterConnections(items, query = '', status = 'all') {
  const needle = query.trim().toLowerCase()
  return items.filter(item =>
    (status === 'all' || (status === 'enabled' ? item.enabled : !item.enabled)) &&
    [item.name, item.provider, item.modelName].some(value => String(value || '').toLowerCase().includes(needle)))
}
