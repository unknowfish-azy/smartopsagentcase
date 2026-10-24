export const pluginEntries = Object.freeze({
  knowledge: { label: '运维知识库', path: '/knowledge' },
  connections: { label: '连接中心', path: '/connections' },
  inspector: { label: '纠察中心', path: '/inspector' },
  statistics: { label: '巡检统计', path: '/inspector/statistics' },
  models: { label: '模型接入', path: '/model-settings' },
  tokens: { label: 'Token 用量', path: '/token-usage' },
  processes: { label: '进程诊断', path: '/tools/processes' },
  trace: { label: '执行轨迹', path: '/agent/trace' }
})
export const pluginCategories = ['诊断分析', '连接与工具', '知识与记忆', '模型能力']
export const builtinPlugins = [
  { id: 'ops-knowledge', name: '运维知识引擎', shortName: '知识引擎', category: '知识与记忆', icon: 'Collection', entry: 'knowledge', dependencies: [], description: '查阅 Linux、网络与服务排障知识，将线索转化为可复用的排查路径。', capabilities: ['知识检索', '故障手册', '命令参考'], boundary: '本地知识浏览，不执行手册中的命令。' },
  { id: 'ops-connections', name: '远程连接工作台', shortName: '远程连接', category: '连接与工具', icon: 'Connection', entry: 'connections', dependencies: [], description: '在统一工作台中管理连接、会话和远程文件，连接真实运维现场。', capabilities: ['会话入口', '远程文件', '连接管理'], boundary: '远程操作需已有后端、有效连接和授权；添加此入口不会自动连接主机。' },
  { id: 'ops-inspector', name: '巡检事件中枢', shortName: '巡检事件', category: '诊断分析', icon: 'View', entry: 'inspector', dependencies: ['ops-knowledge'], description: '集中查看巡检事件与证据，关联知识线索，保留故障分析上下文。', capabilities: ['事件浏览', '证据查看', '故障关联'], boundary: '事件由现有纠察服务提供，添加插件不自动创建巡检任务。' },
  { id: 'ops-models', name: '模型接入适配器', shortName: '模型接入', category: '模型能力', icon: 'Cpu', entry: 'models', dependencies: [], description: '配置模型连接，为运维分析准备可选推理能力与调用入口。', capabilities: ['模型配置', '连接管理', '测试入口'], boundary: '实际调用需要有效服务配置和现有内部调用鉴权。' },
  { id: 'ops-processes', name: '进程诊断手册', shortName: '进程诊断', category: '诊断分析', icon: 'Monitor', entry: 'processes', dependencies: ['ops-knowledge'], description: '按 CPU、内存与进程异常选择诊断场景，查看证据清单与只读命令。', capabilities: ['场景选择', '证据清单', '命令预览'], boundary: '提供诊断参考，不读取本机数据、不执行命令。' },
  { id: 'ops-tokens', name: 'Token 预算观察器', shortName: '用量观察', category: '模型能力', icon: 'DataLine', entry: 'tokens', dependencies: ['ops-models'], description: '观察模型调用消耗和日趋势，配置月度提醒额度，识别用量变化。', capabilities: ['用量趋势', '预算提醒', '模型筛选'], boundary: '依赖真实调用账本；额度是提醒值，不是服务商余额。' },
  { id: 'ops-statistics', name: '巡检统计透镜', shortName: '巡检统计', category: '诊断分析', icon: 'DataAnalysis', entry: 'statistics', dependencies: ['ops-inspector'], description: '从巡检统计中观察事件分布和处理情况，定位运维关注点。', capabilities: ['事件统计', '分布观察'], boundary: '统计由现有纠察接口提供。' },
  { id: 'ops-trace', name: '执行轨迹视窗', shortName: '执行轨迹', category: '知识与记忆', icon: 'Document', entry: 'trace', dependencies: [], description: '打开既有执行轨迹工作区，查看智能体步骤与上下文。', capabilities: ['轨迹入口', '步骤查看'], boundary: '沿用既有页面的数据与演示标识，不声明实时执行状态。' }
].map(item => Object.freeze({ ...item, version: '1.0.0', source: 'builtin' }))
