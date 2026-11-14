import request from '../utils/request.ts'

const data = promise => promise.then(response => response.data?.data ?? response.data)

/** 诊断相关 API 客户端。
 *
 * 端点来自后端 Controller（单一事实来源，不臆造路径/字段）：
 *   - HealthDiagnosticController     : GET  /api/diagnostics/health
 *                                      GET  /api/diagnostics/admin/health
 *   - DiagnosticToolController        : GET  /api/diagnostics/targets
 *                                      POST /api/diagnostics/http           { targetId, method?, assertionPath?, assertionType?, expectedValue? }
 *                                      POST /api/diagnostics/certificate    { targetId }
 *   - HostDiagnosisController         : POST /api/operations/host/diagnose         { runtimeId, sampleSeconds? }
 *   - DatabaseDiagnosisController      : POST /api/operations/database/diagnose      { engine, host, port?, database, credentialRef, teamId?, timeoutSeconds?, maxRows? }
 *   - KubernetesDiagnosisController    : POST /api/operations/kubernetes/diagnose    { runtimeId, context, namespace, workload?, pod?, container?, sinceMinutes? }
 *   - NetworkPathDiagnosisController   : POST /api/operations/network/diagnose       { runtimeId, context, namespace, host?, port?, service?, ingress?, workload?, tls, timeoutSeconds? }
 *
 * 所有响应由 ApiResponse<T> 包装，即 { code, data, message }，data() 辅助解包取 data 字段。
 */
export const diagnosticsApi = {
  // ---- 健康快照 ----
  health: () => data(request.get('/api/diagnostics/health')),
  adminHealth: () => data(request.get('/api/diagnostics/admin/health')),

  // ---- 目标查询 ----
  targets: () => data(request.get('/api/diagnostics/targets')),

  // ---- 工具：/api/diagnostics 域（只需要 targetId，无复杂请求体）----
  http: (payload: HttpPayload) => data(request.post('/api/diagnostics/http', payload)),
  certificate: (targetId: string) => data(request.post('/api/diagnostics/certificate', { targetId })),

  // ---- 工具：/api/operations 域（真实诊断，请求体结构各异）----
  hostDiagnose: (payload: HostDiagnosePayload) =>
    data(request.post('/api/operations/host/diagnose', payload)),

  databaseDiagnose: (payload: DatabaseDiagnosePayload) =>
    data(request.post('/api/operations/database/diagnose', payload)),

  kubernetesDiagnose: (payload: KubernetesDiagnosePayload) =>
    data(request.post('/api/operations/kubernetes/diagnose', payload)),

  networkDiagnose: (payload: NetworkDiagnosePayload) =>
    data(request.post('/api/operations/network/diagnose', payload))
}

// ---- 请求体类型（与后端 record 对齐）----

export interface HttpPayload {
  targetId: string
  method?: string
  assertionPath?: string
  assertionType?: string
  expectedValue?: unknown
}

export interface HostDiagnosePayload {
  /** 必填：目标运行时 ID（需要与 runtime 注册的 ID 一致） */
  runtimeId: string
  /** 可选：采样窗口秒数，1..5，后端会夹紧 */
  sampleSeconds?: number
}

export interface DatabaseDiagnosePayload {
  /** 必填：引擎类型，如 mysql / postgresql */
  engine: string
  /** 必填：数据库主机 */
  host: string
  /** 可选：端口，后端默认 3306 / 5432 等 */
  port?: number
  /** 必填：数据库名 */
  database: string
  /** 必填：凭据引用（后端凭据存储的 ID） */
  credentialRef: string
  /** 可选：团队 ID（用于审计） */
  teamId?: number
  /** 可选：超时秒数，10..30，后端会夹紧 */
  timeoutSeconds?: number
  /** 可选：返回行数上限，后端默认 200，夹紧到 1000 */
  maxRows?: number
}

export interface KubernetesDiagnosePayload {
  /** 必填：目标 runtime ID */
  runtimeId: string
  /** 必填：kubectl context，必须显式给出，不自动推断 */
  context: string
  /** 必填：namespace */
  namespace: string
  /** 可选：workload 名称 */
  workload?: string
  /** 可选：pod 名称 */
  pod?: string
  /** 可选：container 名称 */
  container?: string
  /** 可选：回溯分钟数，后端默认 60，夹紧到 1..1440 */
  sinceMinutes?: number
}

export interface NetworkDiagnosePayload {
  /** 必填：目标 runtime ID */
  runtimeId: string
  /** 必填：kubectl context */
  context: string
  /** 必填：namespace */
  namespace: string
  /** 可选：目标主机 */
  host?: string
  /** 可选：端口，后端默认 443 */
  port?: number
  /** 可选：K8s service 名 */
  service?: string
  /** 可选：ingress 名 */
  ingress?: string
  /** 可选：workload 名 */
  workload?: string
  /** 必填：是否 TLS */
  tls: boolean
  /** 可选：总超时秒数，后端默认 60，夹紧到 10..180 */
  timeoutSeconds?: number
}

/** Tool → API 方法的路由表（在 HealthCenterView 里消费）。 */
export type ToolId = 'host' | 'database' | 'kubernetes' | 'network' | 'http' | 'certificate' | 'config'

export const TOOL_API_ROUTES: Record<ToolId, keyof typeof diagnosticsApi | null> = {
  host: 'hostDiagnose',
  database: 'databaseDiagnose',
  kubernetes: 'kubernetesDiagnose',
  network: 'networkDiagnose',
  http: 'http',
  certificate: 'certificate',
  config: null // 配置差异工具暂时没有 diagnose 端点
}

/** 哪些工具可以从已知上下文自动推导请求体（如 http/certificate 只需要 targets[0].id） */
export const TOOL_AUTO_TARGET: ToolId[] = ['http', 'certificate']
