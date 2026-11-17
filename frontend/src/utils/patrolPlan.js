/**
 * 巡检计划纯函数（可单测）。
 *
 * 数据契约（单一事实来源，不臆造字段）：
 *  - 探测结果来自 POST /api/diagnostics/http（HttpProbeService.Result）：
 *      { status: 'HEALTHY'|'UNHEALTHY', statusCode, durationMs, responseBytes,
 *        truncated, assertion, summary, nextAction, errorCategory }
 *    status 由后端综合「状态码 == expectedStatus 且断言 PASS/NOT_REQUESTED」判定，
 *    前端只忠实转译，不重新发明健康判定。
 *  - 写入目标为 POST /api/inspector/check（InspectionRecordRequest）：
 *      { inspectionId?, taskId必填, target, status必填, severity必填, category?,
 *        reason必填, recommendation?, requiresHuman?, issues?, evidence?, metadata? }
 *
 * 诚实原则：所有 reason/evidence 只由真实探测返回或真实错误文本拼接，不编造结论。
 */

/** 纠察事件分类：巡检类 */
export const PATROL_CATEGORY = 'PATROL'

/** reason 上限（后端文本列有长度约束，超长截断） */
export const REASON_MAX_LENGTH = 500

/** taskId 随机段长度（避免同目标多次巡检 taskId 冲突） */
export const TASK_ID_RANDOM_LENGTH = 6

/** 截断超长文本，保留真实内容不添油加醋 */
function truncate(text, max = REASON_MAX_LENGTH) {
  const raw = String(text ?? '')
  return raw.length > max ? raw.slice(0, max) : raw
}

/** 短随机段（大写字母数字），用于 taskId 去重 */
function shortRandom(length = TASK_ID_RANDOM_LENGTH) {
  let out = ''
  while (out.length < length) {
    out += Math.random().toString(36).slice(2).toUpperCase()
  }
  return out.slice(0, length)
}

/** 判定一次 HTTP 探测是否整体通过（后端已综合状态码与断言） */
function probePassed(probeResult) {
  return Boolean(probeResult) && probeResult.status === 'HEALTHY'
}

/** 由真实探测返回拼装 evidence（保留原始字段，不做二次加工） */
function buildEvidence(probeResult) {
  if (!probeResult) return []
  const { status, statusCode, durationMs, responseBytes, truncated, assertion, summary, nextAction, errorCategory } = probeResult
  return [{
    content: JSON.stringify({ status, statusCode, durationMs, responseBytes, truncated, assertion, summary, nextAction, errorCategory }),
    source: 'diagnostics/http'
  }]
}

/**
 * 把一次 HTTP 探测结果映射为 InspectionRecordRequest 形状的 payload。
 *
 * 映射规则：
 *  - 探测成功且断言通过（status === 'HEALTHY'）→ status='PASS'，severity='INFO'
 *  - 探测完成但失败 / 断言不过（status === 'UNHEALTHY'）→ status='FAIL'，severity='HIGH'，requiresHuman=true
 *  - 接口异常（probeResult 为空，errorText 为真实错误文本）→ status='FAIL'，severity='HIGH'，requiresHuman=true，
 *    reason 使用真实错误文本（截断 500 字符）
 *
 * @param {string} targetId 探测目标 ID（来自 GET /api/diagnostics/targets 的 id 字段）
 * @param {object|null} probeResult POST /api/diagnostics/http 的真实返回；接口异常时传 null
 * @param {number} elapsedMs 前端实测耗时（毫秒）
 * @param {string} [errorText] 接口异常时的真实错误文本（如 axios 错误 message）
 * @returns {object} InspectionRecordRequest 形状 payload
 */
export function mapProbeToInspection(targetId, probeResult, elapsedMs, errorText) {
  if (!targetId) throw new Error('mapProbeToInspection 需要非空 targetId')

  const passed = probePassed(probeResult)
  const isProbeError = !probeResult

  const reason = isProbeError
    ? truncate(errorText || 'HTTP 探测接口调用异常，未返回错误详情')
    : truncate(
        probePassed(probeResult)
          ? `HTTP 探测 HEALTHY：状态码 ${probeResult.statusCode}，断言 ${probeResult.assertion}`
          : `HTTP 探测 UNHEALTHY：状态码 ${probeResult.statusCode}，断言 ${probeResult.assertion}，${probeResult.summary ?? ''}`
      )

  const payload = {
    taskId: `PATROL-${targetId}-${shortRandom()}`,
    target: targetId,
    status: passed ? 'PASS' : 'FAIL',
    severity: passed ? 'INFO' : 'HIGH',
    category: PATROL_CATEGORY,
    reason,
    requiresHuman: !passed,
    metadata: { elapsedMs: Number(elapsedMs) || 0, probeKind: 'http' }
  }

  // recommendation 使用探测返回的 nextAction（真实字段），异常时留空不编造
  if (probeResult?.nextAction) payload.recommendation = probeResult.nextAction

  // FAIL 时附带一条 issue，便于纠察详情页展示分类
  if (!passed) {
    payload.issues = [{
      category: PATROL_CATEGORY,
      severity: 'HIGH',
      reason,
      ...(probeResult?.nextAction ? { recommendation: probeResult.nextAction } : {})
    }]
  }

  payload.evidence = buildEvidence(probeResult)

  return payload
}

/**
 * 汇总巡检结果行。
 * 输入为结果行数组，每行形如 { conclusion: 'PASS'|'FAIL'|'UNKNOWN'|null }；
 * conclusion 缺失（未探测/未完成）计入 unknown。
 *
 * @param {Array<{conclusion?: string|null}>} results
 * @returns {{ total: number, pass: number, fail: number, unknown: number }}
 */
export function summarizePatrol(results) {
  const rows = Array.isArray(results) ? results : []
  const summary = { total: rows.length, pass: 0, fail: 0, unknown: 0 }
  for (const row of rows) {
    if (row?.conclusion === 'PASS') summary.pass += 1
    else if (row?.conclusion === 'FAIL') summary.fail += 1
    else summary.unknown += 1
  }
  return summary
}
