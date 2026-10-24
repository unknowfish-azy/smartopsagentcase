<template>
  <section class="team-workbench" aria-labelledby="team-workbench-title">
    <header class="team-workbench__header">
      <div><p class="team-workbench__eyebrow">TEAM OPERATIONS / TEAM SCOPE</p><h1 id="team-workbench-title">{{ team?.name || '团队协作' }}</h1><span v-if="team" class="team-workbench__status">{{ TEAM_ROLE_LABELS[team.role] }} · {{ team.status === 'active' ? '正常' : '已冻结' }}</span></div>
      <label class="team-workbench__switch">当前团队<select v-model="selectedTeam" aria-label="选择团队"><option v-for="item in teams" :key="item.id" :value="String(item.id)">{{ item.name }}</option></select></label>
    </header>
    <p v-if="error" role="alert" class="team-workbench__error">{{ error }}</p>
    <div class="team-workbench__layout">
      <nav class="team-workbench__menu" aria-label="团队工具菜单">
        <button v-for="item in views" :key="item.id" type="button" :class="{ active: activeView === item.id }" :aria-current="activeView === item.id ? 'page' : undefined" @click="activeView = item.id"><component :is="item.icon" aria-hidden="true" />{{ item.label }}</button>
        <div class="team-workbench__menu-end"><RouterLink :to="`/teams/${selectedTeam}`">成员与权限</RouterLink><RouterLink to="/teams">所有团队</RouterLink></div>
      </nav>
      <div class="team-workbench__surface" :aria-busy="loading">
        <section v-if="activeView === 'agents'" aria-labelledby="team-agents-title">
          <div class="team-workbench__section-head"><h2 id="team-agents-title">共享 Agent</h2><button v-if="canManage && !frozen" type="button" @click="creating = !creating"><Plus aria-hidden="true" />新增 Agent</button></div>
          <form v-if="creating" class="team-workbench__editor" @submit.prevent="createAgent"><label>名称<input v-model.trim="newAgent.name" maxlength="120" required /></label><label>描述<input v-model.trim="newAgent.description" maxlength="500" /></label><button type="submit" :disabled="busy">创建</button></form>
          <p v-if="!agents.length && !loading" class="team-workbench__empty">当前团队还没有共享 Agent。</p>
          <div class="team-workbench__agent-list"><button v-for="agent in agents" :key="agent.id" type="button" :class="{ active: selectedAgent?.id === agent.id }" @click="selectAgent(agent)"><strong>{{ agent.name }}</strong><span>{{ agent.status === 'PUBLISHED' ? '已发布' : '草稿' }}<template v-if="agent.currentVersionNo"> · 版本 {{ agent.currentVersionNo }}</template></span></button></div>
          <div v-if="selectedAgent" class="team-workbench__detail"><h3>{{ selectedAgent.name }}</h3><p>{{ selectedAgent.description || '暂无描述' }}</p><template v-if="canManage && !frozen"><label>Agent 指令<textarea v-model="draft.prompt" maxlength="20000" rows="6" placeholder="定义团队 Agent 的职责和边界" /></label><fieldset class="team-workbench__tool-picker"><legend>工具白名单</legend><label v-for="tool in catalog" :key="tool.toolId"><input type="checkbox" :checked="selectedToolIds.includes(tool.toolId)" @change="toggleTool(tool.toolId, $event.target.checked)" /><span>{{ tool.toolId }} <small>{{ tool.readOnly ? '只读' : '高风险' }}</small></span></label></fieldset><div class="team-workbench__actions"><button type="button" :disabled="busy || !draft.prompt.trim()" @click="saveDraft">保存草稿</button><button type="button" :disabled="busy" @click="publishAgent">发布版本</button></div></template></div>
        </section>
        <section v-else-if="activeView === 'tools'" aria-labelledby="team-tools-title"><div class="team-workbench__section-head"><h2 id="team-tools-title">工具菜单</h2><span>{{ toolGroups.reduce((sum, group) => sum + group.items.length, 0) }} 项</span></div><p v-if="!selectedAgent" class="team-workbench__empty">先选择共享 Agent。</p><template v-else><div v-for="group in toolGroups" :key="group.id" class="team-workbench__tool-group"><h3>{{ group.label }}</h3><div v-for="tool in group.items" :key="tool.toolId" class="team-workbench__tool"><strong>{{ tool.toolId }}</strong><span>{{ tool.readOnly ? '只读' : '需审批' }} · {{ tool.riskLevel }}</span></div></div><p v-if="!toolGroups.length" class="team-workbench__empty">当前 Agent 未开放工具。</p></template></section>
        <section v-else-if="activeView === 'runs'" aria-labelledby="team-runs-title"><div class="team-workbench__section-head"><h2 id="team-runs-title">运行与审批</h2><button type="button" :disabled="busy" @click="loadRuns">刷新</button></div><div v-if="canManage" class="team-workbench__approval-queue"><div class="team-workbench__section-head"><h3>待我审批 <span>{{ pendingApprovals.length }}</span></h3><button type="button" :disabled="busy" @click="loadApprovals">刷新队列</button></div><p v-if="!pendingApprovals.length" class="team-workbench__empty">暂无待审批运行。</p><p v-else class="team-workbench__muted">待审批运行会在团队冻结时自动失效，审批前必须完成预览。</p><ul v-if="pendingApprovals.length"><li v-for="item in pendingApprovals" :key="item.id">#{{ item.id }} · {{ item.toolId }} · 发起人 #{{ item.requesterId }}</li></ul></div><form v-if="selectedAgent && !frozen && team?.role !== 'viewer'" class="team-workbench__run-form" @submit.prevent="createRun"><label>工具<select v-model="runDraft.toolId" required><option value="" disabled>选择工具</option><option v-for="tool in tools" :key="tool.toolId" :value="tool.toolId">{{ tool.toolId }}{{ tool.readOnly ? ' · 只读' : ' · 需审批' }}</option></select></label><label>Runtime ID<input v-model.trim="runDraft.runtimeId" required maxlength="128" /></label><label>参数 JSON<textarea v-model.trim="runDraft.parameters" rows="3" spellcheck="false" /></label><button type="submit" :disabled="busy || !runDraft.toolId || !runDraft.runtimeId">提交运行请求</button></form><p v-else-if="!selectedAgent" class="team-workbench__empty">先选择共享 Agent。</p><div class="team-workbench__run-list"><article v-for="run in runs" :key="run.id"><div><strong>#{{ run.id }} · {{ run.toolId }}</strong><span>{{ run.status }} · Agent {{ run.agentId }}</span><span>发起人 #{{ run.requesterId }} · Runtime {{ run.runtimeId }}</span><pre v-if="runPreview?.id === run.id">{{ runPreview.commands.join('\n') }}</pre></div><div class="team-workbench__actions"><template v-if="run.status === 'PENDING_APPROVAL' && canManage && run.requesterId !== currentUserId && !frozen"><button type="button" :disabled="busy" @click="previewRun(run)">预览</button><button v-if="runPreview?.id === run.id" type="button" :disabled="busy" @click="approveRun(run)">批准</button></template><button v-if="run.status === 'APPROVED' && run.requesterId === currentUserId && !frozen" type="button" :disabled="busy" @click="executeRun(run)">执行</button></div></article><p v-if="!runs.length" class="team-workbench__empty">暂无运行记录。</p></div></section>
        <section v-else aria-labelledby="team-session-title"><div class="team-workbench__section-head"><h2 id="team-session-title">协作记录</h2><button v-if="!frozen && team?.role !== 'viewer'" type="button" :disabled="busy" @click="createConversation"><Plus aria-hidden="true" />新建会话</button></div><div class="team-workbench__session"><aside aria-label="团队会话列表"><button v-for="conversation in conversations" :key="conversation.id" type="button" :class="{ active: selectedConversation?.id === conversation.id }" @click="openConversation(conversation.id)">{{ conversation.title }}</button><p v-if="!conversations.length">暂无会话</p></aside><div class="team-workbench__messages"><template v-if="selectedConversation"><div ref="transcriptEl" class="team-workbench__transcript"><article v-for="message in selectedConversation.messages" :key="message.id" :class="{ receipt: message.role === 'assistant' }"><small>{{ message.role === 'assistant' ? '系统回执' : '团队成员' }}</small><p>{{ message.content }}</p></article><p v-if="!selectedConversation.messages.length">开始记录本次协作。</p></div><form v-if="!frozen && team?.role !== 'viewer'" @submit.prevent="sendMessage"><label class="sr-only" for="team-message">发送协作消息</label><textarea id="team-message" ref="composerInput" v-model.trim="messageDraft" maxlength="2000" rows="3" placeholder="记录排查过程、判断和交接信息" /><button type="submit" :disabled="busy || !messageDraft">发送</button></form></template><p v-else class="team-workbench__empty">选择会话以查看团队记录。</p></div></div></section>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { ChatLineRound, Cpu, Tools, Plus, DocumentChecked } from '@element-plus/icons-vue'
