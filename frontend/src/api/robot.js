/**
 * 巡检机器人 API（M0 台账 + M1 双态控制）。
 * 错误口径：不存在 404 / 状态不允许 409 / 校验失败 400（规则码）/ 桥未连接 503 / 限流 429。
 */
import request from '../utils/request'

/** 全量设备列表（真实登记档案，含 enabled 门禁状态） */
export function getRobotDevices() {
  return request.get('/api/robot/devices')
}

/** 机队自检：桥连接状态、设备状态分布，不伪装在线 */
export function getRobotFleetStatus() {
  return request.get('/api/robot/status')
}

/** 登记/更新设备（幂等按 deviceKey；需 admin.config 能力） */
export function upsertRobotDevice(payload) {
  return request.post('/api/robot/devices', payload)
}

/** 启用/禁用设备（fail-closed：登记后默认禁用） */
export function setRobotDeviceEnabled(deviceKey, enabled) {
  return request.put(`/api/robot/devices/${encodeURIComponent(deviceKey)}/enabled`, { enabled })
}

/** 实时视图：运行态 + 最新遥测 + 桥连接 */
export function getRobotLive(deviceKey) {
  return request.get(`/api/robot/devices/${encodeURIComponent(deviceKey)}/live`)
}

/** 双态切换：AUTONOMOUS / HUMAN_CONTROL / IDLE */
export function switchRobotMode(deviceKey, mode) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/mode`, { mode })
}

/** 命令下发（REST 兜底通道，与 WebSocket 共用白名单/钳位/审计） */
export function sendRobotCommand(deviceKey, op, params = {}) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/command`, { op, params })
}

/** 急停（任何登录用户可用，安全优先） */
export function robotEmergencyStop(deviceKey) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/estop`)
}

/** 人工复位：急停/故障 → 空闲 */
export function resetRobot(deviceKey) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/reset`)
}

/** 最新关键帧 + 最近一次视觉结论（刷新页面后回填；无帧返回 null） */
export function getRobotFrame(deviceKey) {
  return request.get(`/api/robot/devices/${encodeURIComponent(deviceKey)}/frame`)
}

/** M3：受理自主巡检任务（route 为空时后端用默认环形 route） */
export function submitRobotTask(deviceKey, route, planId) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/tasks`, { route, planId })
}

/** M3：设备最近 100 条任务 */
export function getRobotTasks(deviceKey) {
  return request.get(`/api/robot/devices/${encodeURIComponent(deviceKey)}/tasks`)
}

/** M3：机队任务汇总（RUNNING/PAUSED/FAILED 计数） */
export function getRobotTaskSummary() {
  return request.get('/api/robot/tasks/summary')
}

export function pauseRobotTask(id) { return request.post(`/api/robot/tasks/${id}/pause`) }
export function resumeRobotTask(id) { return request.post(`/api/robot/tasks/${id}/resume`) }
export function cancelRobotTask(id) { return request.post(`/api/robot/tasks/${id}/cancel`) }

/** M3：语音指令入口（注入检测 → 词表匹配 → 控制命令） */
export function sendRobotVoice(deviceKey, text) {
  return request.post(`/api/robot/devices/${encodeURIComponent(deviceKey)}/voice`, { text })
}

/** M4：机队调度 */
export function submitRobotFleet(deviceKeys, planId) {
  return request.post('/api/robot/fleet/submit', { deviceKeys, planId })
}
export function getRobotFleetPlan(planId) { return request.get(`/api/robot/fleet/${encodeURIComponent(planId)}`) }
export function pauseRobotFleet(planId) { return request.post(`/api/robot/fleet/${encodeURIComponent(planId)}/pause`) }
export function cancelRobotFleet(planId) { return request.post(`/api/robot/fleet/${encodeURIComponent(planId)}/cancel`) }
export function getRobotFleetPlanStatus() { return request.get('/api/robot/fleet/status') }

/** 控制台 WebSocket 端点（开发环境经 vite /ws 代理） */
export function robotConsoleEndpoint(origin = window.location.origin) {
  const url = new URL(origin)
  url.protocol = ['https:', 'wss:'].includes(url.protocol) ? 'wss:' : 'ws:'
  url.pathname = '/ws/robot/console'
  url.search = ''
  url.hash = ''
  return url.toString()
}
