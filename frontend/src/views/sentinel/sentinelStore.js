/**
 * 哨兵 / 脚本 / 告警 三个模块的共享状态与后端接口层。
 *
 * 后端 `sentinel_*` 接口**已实现**（`SentinelController`，映射与本文件 `SENTINEL_API` 一一对应，
 * 表结构见 docs/sentinel-scripts-alerts-design.md）。这里**如实反映真实状态**：
 *   - 请求成功（含空数据）→ `ready`，使用后端真实数据；
 *   - 未登录（全部请求 401）→ `unauthorized`，界面提示先登录；
 *   - 登录后接口仍缺失（404）/ 网络错误 → `unavailable`，界面明说"后端未接入"。
 * 三种状态都**绝不填充看起来像真的假数据**。
 *
 * 注意：Spring Security 在认证前就拦截，未登录时真实接口与假接口都返回 401，
 * 因此只能区分"未登录"与"已登录但接口缺失"，无法在未登录时判断接口是否存在。
 */

import { reactive } from 'vue'
import request from '../../utils/request.ts'

/** 后端接口契约（与本文件一一对应，便于后端按契约实现）。 */
export const SENTINEL_API = Object.freeze({
  tasks: '/api/sentinel/tasks',
  task: id => `/api/sentinel/tasks/${encodeURIComponent(id)}`,
  taskToggle: id => `/api/sentinel/tasks/${encodeURIComponent(id)}/enabled`,
  taskRuntime: id => `/api/sentinel/tasks/${encodeURIComponent(id)}/runtime`,
  samples: (id, range) => `/api/sentinel/tasks/${encodeURIComponent(id)}/samples?range=${encodeURIComponent(range)}`,
  templates: '/api/sentinel/threshold-templates',
  scripts: '/api/sentinel/scripts',
  script: id => `/api/sentinel/scripts/${encodeURIComponent(id)}`,
  scriptVersions: id => `/api/sentinel/scripts/${encodeURIComponent(id)}/versions`,
  scriptRuns: id => `/api/sentinel/scripts/${encodeURIComponent(id)}/runs`,
  scriptLint: '/api/sentinel/scripts/lint',
  alertRules: '/api/sentinel/alert-rules',
  alerts: '/api/sentinel/alerts',
  alert: id => `/api/sentinel/alerts/${encodeURIComponent(id)}`,
  alertAcknowledge: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/acknowledge`,
  alertDispatch: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/dispatch`,
  alertClose: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/close`,
  alertAnalyze: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/analyze`,
  alertNotify: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/notify`,
  alertKnowledge: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/knowledge`,
  alertPropose: id => `/api/sentinel/alerts/${encodeURIComponent(id)}/propose-remediation`,
  knowledgeCandidates: '/api/sentinel/knowledge-candidates',
  variables: '/api/sentinel/variables',
  scriptPrepareRun: id => `/api/sentinel/scripts/${encodeURIComponent(id)}/prepare-run`,
  runResult: runId => `/api/sentinel/runs/${encodeURIComponent(runId)}/result`,
  schedules: '/api/sentinel/schedules',
  schedule: id => `/api/sentinel/schedules/${encodeURIComponent(id)}`,
  runDetail: runId => `/api/sentinel/runs/${encodeURIComponent(runId)}`,
  taskGroups: '/api/sentinel/task-groups',
  taskGroup: label => `/api/sentinel/task-groups/${encodeURIComponent(label)}/enabled`,
  taskGroupAssign: id => `/api/sentinel/tasks/${encodeURIComponent(id)}/group`,
  scriptUpload: '/api/sentinel/scripts/upload'
})

export const sentinelState = reactive({
  loaded: false,
  loading: false,
  /** 'ready' = 后端已接入（含空数据）；'unauthorized' = 未登录，需先登录；'unavailable' = 登录后接口缺失或请求失败 */
  status: 'unknown',
  reason: '',
  /** 最后一次成功拉到真实数据的时刻（ms 时间戳），用于界面展示"最后更新：N 秒前" */
  lastPolledAt: null,
  tasks: [],
  templates: [],
  scripts: [],
  runs: [],
  alertRules: [],
  alerts: [],
  schedules: [],
  taskGroups: []
})

