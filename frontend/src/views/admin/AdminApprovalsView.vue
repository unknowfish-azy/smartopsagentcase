<template>
  <section aria-labelledby="approvals-title">
    <header class="admin-page-header">
      <div>
        <p class="admin-eyebrow">AGENT GOVERNANCE / APPROVALS</p>
        <h1 id="approvals-title">审批监督</h1>
        <p class="admin-muted">仅列出你具备批准资格的团队待办；申请者、工具、预览状态与决策依据分开显示。批准必须由本人先完成预览，禁止自批。</p>
      </div>
      <button type="button" :disabled="loading || refreshing" @click="load({ preserve: true })">{{ refreshing ? '刷新中…' : '刷新' }}</button>
    </header>
    <p v-if="refreshing" class="admin-muted admin-refresh-hint" role="status">正在刷新审批待办…</p>
    <p v-else-if="updatedAt && data" class="admin-muted admin-refresh-hint">最近更新：{{ formatAdminTime(updatedAt) }} · 已检查 {{ data.teamsLoaded }} 个具备批准资格的团队</p>
    <AdminErrorState :message="error" :busy="loading || refreshing" @retry="load()" />
    <p v-if="data?.teamsFailed?.length" class="admin-notice" role="status">以下团队未能读取待办（可能已冻结或批准资格被移除）：{{ data.teamsFailed.join('、') }}</p>
    <p v-if="loading" role="status">正在加载审批待办…</p>

    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="待审批运行列表">
      <table>
        <thead><tr><th scope="col">团队</th><th scope="col">运行</th><th scope="col">工具</th><th scope="col">申请者</th><th scope="col">提交时间</th><th scope="col">预览状态</th><th scope="col">操作</th></tr></thead>
        <tbody>
          <tr v-for="run in data.pending" :key="run.id">
            <td>{{ run.teamName }}<span class="admin-muted"> · ID {{ run.teamId }}</span></td>
            <td>#{{ run.id }}</td>
            <td>{{ run.toolId }}<span v-if="run.readOnly" class="admin-muted"> · 只读</span></td>
            <td>ID {{ run.requesterId }}</td>
            <td>{{ formatAdminTime(run.createdAt) }}</td>
            <td><span class="admin-status" :class="run.previewedBy ? 'admin-status--success' : 'admin-status--warning'">{{ run.previewedBy ? '已预览' : '未预览' }}</span></td>
            <td><div class="admin-actions"><button type="button" @click="openDetail(run)">详情与审批</button></div></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!data.teamsLoaded" class="admin-empty">你目前没有具备批准资格的团队，因此没有可监督的审批待办。</p>
      <p v-else-if="!data.pending.length" class="admin-empty">所列团队当前没有待审批的 Agent 运行。</p>
    </div>

    <section v-if="data" class="approval-history" aria-labelledby="recent-runs-title">
      <h2 id="recent-runs-title" class="admin-section-title">近期运行记录</h2>
      <p class="admin-muted">来自同一批团队的权威运行记录，用于核对审批之后的执行结果；只展示元数据与状态。</p>
      <div class="admin-table-wrap" tabindex="0" aria-label="近期运行记录列表">
        <table>
          <thead><tr><th scope="col">团队</th><th scope="col">运行</th><th scope="col">工具</th><th scope="col">申请者</th><th scope="col">提交时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
          <tbody>
            <tr v-for="run in data.recent" :key="run.id">
              <td>{{ run.teamName }}</td>
              <td>#{{ run.id }}</td>
              <td>{{ run.toolId }}</td>
              <td>ID {{ run.requesterId }}</td>
              <td>{{ formatAdminTime(run.createdAt) }}</td>
              <td><span class="admin-status" :class="statusTone(run.status)">{{ statusLabel(run.status) }}</span></td>
              <td><div class="admin-actions"><button type="button" @click="openDetail(run)">查看</button></div></td>
            </tr>
          </tbody>
        </table>
        <p v-if="!data.recent.length" class="admin-empty">近期还没有已审批或已执行的运行记录。</p>
      </div>
    </section>

    <AdminDialog v-if="dialogOpen" title="运行详情与审批" :busy="busy" @close="closeDetail">
      <p v-if="detailLoading" role="status">正在加载运行详情…</p>
      <AdminErrorState v-else-if="detailError" :message="detailError" @retry="loadDetail" />
      <template v-else-if="detail">
        <dl class="approval-detail-grid">
          <dt>运行编号</dt><dd>#{{ detail.id }}<span class="admin-muted"> · 团队 ID {{ detail.teamId }}</span></dd>
          <dt>状态</dt><dd><span class="admin-status" :class="statusTone(detail.status)">{{ statusLabel(detail.status) }}</span></dd>
          <dt>工具</dt><dd>{{ detail.toolId }}<span class="admin-muted"> · {{ detail.readOnly ? '只读' : '写入，需要预览摘要一致' }}</span></dd>
          <dt>申请者</dt><dd>ID {{ detail.requesterId }}</dd>
          <dt>提交时间</dt><dd>{{ formatAdminTime(detail.createdAt) }}</dd>
          <dt>预览人</dt><dd>{{ detail.previewedBy ? ('ID ' + detail.previewedBy) : '尚未预览' }}</dd>
          <dt>审批人</dt><dd>{{ detail.approvedBy ? ('ID ' + detail.approvedBy) : '尚未审批' }}</dd>
          <dt>许可有效期</dt><dd>{{ detail.grantExpiresAt ? formatAdminTime(detail.grantExpiresAt) : '无（未批准或不可执行）' }}</dd>
          <dt>决策依据</dt><dd>{{ detail.decisionBasis || '未记录' }}</dd>
        </dl>
        <p class="admin-muted">原始参数不在此展示；批准前请用预览核对将要执行的命令。</p>
        <section v-if="pendingRun" class="approval-actions" aria-labelledby="approval-actions-title">
          <h3 id="approval-actions-title">审批操作</h3>
          <div class="admin-actions">
            <button type="button" :disabled="busy" @click="runPreview">{{ busy ? '处理中…' : (previewedByMe ? '重新生成预览' : '生成预览') }}</button>
          </div>
          <p v-if="previewError" class="admin-error" role="alert">{{ previewError }}</p>
          <ol v-if="previewCommands.length" class="approval-commands">
            <li v-for="(command, index) in previewCommands" :key="index"><code>{{ command }}</code></li>
          </ol>
          <form @submit.prevent="approve">
            <label>决策依据（可选，最多 800 字）<textarea v-model.trim="decisionBasis" maxlength="800" rows="3" :disabled="busy"></textarea></label>
            <button type="submit" :disabled="busy || !previewedByMe">{{ busy ? '提交中…' : '批准运行' }}</button>
            <p v-if="!previewedByMe" class="admin-muted">批准前必须由你本人完成一次预览，服务端会校验预览人。</p>
          </form>
          <p v-if="actionError" class="admin-error" role="alert">{{ actionError }}</p>
        </section>
        <p v-else class="admin-notice">该运行已不在待审批状态，页面仅展示记录。</p>
      </template>
      <footer><button type="button" :disabled="busy" @click="closeDetail">关闭</button></footer>
    </AdminDialog>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { teamApi } from '../../api/teams.ts'
