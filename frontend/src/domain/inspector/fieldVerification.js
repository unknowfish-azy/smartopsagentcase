/**
 * 现场核查工单面板 · 纯函数层（语义蒸馏自外部作品"现场核查/版本化核查结果"标题语义，
 * 映射为本项目纠察事件的人工复核；不指向任何真实河流系统）。
 *
 * 后端契约（InspectionVerifyRequest，POST /api/inspector/verify）：
 *   { inspectionId, resolved, status, details: Map<String,Object> }
 * details_json 落 inspection_verification 表。
 *
 * 诚实规则：
 *   - 提交失败时本地保留记录但必须标注 SESSION-LOCAL（未同步后端），绝不伪装成功
 *   - 版本号 = 已有 verification 记录数 + 本次会话已提交数，从 v1 起
 *   - 空数据显示 —，不编造历史
 */

export const VERIFY_STATUSES = Object.freeze(['PASS', 'FAIL', 'PENDING'])

/**
 * 构造 verify 请求体。
 * @param {object} event 纠察事件（需 id）
 * @param {{reading:number|string, status:string, note:string}} form 表单
 * @returns {{inspectionId:string, resolved:boolean, status:string, details:{reading:number|string, note:string}}}
 */
export function buildVerifyPayload(event, form) {
  const status = VERIFY_STATUSES.includes(form.status) ? form.status : 'PENDING'
  const reading = form.reading === '' || form.reading == null ? null : Number(form.reading)
  return {
    inspectionId: String(event?.id ?? ''),
    resolved: status === 'PASS',
    status,
    details: {
      reading: Number.isFinite(reading) ? reading : null,
      note: (form.note || '').trim()
    }
  }
}

/**
 * 下一个版本号：v1 起 = 已有 verification 数 + 会话提交数 + 1。
 * @param {object|null} verification 事件自带 verification（可能为 null）
 * @param {number} sessionCount 本次会话已提交次数
 * @returns {string} 'v1' | 'v2' | ...
 */
export function nextVersion(verification, sessionCount) {
  const base = (verification ? 1 : 0) + Math.max(0, sessionCount)
  return `v${base + 1}`
}

/**
 * 追加会话事件流条目。
 * @param {Array} events 现有会话事件
 * @param {'submitted'|'resubmitted'|'comment_created'} kind
 * @param {{version?:string, status?:string, reading?:number|null, synced?:boolean}} info
 * @returns {Array} 新数组（尾插，时间升序）
 */
export function appendSessionEvent(events, kind, info = {}) {
  const allowed = ['submitted', 'resubmitted', 'comment_created']
  if (!allowed.includes(kind)) return [...(events || [])]
  return [
    ...(events || []),
    {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      kind,
      at: new Date().toISOString(),
      version: info.version || null,
      status: info.status || null,
      reading: info.reading ?? null,
      synced: !!info.synced
    }
  ]
}

/**
 * 版本记录条目。
 * @returns {{version:string, at:string, status:string, reading:number|null, note:string, synced:boolean}}
 */
export function makeVersionEntry(version, payload, synced) {
  return {
    version,
    at: new Date().toISOString(),
    status: payload.status,
    reading: payload.details.reading,
    note: payload.details.note,
    synced: !!synced
  }
}