/** 轮询定时器句柄（非响应式，避免被 Vue 追踪为依赖）。 */
let pollingTimer = null

function markUnavailable(failure) {
  const status = failure?.response?.status
  sentinelState.status = 'unavailable'
  sentinelState.reason = status === 404
    ? '后端尚未提供 /api/sentinel/* 接口，界面按未接入状态显示。'
    : (failure?.message || '无法读取哨兵数据。')
}

/**
 * 并发收集多个哨兵接口；保留每个请求的成败与 HTTP 状态码，
 * 以便在「未登录 401」与「接口未接入 404」之间做出准确判断
 * （未登录时真实接口与假接口都返回 401，只有登录后才能区分两者）。
 */
async function collect(paths) {
  return Promise.all(paths.map(async path => {
    try {
      const data = await request.get(path)
      return { ok: true, status: 200, data }
    } catch (error) {
      return { ok: false, status: error?.response?.status ?? 0, error }
    }
  }))
}

/** 把后端返回的数据解包为数组；后端用 ApiResponse.success(list) 包裹，拦截器已剥掉外层，这里直接是数组。 */
function unwrapList(payload) {
  if (Array.isArray(payload)) return payload
  if (payload && Array.isArray(payload.items)) return payload.items
  if (payload && Array.isArray(payload.data)) return payload.data
  return []
}

/** 一次性拉取三个模块的列表；按返回结果区分三种状态，绝不伪造数据。 */
export async function loadSentinel() {
  if (sentinelState.loading) return
  sentinelState.loading = true
  try {
    const [tasksR, templatesR, scriptsR, alertRulesR, alertsR, schedulesR, taskGroupsR] = await collect([
      SENTINEL_API.tasks,
      SENTINEL_API.templates,
      SENTINEL_API.scripts,
      SENTINEL_API.alertRules,
      SENTINEL_API.alerts,
      SENTINEL_API.schedules,
      SENTINEL_API.taskGroups
    ])
    const results = [tasksR, templatesR, scriptsR, alertRulesR, alertsR, schedulesR, taskGroupsR]
    // 全部失败：要么是未登录（401），要么是接口/网络问题
    if (results.every(r => !r.ok)) {
      const allUnauthorized = results.every(r => r.status === 401)
      if (allUnauthorized) {
        sentinelState.status = 'unauthorized'
        sentinelState.reason = '请先登录后再查看哨兵监控数据。'
      } else {
        markUnavailable(tasksR.error)
      }
      return
    }
    sentinelState.tasks = unwrapList(tasksR.data)
    sentinelState.templates = unwrapList(templatesR.data)
    sentinelState.scripts = unwrapList(scriptsR.data)
    sentinelState.alertRules = unwrapList(alertRulesR.data)
    sentinelState.alerts = unwrapList(alertsR.data)
    sentinelState.schedules = unwrapList(schedulesR.data)
    sentinelState.taskGroups = unwrapList(taskGroupsR.data)
    sentinelState.status = 'ready'
    sentinelState.reason = ''
    sentinelState.lastPolledAt = Date.now()
  } catch (failure) {
    markUnavailable(failure)
  } finally {
    sentinelState.loaded = true
    sentinelState.loading = false
  }
}

/**
 * 启动真实轮询：按 intervalMs 周期性拉取哨兵数据，让界面"活"起来
 * （最近采样时间、节点状态翻转、表格与巡网联动都会随之刷新）。
 * 重复调用会先清掉旧定时器，避免叠加；组件卸载务必调用 stopPolling()。
 * 轮询打的是真实接口：后端未实现 /api/sentinel/* 时静默失败（界面继续显示"未接入"），
 * 不会伪造数据，也不会刷爆后端。
 */
export function startPolling(intervalMs = 30000) {
  if (pollingTimer) clearInterval(pollingTimer)
  pollingTimer = setInterval(() => { loadSentinel() }, intervalMs)
}