import { teamApi } from '../../api/teams.ts'
import { teamAgentsApi, teamConversationApi, teamToolsApi, teamRunsApi } from '../../api/teamAgents.ts'
import { currentSession } from '../../security/session.js'
import { TEAM_ROLE_LABELS, isTeamManager } from '../../domain/team/permissions.ts'
import { teamToolGroups, teamWorkspaceState } from '../../domain/team/teamCollaboration.ts'
import './teamCollaboration.css'

const route = useRoute(), router = useRouter()
const views = [{ id: 'agents', label: '共享 Agent', icon: Cpu }, { id: 'tools', label: '工具菜单', icon: Tools }, { id: 'runs', label: '运行与审批', icon: DocumentChecked }, { id: 'sessions', label: '协作会话', icon: ChatLineRound }]
const currentUserId = computed(() => currentSession.value?.id)
const state = reactive(teamWorkspaceState())
const teams = ref([]), team = ref(null), agents = ref([]), tools = ref([]), catalog = ref([]), runs = ref([]), pendingApprovals = ref([]), conversations = ref([]), selectedConversation = ref(null)
const runDraft = reactive({ toolId: '', runtimeId: '', parameters: '{}' })
const runPreview = ref(null)
const activeView = ref('agents'), loading = ref(false), busy = ref(false), error = ref(''), creating = ref(false), messageDraft = ref('')
const newAgent = reactive({ name: '', description: '' }), draft = reactive({ prompt: '', toolsJson: '[]' })
const composerInput = ref(null), transcriptEl = ref(null)
const selectedTeam = computed({ get: () => String(route.params.teamId || ''), set: value => router.push(`/teams/${encodeURIComponent(value)}/workspace`) })
const selectedAgent = computed(() => agents.value.find(agent => agent.id === state.agentId))
const canManage = computed(() => isTeamManager(team.value?.role))
const frozen = computed(() => team.value?.status === 'frozen')
const toolGroups = computed(() => teamToolGroups(tools.value))
const selectedToolIds = computed(() => {
  try { const values = JSON.parse(draft.toolsJson); return Array.isArray(values) ? values : [] }
  catch { return [] }
})
let generation = 0

