/* ToolParamsForm 的字段 schema（抽出来让组件和测试共用同一份定义）。
 *
 * 不包含网络调用，不 import Vue — 纯对象常量。
 * 字段来自后端 DiagnosisController record 定义。
 */

export const TOOL_DEFAULTS = Object.freeze({
  host: { runtimeId: '', sampleSeconds: 2 },
  kubernetes: { runtimeId: '', context: '', namespace: '', workload: '', pod: '', container: '', sinceMinutes: 60 },
  network: { runtimeId: '', context: '', namespace: '', host: '', port: 443, service: '', ingress: '', workload: '', tls: true, timeoutSeconds: 60 },
  database: { engine: '', host: '', port: 0, database: '', credentialRef: '', teamId: null, timeoutSeconds: 10, maxRows: 200 }
})

/** 每个工具的必填字段数组。
 *  顺序对应组件渲染顺序，但顺序不是强约束 — 只在 submit 时判非空。
 */
export const REQUIRED = Object.freeze({
  host: ['runtimeId'],
  kubernetes: ['runtimeId', 'context', 'namespace'],
  network: ['runtimeId', 'context', 'namespace', 'tls'],
  database: ['engine', 'host', 'database', 'credentialRef']
})

/** 工具是否属于"自动探测目标"（http / certificate 只需 targets[0].id，不经过 ToolParamsForm）。 */
export const TOOL_AUTO_TARGET = Object.freeze(['http', 'certificate'])

/** 工具是否经过 ToolParamsForm 手动填字段。 */
export function requiresParams(toolId) {
  return Boolean(TOOL_DEFAULTS[toolId]) && !TOOL_AUTO_TARGET.includes(toolId)
}
