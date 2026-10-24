function parseJsonText(value) {
  const text = String(value || '').trim()
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i)
  return JSON.parse(fenced ? fenced[1] : text)
}

export function parseFunctionCallResponse(response, tools = []) {
  try {
    const raw = typeof response === 'string' ? parseJsonText(response) : response
    const call = raw?.tool_call || raw?.toolCall || raw?.function_call || raw
    const toolId = call?.toolId || call?.tool_id || call?.name || call?.function?.name
    const parameters = call?.parameters || call?.arguments || call?.function?.arguments || {}
    if (!toolId || typeof toolId !== 'string') return { ok: false, error: '模型未返回有效工具名称' }
    if (!parameters || Array.isArray(parameters) || typeof parameters !== 'object') return { ok: false, error: '工具参数必须是对象' }
    const tool = tools.find(item => item.id === toolId)
    if (!tool) return { ok: false, error: `工具未被允许调用：${toolId}` }
    return { ok: true, toolId, parameters: Object.freeze({ ...parameters }), tool }
  } catch {
    return { ok: false, error: '模型工具调用不是有效 JSON' }
  }
}
