import http from '../utils/request'

/**
 * 预测面（/api/sentinel/forecast）接口层。
 *
 * 预测序列本身暂无后端实现（页面离线走演示数据集），这里只封装
 * 已落地的预防性契约草案端点（P1-4）。草案 digest 为空串、不落库，
 * 签发必须由 Agent 侧完成——与工单侧契约草案同一信任边界。
 */

const BASE = '/api/sentinel/forecast'

/** 按越界预测上下文生成预防性恢复契约草案（模板 forecast-preventive/v1）。 */
export function createForecastContractDraft(payload) {
  return http.post(`${BASE}/contract-draft`, payload)
}
