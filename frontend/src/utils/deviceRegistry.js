/**
 * 设备接入台账的纯统计内核。
 *
 * 只做字段级聚合，不发请求、不造数：
 * 输入即真实接口返回的数组（服务器 / 模型连接），
 * 缺数据或字段缺失时按 0 计，绝不推断。
 */

/**
 * 汇总接入台账三类来源中的两类（服务器、模型连接）。
 * 智维 Mini 本地运行时状态由视图直接展示，不参与此汇总。
 *
 * @param {Array|null} servers  GET /api/servers 返回的服务器数组（真实状态字段 status）
 * @param {Array|null} connections GET /api/model-connections 返回的模型连接数组（enabled 字段）
 * @returns {{serverTotal: number, serverOnline: number, connectionTotal: number, connectionEnabled: number}}
 */
export function summarizeLedger(servers, connections) {
  const serverList = Array.isArray(servers) ? servers : []
  const connectionList = Array.isArray(connections) ? connections : []

  // 服务器在线以真实 status 字段判定（ONLINE / online），其余（WARNING/OFFLINE/UNKNOWN/缺失）不计在线
  const serverOnline = serverList.filter((server) => {
    const status = server && typeof server === 'object' ? server.status : null
    return status === 'ONLINE' || status === 'online'
  }).length

  // 连接启用以真实 enabled 字段判定，仅严格布尔 true 计入
  const connectionEnabled = connectionList.filter((connection) => {
    return Boolean(connection && typeof connection === 'object' && connection.enabled === true)
  }).length

  return {
    serverTotal: serverList.length,
    serverOnline,
    connectionTotal: connectionList.length,
    connectionEnabled
  }
}