import { teamRunsApi } from '../../api/teamAgents.ts'
import AdminDialog from '../../components/admin/AdminDialog.vue'
import AdminErrorState from '../../components/admin/AdminErrorState.vue'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
import { currentSession } from '../../security/session.js'

const RECENT_LIMIT_PER_TEAM = 10
const APPROVE_READY = ['owner', 'admin', 'specialist']
const statusLabels = {
  PENDING_APPROVAL: '待审批', APPROVED: '已批准待执行', RUNNING: '执行中',
  SUCCEEDED: '已成功', FAILED: '已失败', EXPIRED: '已过期'
}
const statusLabel = value => statusLabels[value] || value
const statusTone = value => value === 'SUCCEEDED' ? 'admin-status--success'
  : value === 'FAILED' || value === 'EXPIRED' ? 'admin-status--danger'
    : value === 'PENDING_APPROVAL' ? 'admin-status--warning' : 'admin-status--muted'

// 团队列表是唯一可跨团队发现待办的既有契约；管理员入口不授予团队成员权限，
// 因此这里只检查自己确实具备批准资格的团队，不做任何 admin 兜底。
const { data, loading, refreshing, error, updatedAt, load } = useAdminResource(async () => {
  const page = await teamApi.list({ page: 1, pageSize: 100 })
  const teams = (page.items || []).filter(team => team.status === 'active' && APPROVE_READY.includes(team.role))
  const results = await Promise.allSettled(teams.map(async team => {
    const pending = await teamRunsApi.pendingApprovals(team.id)
    let recent = []
    try { recent = await teamRunsApi.list(team.id) } catch { recent = [] }
    return { team, pending: pending || [], recent: recent || [] }
  }))
  const pending = []
  const recent = []
  const teamsFailed = []
  let teamsLoaded = 0
  results.forEach((result, index) => {
    if (result.status !== 'fulfilled') { teamsFailed.push(teams[index].name); return }
    teamsLoaded += 1
    const { team, pending: teamPending, recent: teamRecent } = result.value
    teamPending.forEach(run => pending.push({ ...run, teamName: team.name }))
    teamRecent
      .filter(run => run.status !== 'PENDING_APPROVAL')
      .slice(0, RECENT_LIMIT_PER_TEAM)
      .forEach(run => recent.push({ ...run, teamName: team.name }))
  })
  pending.sort((left, right) => left.id - right.id)
  recent.sort((left, right) => (right.createdAt || '').localeCompare(left.createdAt || ''))
  return { pending, recent: recent.slice(0, 40), teamsLoaded, teamsFailed }
})

