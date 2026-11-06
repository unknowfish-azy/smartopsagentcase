import http from '../utils/request'

/**
 * 恢复契约平台侧只读接口（backend RecoveryContractController）。
 *
 * 主体身份由后端从会话上下文取，前端不传也不伪造 ownerUserId。
 * 返回的是平台已登记的契约与回执，不是本页面生成的判定。
 */
export function listRecoveryContracts(params = {}) {
  return http.get('/api/recovery/contracts', { params })
}

export function getRecoveryContract(id) {
  return http.get(`/api/recovery/contracts/${id}`)
}

export function getRecoveryReplay(id) {
  return http.get(`/api/recovery/contracts/${id}/replay`)
}
