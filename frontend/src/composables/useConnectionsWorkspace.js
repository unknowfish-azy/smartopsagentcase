import { computed, onMounted, ref } from 'vue'
import { visibleRuntimeIds } from '../components/operations/connectionWorkspace.js'
import {
  canConnect,
  closeOperationRuntime,
  connectOperationSession,
  createOperationSession,
  executeMultiExec,
  getOperationAgentContext,
  getOperationCapabilities,
  getOperationSessions,
  orderOperationSessions,
  previewMultiExec,
  startOperationTunnel,
  stopOperationTunnel
} from '../api/operations.ts'
import { clearActiveOperationRuntime, setActiveOperationRuntime } from '../api/operationRuntimeState.ts'

export const CONNECTIONS_WORKSPACE_KEY = Symbol('ConnectionsWorkspace')

export function useConnectionsWorkspace() {
  const query = ref('')
  const openTabs = ref([])
  const initialLoading = ref(false)
  const initialError = ref('')
  const showCreate = ref(false)
  const activeRemoteDialog = ref('')
  const capabilities = ref([])
  const sessions = ref([])
  const draft = ref({ protocol: 'SSH', name: '', host: '', port: 22, username: '' })
  const selectedSession = ref(null)
  const runtimeId = ref('')
  const connecting = ref(false)
  const connectionError = ref('')
  const hostKey = ref(null)
  const layout = ref('SINGLE')
  const visibleRuntimes = computed(() => visibleRuntimeIds(openTabs.value, runtimeId.value, layout.value))
  const activeWorkspace = ref('TERMINAL')
  const showSessionTree = ref(true)
  const showServerInspector = ref(true)
  const tunnels = ref([])
  const selectedTunnel = ref(null)
  const activeTab = computed(() => openTabs.value.find(tab => tab.runtimeId === runtimeId.value))
  const runtimeOnline = computed(() => activeTab.value?.status === '在线')
  const showMultiExec = ref(false)
  const multiCommand = ref('')
  const multiPreview = ref(null)
  const selectedRuntimeIds = ref([])
  const multiApprovalStep = ref(0)
  const agentContext = ref(null)
  const agentContextLoading = ref(false)
  const agentContextError = ref('')

  const bridgeReady = computed(() => capabilities.value.some(item => item.protocol === 'SSH' && item.status === 'SUPPORTED'))
  const bridgeStatus = computed(() => bridgeReady.value ? '已配置 SSH 适配器' : '桥接能力未知')
  const canSubmit = computed(() => Boolean(draft.value.name && draft.value.host && draft.value.username && capabilities.value.some(item => item.protocol === draft.value.protocol && canConnect(item))))
  const orderedSessions = computed(() => orderOperationSessions(sessions.value))
  const recentSessions = computed(() => orderedSessions.value.slice(0, 5))
  const filteredSessions = computed(() => orderedSessions.value.filter(session => !query.value || `${session.name} ${session.host} ${session.protocol} ${session.tagsJson || ''}`.toLowerCase().includes(query.value.toLowerCase())))
  const onlineTabs = computed(() => openTabs.value.filter(tab => tab.status === '在线'))
  const remoteDialogTitle = computed(() => ({ terminal: '终端', session: '新建远程会话', server: '服务器与连接资源', tools: '远程工具', favorites: '我的会话', view: '工作区视图', xserver: 'X服务器', split: '分屏布局', 'multi-exec': '多重执行', tunnel: 'SSH 隧道', files: '远程文件', settings: '连接设置', macros: '宏', help: '使用帮助' })[activeRemoteDialog.value] || '远程工具')
  const remoteDialogSubtitle = computed(() => ({ terminal: '打开真实会话终端工作区', session: '创建并保存 SSH / SFTP 连接配置', server: '查看后端返回的真实会话和桥接能力', tools: '打开已经接入的终端、文件、隧道和诊断工具', favorites: '快速恢复最近保存的连接', view: '检查当前工作区面板状态', xserver: '检查 X11 图形转发桥接状态', split: '选择当前已打开运行时的显示方式', 'multi-exec': '对多个在线目标执行受审批保护的命令', tunnel: '查看当前 SSH 运行时的端口转发', files: '查看当前 SSH / SFTP 运行时的远程文件', settings: '调整当前页面的连接与终端偏好', macros: '命令序列功能与安全边界', help: '了解真实连接、权限和安全边界' })[activeRemoteDialog.value] || '')

  function capabilityLabelZh(capability) {
    if (!capability) return '能力未知'
    if (capability.status === 'SUPPORTED') return '桥接可用'
    if (capability.status === 'REQUIRES_NATIVE_BRIDGE') return '需要本地桥接'
    return capability.status
  }

  function riskLabel(risk) {
    return ({ LOW: '低', MEDIUM: '中', HIGH: '高', CRITICAL: '严重' })[risk] || risk
  }

  function agentActionLabel(action) {
    return ({
      EXPLAIN_COMMAND: '解释命令',
      ANALYZE_OUTPUT: '分析输出',
      SEARCH_KNOWLEDGE: '搜索知识',
      SAVE_TO_MEMORY: '保存到记忆'
    })[action] || action
  }

  function executionBoundaryLabel(boundary) {
    if (boundary === 'EXECUTE_REQUIRES_EXPLICIT_APPROVAL') return '执行操作需要明确审批'
    return boundary || '执行操作需要审批'
  }

  function formatLastConnected(value) {
    if (!value) return '从未连接'
    const timestamp = new Date(value)
    if (Number.isNaN(timestamp.getTime())) return '连接时间未知'
    return timestamp.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  function openRemoteDialog(type) {
    activeRemoteDialog.value = type
  }

  function closeRemoteDialog() {
    activeRemoteDialog.value = ''
  }

  function selectSession(session, tabId) {
    if (connecting.value || hostKey.value) return
    runtimeId.value = tabId || openTabs.value.findLast(tab => tab.session.id === session.id)?.runtimeId || ''
    agentContext.value = null; agentContextError.value = ''; selectedTunnel.value = null
    activeWorkspace.value = 'TERMINAL'
    selectedSession.value = session
    connectionError.value = ''
    if (runtimeId.value) loadAgentContext(runtimeId.value)
  }

  async function closeRuntimeTab(tab) {
    if (!window.confirm(`关闭 ${tab.session.name}？该连接及其隧道会结束。`)) return
    try { await closeOperationRuntime(tab.runtimeId) }
    catch (error) { if (error.status !== 404 && error.response?.status !== 404) { connectionError.value = error.message; return } }
    openTabs.value = openTabs.value.filter(item => item.runtimeId !== tab.runtimeId)
    tunnels.value = tunnels.value.filter(item => item.runtimeId !== tab.runtimeId)
    if (runtimeId.value === tab.runtimeId) {
      runtimeId.value = ''
      agentContext.value = null
      clearActiveOperationRuntime()
    }
  }

  async function loadAgentContext(nextRuntimeId) {
    agentContextLoading.value = true
    agentContextError.value = ''
    try {
      const response = await getOperationAgentContext(nextRuntimeId)
      if (runtimeId.value === nextRuntimeId) agentContext.value = response.data?.data || response.data
    } catch {
      if (runtimeId.value === nextRuntimeId) { agentContext.value = null; agentContextError.value = '暂时无法读取会话上下文' }
    } finally {
      if (runtimeId.value === nextRuntimeId) agentContextLoading.value = false
    }
  }

  function createTunnel() {
    if (!runtimeId.value) return
    const tunnel = { id: `draft-${Date.now()}`, runtimeId: runtimeId.value, name: `${selectedSession.value?.name || 'ssh'}-local`, type: 'LOCAL', listenAddress: '127.0.0.1', listenPort: 15432, targetHost: '', targetPort: 5432, sessionName: selectedSession.value?.name || 'SSH', status: 'STOPPED', autoReconnect: false, logs: [] }
    tunnels.value = [...tunnels.value, tunnel]
    selectedTunnel.value = tunnel
  }

  async function startTunnel(tunnel) {
    if (!tunnel || !runtimeId.value || tunnel.status === 'RUNNING') return
    tunnel.status = 'STARTING'
    selectedTunnel.value = tunnel
    try {
      if (!tunnel.targetHost) throw new Error('请先编辑隧道目标主机')
      const response = await startOperationTunnel(tunnel.runtimeId, { name: tunnel.name, listenAddress: tunnel.listenAddress, listenPort: tunnel.listenPort, targetHost: tunnel.targetHost, targetPort: tunnel.targetPort })
      const result = response.data?.data || response.data
      tunnel.bridgeId = result?.tunnelId || result?.id
      tunnel.status = result?.status === 'RUNNING' || result?.status === 'LISTENING' ? 'RUNNING' : 'ERROR'
      tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} START ${tunnel.status}`]
    } catch (error) {
      tunnel.status = 'ERROR'
      tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} ERROR ${error.message || 'START FAILED'}`]
    }
  }

  async function stopTunnel(tunnel) {
    if (!tunnel || !runtimeId.value || !tunnel.bridgeId) return
    try {
      await stopOperationTunnel(tunnel.runtimeId, tunnel.bridgeId)
      tunnel.status = 'STOPPED'
      tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} STOPPED`]
    } catch {
      tunnel.status = 'ERROR'
    }
    selectedTunnel.value = tunnel
  }

  function editTunnel(tunnel) {
    if (tunnel.status === 'RUNNING' || tunnel.status === 'STARTING') return
    const name = window.prompt('Tunnel name', tunnel.name)
    if (!name?.trim()) return
    const host = window.prompt('目标主机（从 SSH 服务器访问）', tunnel.targetHost)
    if (!host?.trim()) return
    const port = Number(window.prompt('目标端口', String(tunnel.targetPort)))
    const listenPort = Number(window.prompt('桥接服务器监听端口', String(tunnel.listenPort)))
    if (![port, listenPort].every(value => Number.isInteger(value) && value > 0 && value <= 65535)) return
    Object.assign(tunnel, { name: name.trim(), targetHost: host.trim(), targetPort: port, listenPort })
  }

  async function removeTunnel(tunnel) {
    if (!window.confirm(`Delete tunnel ${tunnel.name}?`)) return
    if (tunnel.status === 'STARTING') return
    if (tunnel.bridgeId) { await stopTunnel(tunnel); if (tunnel.status !== 'STOPPED') return }
    tunnels.value = tunnels.value.filter(item => item.id !== tunnel.id)
    if (selectedTunnel.value?.id === tunnel.id) selectedTunnel.value = null
  }

  function showTunnelLogs(tunnel) {
    window.alert((tunnel.logs || []).join('\n') || 'No tunnel logs')
  }

  async function connectSelected(decision = 'NONE') {
    if (!selectedSession.value || connecting.value || runtimeOnline.value) return
    const target = selectedSession.value
    connecting.value = true
    connectionError.value = ''
    try {
      const response = await connectOperationSession(target.id, decision)
      const result = response.data?.data || response.data
      if (result?.status === 'HOST_KEY_REQUIRED') {
        hostKey.value = result
        return
      }
      if (result?.status !== 'ONLINE') {
        connectionError.value = `${result?.stage || 'CONNECT'} ${result?.message || 'FAILED'}`
        return
      }
      if (!result.runtimeId) throw new Error('连接响应缺少运行时标识')
      openTabs.value.push({ runtimeId: result.runtimeId, session: { ...target }, status: '正在连接终端' })
      runtimeId.value = result.runtimeId
      setActiveOperationRuntime({ runtimeId: result.runtimeId, sessionName: target.name, host: target.host })
      activeWorkspace.value = 'TERMINAL'
      await loadAgentContext(result.runtimeId)
    } catch (error) {
      connectionError.value = `${target.host}:${target.port} ${target.protocol} · ${error.message || '连接失败'}`
    } finally {
      connecting.value = false
    }
  }

  async function previewCommand() {
    if (!multiCommand.value.trim() || !selectedRuntimeIds.value.length) { connectionError.value = '请选择至少一个在线目标并填写命令'; return }
    try {
      const targets = onlineTabs.value.filter(tab => selectedRuntimeIds.value.includes(tab.runtimeId))
      const response = await previewMultiExec({ command: multiCommand.value, runtimeIds: targets.map(tab => tab.runtimeId), productionTarget: targets.some(tab => /prod/i.test(tab.session.name || '')) })
      multiPreview.value = response.data?.data || response.data
      multiApprovalStep.value = 0
    } catch (error) { connectionError.value = error.message || '无法生成命令风险预览' }
  }

  async function approveCommand() {
    if (!multiPreview.value) return
    if (multiPreview.value.requiredApprovals > 1 && multiApprovalStep.value === 0) { multiApprovalStep.value = 1; return }
    try {
      const result = await executeMultiExec({ previewId: multiPreview.value.id, confirmationNonce: multiPreview.value.confirmationNonce, secondConfirmationNonce: multiPreview.value.requiredApprovals > 1 ? multiPreview.value.confirmationNonce : undefined })
      const execution = result.data?.data || result.data
      const failed = execution?.results?.filter(item => item.status !== 'SENT') || []
      if (failed.length) connectionError.value = `${failed.length} 个目标未发送`
    } catch (error) { connectionError.value = error.message || '批量命令未发送'; return }
    showMultiExec.value = false
    multiPreview.value = null
    multiCommand.value = ''
    selectedRuntimeIds.value = []
    multiApprovalStep.value = 0
  }

  function openMultiExec() {
    selectedRuntimeIds.value = runtimeId.value ? [runtimeId.value] : []
    multiCommand.value = ''
    multiPreview.value = null
    multiApprovalStep.value = 0
    showMultiExec.value = true
  }

  async function submitCreate() {
    if (!canSubmit.value) return
    try {
      const response = await createOperationSession({ ...draft.value })
      const created = response.data?.data || response.data
      if (created) sessions.value = [...sessions.value, created]
      if (created) selectSession(created)
      showCreate.value = false
      draft.value = { protocol: 'SSH', name: '', host: '', port: 22, username: '' }
    } catch (error) {
      connectionError.value = error.message || '保存会话失败'
    }
  }

  async function loadResources() {
    if (initialLoading.value) return
    initialLoading.value = true
    initialError.value = ''
    try {
      const [capabilityResponse, sessionResponse] = await Promise.all([getOperationCapabilities(), getOperationSessions()])
      const nextCapabilities = capabilityResponse.data?.data || capabilityResponse.data
      const nextSessions = sessionResponse.data?.data || sessionResponse.data
      if (!Array.isArray(nextCapabilities) || !Array.isArray(nextSessions)) throw new Error('连接资源响应格式异常')
      capabilities.value = nextCapabilities.filter(item => item && typeof item.protocol === 'string')
      sessions.value = nextSessions.filter(item => item && item.id != null)
    } catch (error) {
      initialError.value = error.message || '无法加载连接资源'
    } finally {
      initialLoading.value = false
    }
  }

  onMounted(loadResources)

  return {
    query,
    openTabs,
    initialLoading,
    initialError,
    showCreate,
    activeRemoteDialog,
    capabilities,
    sessions,
    draft,
    selectedSession,
    runtimeId,
    connecting,
    connectionError,
    hostKey,
    layout,
    visibleRuntimes,
    activeWorkspace,
    showSessionTree,
    showServerInspector,
    tunnels,
    selectedTunnel,
    activeTab,
    runtimeOnline,
    showMultiExec,
    multiCommand,
    multiPreview,
    selectedRuntimeIds,
    multiApprovalStep,
    agentContext,
    agentContextLoading,
    agentContextError,
    bridgeReady,
    bridgeStatus,
    canSubmit,
    orderedSessions,
    recentSessions,
    filteredSessions,
    onlineTabs,
    remoteDialogTitle,
    remoteDialogSubtitle,
    capabilityLabelZh,
    riskLabel,
    agentActionLabel,
    executionBoundaryLabel,
    formatLastConnected,
    openRemoteDialog,
    closeRemoteDialog,
    selectSession,
    closeRuntimeTab,
    loadAgentContext,
    createTunnel,
    startTunnel,
    stopTunnel,
    editTunnel,
    removeTunnel,
    showTunnelLogs,
    connectSelected,
    previewCommand,
    approveCommand,
    openMultiExec,
    submitCreate,
    loadResources
  }
}