/** 停止轮询，释放定时器。 */
export function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

/** 切换某个哨兵任务的启停。后端未接入时返回 false，由界面如实提示。 */
export async function toggleTask(id, enabled) {
  try {
    await request.patch(SENTINEL_API.taskToggle(id), { enabled })
    const task = sentinelState.tasks.find(item => item.id === id)
    if (task) task.enabled = enabled
    return true
  } catch {
    return false
  }
}

/**
 * 把哨兵任务重绑到一个已授权的运行连接。
 *
 * 运行通道是会话级的：后端重启或终端关闭后任务会变成「缺少运行连接」，
 * 重新连接产生的是新的 runtimeId，必须重绑而不是删任务重建。
 * 后端若该连接已有存活通道会直接复用，不会重复挂 SSH。
 */
export async function rebindRuntime(id, sessionId) {
  try {
    const response = await request.post(SENTINEL_API.taskRuntime(id), { sessionId })
    const task = sentinelState.tasks.find(item => item.id === id)
    if (task && response.data) Object.assign(task, response.data)
    return { ok: true, task: response.data }
  } catch (failure) {
    const status = failure?.response?.status
    return {
      ok: false,
      message: status === 401 ? '会话已失效，请重新登录。'
        : status === 404 ? '任务或运行连接不存在。'
          : (failure?.response?.data?.message || failure.message || '重绑失败，请重试。')
    }
  }
}

/** 计算采集成功率；没有样本时返回 null 而不是 0，避免把"没数据"说成"全失败"。 */
export function successRate(task) {
  const total = (task?.successCount ?? 0) + (task?.failureCount ?? 0)
  if (!Number.isFinite(total) || total <= 0) return null
  return task.successCount / total
}

/**
 * 触发一次告警研判。
 *
 * 后端只写 `ai_summary` 与 `recommended_script_id`，不改变状态、不执行脚本；
 * 返回的 `advice` 带证据、候选脚本与免责声明，界面必须把它当**建议**展示。
 */
export async function analyzeAlert(id) {
  try {
    const response = await request.post(SENTINEL_API.alertAnalyze(id))
    return { ok: true, advice: response.data }
  } catch (failure) {
    const status = failure?.response?.status
    return {
      ok: false,
      message: status === 404 ? '告警不存在或无权限访问。'
        : status === 503 ? '研判服务暂不可用，请稍后重试。'
          : (failure?.response?.data?.message || failure.message || '研判失败，请重试。')
    }
  }
}

/** 发送告警通知。返回**逐渠道真实结果**（sent/failed/not_configured/rejected）。 */
export async function notifyAlert(id) {
  try {
    const response = await request.post(SENTINEL_API.alertNotify(id))
    return { ok: true, results: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '通知发送失败，请重试。' }
  }
}

/**
 * 发起一次脚本执行。
 *
 * **不会执行命令**：服务端只生成既有多机执行的预览，并把意图登记为待审批。
 * 返回的 `previewId` / `confirmationNonce` 要交给既有的执行接口才算真正执行。
 */
export async function prepareScriptRun(scriptId, { trigger, runtimeIds, alertId, variables }) {
  try {
    const response = await request.post(SENTINEL_API.scriptPrepareRun(scriptId), {
      trigger, runtimeIds, alertId, variables
    })
    return { ok: true, plan: response.data }
  } catch (failure) {
    const status = failure?.response?.status
    return {
      ok: false,
      message: status === 404 ? '脚本或告警不存在，或无权限访问。'
        : status === 409 ? (failure?.response?.data?.message || '当前状态不允许发起执行。')
          : (failure?.response?.data?.message || failure.message || '发起执行失败，请重试。')
    }
  }
}

/**
 * 新建/删除定时计划。
 *
 * 定时到点后**只生成待审批预览**，不会执行命令；这一点由后端 fireDueSchedules 保证。
 */
export async function addSchedule(scriptId, { cronExpr, runtimeId }) {
  try {
    const response = await request.post(SENTINEL_API.schedules, { scriptId, cronExpr, runtimeId })
    return { ok: true, schedule: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '保存定时计划失败。' }
  }
}