function toggleTool(id, checked) {
  const selected = new Set(selectedToolIds.value)
  if (checked) selected.add(id)
  else selected.delete(id)
  draft.toolsJson = JSON.stringify([...selected])
}

async function load() {
  const epoch = ++generation
  const previousTeam = state.teamId
  state.selectTeam(Number(route.params.teamId))
  if (previousTeam !== state.teamId) {
    team.value = null; agents.value = []; catalog.value = []; runs.value = []; pendingApprovals.value = []; conversations.value = []; selectedConversation.value = null
    runPreview.value = null
    draft.prompt = ''; draft.toolsJson = '[]'
  }
  error.value = ''; loading.value = true
  try {
    const [list, detail, agentList, sessionList, runList] = await Promise.all([
      teamApi.list({ page: 1, pageSize: 100 }), teamApi.detail(state.teamId), teamAgentsApi.list(state.teamId),
      teamConversationApi.list(state.teamId), teamRunsApi.list(state.teamId)
    ])
    if (epoch !== generation) return
    teams.value = list.items || []; team.value = detail.team; agents.value = agentList || []; tools.value = []; conversations.value = sessionList || []; runs.value = runList || []
    pendingApprovals.value = isTeamManager(team.value?.role) ? await teamRunsApi.pendingApprovals(state.teamId).catch(() => []) : []
    catalog.value = isTeamManager(team.value?.role) && team.value?.status === 'active'
      ? await teamAgentsApi.catalog(state.teamId) : []
    if (state.agentId && !agents.value.some(agent => agent.id === state.agentId)) state.selectAgent(null)
    if (state.agentId && team.value?.status === 'active' && team.value?.role !== 'viewer') {
      tools.value = await teamToolsApi.list(state.teamId, state.agentId).catch(() => [])
    }
    if (state.conversationId && conversations.value.some(item => item.id === state.conversationId)) {
      const current = await teamConversationApi.detail(state.conversationId)
      if (epoch === generation && current.teamId === state.teamId) selectedConversation.value = current
    } else {
      state.selectConversation(null); selectedConversation.value = null
    }
  } catch (failure) { if (epoch === generation) error.value = failure.message || '团队工作台暂时无法加载' }
  finally { if (epoch === generation) loading.value = false }
}

