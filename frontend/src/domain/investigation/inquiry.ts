export function questionsForFault(fault: Record<string, any> = {}) {
  const title = `${fault.title || ''} ${fault.evidence?.map(item => item.content).join(' ') || ''}`.toLowerCase()
  if (title.includes('502') || title.includes('bad gateway')) return [
    { id: 'persistence', priority: 'HIGH', prompt: '这个问题是否持续存在？', why: '持续性可以区分瞬时网络波动与持续的上游/配置故障。', type: 'single', options: [['once', '只出现一次'], ['persistent', '持续发生'], ['intermittent', '间歇发生'], ['unknown', '不确定']] },
    { id: 'change', priority: 'HIGH', prompt: '最近是否修改过服务或代理配置？', why: '变更时间线有助于关联 Nginx、Service 或发布操作。', type: 'single', options: [['yes', '是'], ['no', '否'], ['unknown', '不确定']] },
    { id: 'upstream', priority: 'MEDIUM', prompt: '后端服务目前是否可访问？', why: '502 常见原因是反向代理无法获得有效上游响应。', type: 'single', options: [['healthy', '正常'], ['failed', '异常'], ['unchecked', '未检查']] }
  ]
  return [{ id: 'scope', priority: 'HIGH', prompt: '这个异常影响范围是什么？', why: '先确定影响范围，避免把局部现象当成整体故障。', type: 'single', options: [['single', '单个服务'], ['multiple', '多个服务'], ['site', '整个站点'], ['unknown', '不确定']] }]
}

export function normalizeAnswer(question, value) {
  const option = question.options?.find(([id]) => id === value)
  return { value: option?.[0] || value, label: option?.[1] || value, original: value, confidence: option ? 1 : 0.6 }
}