export async function deleteSchedule(id) {
  try {
    await request.delete(SENTINEL_API.schedule(id))
    return { ok: true }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '删除失败。' }
  }
}

/** 读取一次执行记录的详情（用于回放）。不含确认码，回放不是重新执行。 */
export async function loadRunDetail(runId) {
  try {
    const response = await request.get(SENTINEL_API.runDetail(runId))
    return { ok: true, detail: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '读取执行记录失败。' }
  }
}

/**
 * 由团队 Agent 提出处置（团队协作链路）。
 *
 * 不执行命令：服务端生成预览并在团队侧创建待审批运行，
 * 后续仍要 preview → approve → consumeGrant。
 */
export async function proposeRemediation(alertId, { teamId, agentId, versionId, scriptId, runtimeId }) {
  try {
    const response = await request.post(SENTINEL_API.alertPropose(alertId), {
      teamId, agentId, versionId, scriptId, runtimeId
    })
    return { ok: true, proposal: response.data }
  } catch (failure) {
    const status = failure?.response?.status
    return {
      ok: false,
      message: status === 403 ? '当前账号不是该团队成员，或该工具未启用。'
        : status === 404 ? '告警、脚本或团队资源不存在。'
          : (failure?.response?.data?.message || failure.message || '提交处置建议失败，请重试。')
    }
  }
}

/**
 * 创建哨兵任务。
 *
 * 这里不做"前端校验一遍、后端再校验一遍"的双份规则：
 * 目标格式、指标白名单、间隔范围的**唯一权威在后端**。
 * 前端只做最明显的空值提示，避免把校验规则写成两份后互相漂移。
 */
export async function createTask({ name, kind, target, matchRule, intervalSec, templateId, runtimeId, groupLabel }) {
  try {
    const response = await request.post(SENTINEL_API.tasks, {
      name, kind, target, matchRule, intervalSec, templateId, runtimeId, groupLabel
    })
    return { ok: true, task: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '创建哨兵任务失败。' }
  }
}

/** 创建阈值模板。规则形如 { metric, operator, value }，复合阈值传多条。 */
export async function createTemplate({ name, description, rules, severity, debounceSec }) {
  try {
    const response = await request.post(SENTINEL_API.templates, { name, description, rules, severity, debounceSec })
    return { ok: true, template: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '创建阈值模板失败。' }
  }
}

/** 创建告警规则：把哨兵项与处置脚本绑起来，并指定分级与通知渠道。 */
export async function createAlertRule({ name, templateId, severity, scriptId, notifyChannels, webhookUrl, emailTo }) {
  try {
    const response = await request.post(SENTINEL_API.alertRules, {
      name, templateId, severity, scriptId, notifyChannels, webhookUrl, emailTo
    })
    return { ok: true, rule: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '创建告警规则失败。' }
  }
}

/** 按资产分组批量启停；返回实际改动的任务数。 */
export async function toggleGroup(label, enabled) {
  try {
    const response = await request.patch(SENTINEL_API.taskGroup(label), { enabled })
    return { ok: true, changed: response.data?.changed ?? 0 }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '批量启停失败。' }
  }
}

/** 从文件内容导入脚本。上传与手动编写走同一条预检路径。 */
export async function uploadScript({ fileName, content, language, riskLevel, tags }) {
  try {
    const response = await request.post(SENTINEL_API.scriptUpload, { fileName, content, language, riskLevel, tags })
    return { ok: true, script: response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '导入脚本失败。' }
  }
}

/** 把已关闭的告警沉淀为知识候选。未关闭时后端会拒绝（409），这里原样转达原因。 */
export async function createKnowledgeCandidate(id) {
  try {
    const response = await request.post(SENTINEL_API.alertKnowledge(id))
    return { ok: true, ...response.data }
  } catch (failure) {
    return { ok: false, message: failure?.response?.data?.message || failure.message || '沉淀失败，请重试。' }
  }
}
