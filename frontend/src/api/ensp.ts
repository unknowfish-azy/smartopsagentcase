import http from '../utils/request'

/**
 * eNSP 实验知识库（华为《网络设备安装与调试（eNSP 模拟器）》第二版）。
 *
 * 后端只读目录来自 classpath 的 resources/ensp，接口前缀 /api/ensp；
 * 配置校验按教材命令规则库执行，返回逐行状态与实验步骤比对结果。
 */

export const getEnspOverview = () => http.get('/api/ensp/overview')

export const getEnspModules = () => http.get('/api/ensp/modules')

export const getEnspModule = (id: string) => http.get(`/api/ensp/modules/${encodeURIComponent(id)}`)

export const getEnspKnowledge = (params: { moduleId?: string; category?: string; keyword?: string } = {}) =>
    http.get('/api/ensp/knowledge', { params })

export const getEnspExperiments = (params: { moduleId?: string; difficulty?: string; keyword?: string } = {}) =>
    http.get('/api/ensp/experiments', { params })

export const getEnspExperiment = (id: string) => http.get(`/api/ensp/experiments/${encodeURIComponent(id)}`)

export const getEnspTopologies = () => http.get('/api/ensp/topologies')

export const getEnspTopology = (id: string) => http.get(`/api/ensp/topologies/${encodeURIComponent(id)}`)

export const parseEnspTopology = (xml: string, topologyId?: string) =>
    http.post('/api/ensp/topologies/parse', { xml, topologyId })

export const getEnspCommands = () => http.get('/api/ensp/commands')

export const getEnspStats = () => http.get('/api/ensp/stats')

/** 逐行校验一段配置（可粘贴带提示符的完整会话）。 */
export const validateEnspConfig = (lines: string[], context = 'user') =>
    http.post('/api/ensp/validate', { lines, context })

/** 与实验期望命令比对，返回得分、缺失命令与分步进度。 */
export const validateEnspExperiment = (experimentId: string, lines: string[]) =>
    http.post('/api/ensp/validate-config', { experimentId, lines })