async function mutate(action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action(); await load() }
  catch (failure) { error.value = failure.message || '操作失败，请重试' }
  finally { busy.value = false }
}

async function selectAgent(agent) {
  state.selectAgent(agent.id); draft.prompt = ''; draft.toolsJson = '[]'; tools.value = []; runDraft.toolId = ''
  try {
    const detail = await teamAgentsApi.detail(state.teamId, agent.id)
    if (state.agentId === agent.id && detail.agent.teamId === state.teamId) {
      draft.prompt = detail.draft?.prompt || detail.currentVersion?.prompt || ''
      draft.toolsJson = detail.draft?.toolsJson || detail.currentVersion?.toolsJson || '[]'
      if (agent.status === 'PUBLISHED' && team.value?.status === 'active' && team.value?.role !== 'viewer') {
        tools.value = await teamToolsApi.list(state.teamId, agent.id)
      }
    }
  } catch (failure) { error.value = failure.message || '无法读取 Agent 详情' }
}
async function createAgent() { await mutate(async () => { const created = await teamAgentsApi.create(state.teamId, newAgent); state.selectAgent(created.id); creating.value = false; newAgent.name = ''; newAgent.description = '' }) }
async function saveDraft() { await mutate(() => teamAgentsApi.saveDraft(state.teamId, state.agentId, draft)) }
async function publishAgent() { await mutate(() => teamAgentsApi.publish(state.teamId, state.agentId)) }
async function loadRuns() { try { runs.value = await teamRunsApi.list(state.teamId); await loadApprovals() } catch (failure) { error.value = failure.message || '无法读取运行记录' } }
async function loadApprovals() { if (!canManage.value) return; try { pendingApprovals.value = await teamRunsApi.pendingApprovals(state.teamId) } catch (failure) { error.value = failure.message || '无法读取待审批队列' } }
async function previewRun(run) {
  busy.value = true; error.value = ''; runPreview.value = null
  try { const result = await teamRunsApi.preview(run.id); runPreview.value = { id: run.id, commands: result.commands || [] } }
  catch (failure) { error.value = failure.message || '无法预览命令' }
  finally { busy.value = false }
}
async function createRun() {
  let parameters
  try { parameters = JSON.parse(runDraft.parameters); if (!parameters || Array.isArray(parameters) || typeof parameters !== 'object') throw new Error() }
  catch { error.value = '参数必须是 JSON 对象'; return }
  await mutate(async () => {
    const agent = await teamAgentsApi.detail(state.teamId, state.agentId)
    await teamRunsApi.create(state.teamId, state.agentId, { versionId: agent.currentVersion?.id, runtimeId: runDraft.runtimeId, toolId: runDraft.toolId, parameters })
  })
  activeView.value = 'runs'
}
async function approveRun(run) { await mutate(() => teamRunsApi.approve(run.id)); runPreview.value = null }
async function executeRun(run) {
  if (!window.confirm(`确认执行 ${run.toolId}？`)) return
  await mutate(() => teamRunsApi.execute(run.id))
}
function scrollTranscriptToEnd() { if (transcriptEl.value) transcriptEl.value.scrollTop = transcriptEl.value.scrollHeight }
async function createConversation() {
  await mutate(async () => {
    // 标题带日期时间：同日多次新建不再重名，列表中可区分
    const created = await teamConversationApi.create(state.teamId, `团队协作 ${new Date().toLocaleString('zh-CN', { hour12: false })}`)
    state.selectConversation(created.id); activeView.value = 'sessions'
  })
  await nextTick(); composerInput.value?.focus()
}
async function openConversation(id) {
  const epoch = generation
  try { const detail = await teamConversationApi.detail(id); if (epoch === generation && detail.teamId === state.teamId) { state.selectConversation(id); selectedConversation.value = detail; await nextTick(); scrollTranscriptToEnd() } }
  catch (failure) { error.value = failure.message || '无法读取会话' }
}
async function sendMessage() {
  if (!messageDraft.value || !state.conversationId) return
  const text = messageDraft.value
  busy.value = true; error.value = ''
  try { selectedConversation.value = await teamConversationApi.append(state.conversationId, text); messageDraft.value = ''; conversations.value = await teamConversationApi.list(state.teamId); await nextTick(); scrollTranscriptToEnd() }
  catch (failure) { error.value = failure.message || '发送失败' }
  finally { busy.value = false }
}
watch(() => route.params.teamId, load)
onMounted(load)
</script>