const dialogOpen = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const pendingRun = ref(null)
const previewCommands = ref([])
const previewError = ref('')
const actionError = ref('')
const decisionBasis = ref('')
const busy = ref(false)
let detailId = 0
const previewedByMe = computed(() => Boolean(detail.value?.previewedBy) && detail.value.previewedBy === currentSession.value?.id)

function openDetail(run) {
  dialogOpen.value = true
  detail.value = null
  detailError.value = ''
  previewCommands.value = []
  previewError.value = ''
  actionError.value = ''
  decisionBasis.value = ''
  pendingRun.value = { ...run }
  detailId = run.id
  loadDetail()
}
async function loadDetail() {
  detailLoading.value = true
  detailError.value = ''
  try { detail.value = await teamRunsApi.detail(detailId) }
  catch (failure) { detailError.value = failure.message || '运行详情加载失败' }
  finally { detailLoading.value = false }
}
async function runPreview() {
  if (busy.value) return
  busy.value = true
  previewError.value = ''
  actionError.value = ''
  try {
    const result = await teamRunsApi.preview(detailId)
    previewCommands.value = Array.isArray(result?.commands) ? result.commands : []
    await loadDetail()
    // 预览后服务端会记录预览人；若详情未刷新出来，至少让按钮状态依赖重新读取的结果。
    if (!detail.value?.previewedBy) previewError.value = '预览已执行，但运行详情未返回预览人，请刷新后重试。'
  } catch (failure) { previewError.value = failure.message || '预览失败，请确认工具与运行状态' }
  finally { busy.value = false }
}
async function approve() {
  if (busy.value || !previewedByMe.value) return
  busy.value = true
  actionError.value = ''
  const basis = decisionBasis.value
  try {
    await teamRunsApi.approve(detailId, basis || undefined)
    closeDetail()
    await load({ preserve: true })
  } catch (failure) { actionError.value = failure.message || '审批失败，请核对预览与运行状态' }
  finally { busy.value = false }
}
function closeDetail() {
  if (busy.value) return
  dialogOpen.value = false
  detail.value = null
  pendingRun.value = null
  previewCommands.value = []
  previewError.value = ''
  actionError.value = ''
  decisionBasis.value = ''
}
onMounted(() => load())
</script>

<style scoped>
.admin-refresh-hint { margin: 6px 0 12px; font-size: 13px; }
.approval-history { display: grid; gap: 8px; margin-top: 26px; }
.approval-detail-grid { display: grid; grid-template-columns: minmax(96px, 130px) 1fr; gap: 8px 14px; margin: 0 0 14px; }
.approval-detail-grid dt { color: var(--admin-muted); font-size: 13px; }
.approval-detail-grid dd { margin: 0; overflow-wrap: anywhere; }
.approval-actions { display: grid; gap: 12px; padding-top: 14px; border-top: 1px solid var(--admin-border); }
.approval-actions form { display: grid; gap: 10px; justify-items: start; }
.approval-actions label { display: grid; gap: 6px; width: 100%; font-size: 13px; color: var(--admin-muted); }
.approval-actions textarea { width: 100%; resize: vertical; }
.approval-commands { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
.approval-commands code { overflow-wrap: anywhere; }
</style>
