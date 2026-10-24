<template>
  <section class="harbor-browser" aria-label="Harbor 项目与仓库浏览器">
    <header class="harbor-head">
      <div><strong>HARBOR / READ-ONLY CATALOG</strong><p>使用后端配置的实例与读取凭据；不会推送、删除或修改策略。</p></div>
      <button type="button" :disabled="loadingStatus" @click="loadStatus">{{ loadingStatus ? '检查中…' : '重新检查连接' }}</button>
    </header>
    <div class="connection-status" role="status">
      <strong :class="{ readable: connectionState.healthy }">{{ connectionState.label }}</strong>
      <span>{{ configured ? '地址已配置，不等于服务健康' : '等待实例配置' }}</span>
      <small v-if="connection?.checkedAt">检查时间：{{ new Date(connection.checkedAt).toLocaleString() }} · 五分钟后过期，不自动请求</small>
      <small v-if="connection?.message">{{ connection.message }}</small>
      <small v-if="connection?.traceId">检查 TraceId: {{ connection.traceId }}</small>
    </div>
    <p v-if="statusError" class="harbor-error" role="alert">{{ statusError }}</p>
    <div v-if="!configured && !loadingStatus" class="harbor-empty"><strong>尚未配置 Harbor</strong><p>请由管理员配置后端 Harbor 地址与只读凭据。此处不展示或收集密码。</p></div>
    <template v-if="configured">
      <div class="harbor-toolbar">
        <span>{{ projectTotal }} 个可见项目 · 当前凭据范围</span>
        <div class="harbor-actions"><button type="button" :disabled="loadingProjects" @click="loadProjects(projectPage)">刷新项目</button><button type="button" :disabled="loadingProjects || projectPage <= 1" @click="loadProjects(projectPage - 1)">上一页</button><span>{{ projectPage }} / {{ projectPages }}</span><button type="button" :disabled="loadingProjects || projectPage >= projectPages" @click="loadProjects(projectPage + 1)">下一页</button></div>
      </div>
      <p v-if="projectError" class="harbor-error" role="alert">{{ projectError }}</p>
      <div v-else class="harbor-grid">
        <nav class="project-list" aria-label="Harbor 项目">
          <button v-for="project in projects" :key="project.name" type="button" :aria-pressed="selectedProject === project.name" class="project-item" @click="selectProject(project.name)"><span>{{ project.name }}</span><small>{{ project.repositoryCount }} 个仓库 · {{ project.publicAccess ? '公开' : '私有' }}</small></button>
          <p v-if="!loadingProjects && !projects.length" class="harbor-muted">当前凭据未返回可见项目。</p>
        </nav>
        <div class="repository-list">
          <div class="repository-head"><strong>{{ selectedProject || '选择一个项目' }}</strong><span v-if="selectedProject">{{ repositoryTotal }} 个仓库</span></div>
          <label v-if="selectedProject" class="filter-label">筛选当前页仓库<input v-model="repositoryFilter" type="search" placeholder="仓库名称（仅本页）" /></label>
          <p v-if="repositoryError" class="harbor-error" role="alert">{{ repositoryError }}</p>
          <p v-else-if="loadingRepositories" class="harbor-muted">正在读取仓库…</p>
          <div v-else-if="selectedProject" class="repository-table">
            <button v-for="repository in visibleRepositories" :key="repository.name" type="button" class="repository-row" :aria-pressed="selectedRepository === repository.name" @click="selectRepository(repository.name)"><span>{{ repository.name }}</span><small>{{ repository.artifactCount }} 个制品 · 查看详情</small></button>
            <p v-if="!visibleRepositories.length" class="harbor-muted">本页没有匹配的仓库。</p>
            <div class="harbor-pagination"><button type="button" :disabled="repositoryPage <= 1" @click="loadRepositories(repositoryPage - 1)">上一页</button><span>第 {{ repositoryPage }} / {{ repositoryPages }} 页</span><button type="button" :disabled="repositoryPage >= repositoryPages" @click="loadRepositories(repositoryPage + 1)">下一页</button></div>
          </div>
          <p v-else class="harbor-muted">点击左侧项目查看仓库。</p>
        </div>
      </div>
      <section v-if="selectedRepository" class="artifact-panel" aria-label="制品详情">
        <header class="harbor-head"><div><h3>{{ selectedRepository }}</h3><p>{{ artifactTotal }} 个制品 · 未读取扫描报告，不表示安全评估通过</p></div><button type="button" :disabled="loadingArtifacts" @click="loadArtifacts(artifactPage)">刷新制品</button></header>
        <label class="filter-label">筛选当前页 Tag / Digest<input v-model="artifactFilter" type="search" placeholder="标签或 sha256 摘要（仅本页）" /></label>
        <p v-if="artifactError" class="harbor-error" role="alert">{{ artifactError }}</p>
        <p v-else-if="loadingArtifacts" role="status">正在读取制品…</p>
        <template v-else>
          <article v-for="artifact in visibleArtifacts" :key="artifact.digest" class="artifact-card">
            <strong>{{ artifact.tags.length ? artifact.tags.join(' / ') : '无标签制品' }}</strong><code>{{ artifact.digest }}</code>
            <dl><div><dt>平台</dt><dd>{{ artifact.platforms.join('、') || '未返回平台信息' }}</dd></div><div><dt>类型 / 大小</dt><dd>{{ artifact.type || '未知' }} / {{ formatSize(artifact.size) }}</dd></div><div><dt>推送时间</dt><dd>{{ artifact.pushedAt || '未返回' }}</dd></div></dl>
          </article>
          <p v-if="!visibleArtifacts.length" class="harbor-muted">本页没有匹配的制品。</p>
        </template>
        <div class="harbor-pagination"><button type="button" :disabled="loadingArtifacts || artifactPage <= 1" @click="loadArtifacts(artifactPage - 1)">上一页制品</button><span>{{ artifactPage }} / {{ artifactPages }}</span><button type="button" :disabled="loadingArtifacts || artifactPage >= artifactPages" @click="loadArtifacts(artifactPage + 1)">下一页制品</button></div>
      </section>
      <small v-if="traceId" class="harbor-trace">最近成功读取 TraceId: {{ traceId }}</small>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import http from '../../utils/request'
import { connectionPresentation, createRequestGate, filterArtifacts, repositoryWithinProject } from './harborState.js'

const configured = ref(false), connection = ref(null), now = ref(Date.now())
const projects = ref([]), repositories = ref([]), artifacts = ref([])
const selectedProject = ref(''), selectedRepository = ref(''), traceId = ref('')
const projectTotal = ref(0), repositoryTotal = ref(0), artifactTotal = ref(0)
const projectPage = ref(1), repositoryPage = ref(1), artifactPage = ref(1)
const projectPages = ref(1), repositoryPages = ref(1), artifactPages = ref(1)
const statusError = ref(''), projectError = ref(''), repositoryError = ref(''), artifactError = ref('')
const loadingStatus = ref(false), loadingProjects = ref(false), loadingRepositories = ref(false), loadingArtifacts = ref(false)
const repositoryFilter = ref(''), artifactFilter = ref('')
const gates = { status: createRequestGate(), projects: createRequestGate(), repositories: createRequestGate(), artifacts: createRequestGate() }
const connectionState = computed(() => connectionPresentation(connection.value, loadingStatus.value, now.value))
const visibleRepositories = computed(() => repositories.value.filter(item => item.name.toLowerCase().includes(repositoryFilter.value.trim().toLowerCase())))
const visibleArtifacts = computed(() => filterArtifacts(artifacts.value, artifactFilter.value))
const dataOf = response => response.data || response
const pages = data => Math.max(1, Math.ceil(data.total / data.pageSize))
const formatSize = size => Number.isFinite(size) && size >= 0 ? `${(size / 1048576).toFixed(2)} MiB` : '未知'

function resetArtifacts() {
  gates.artifacts.invalidate()
  selectedRepository.value = ''; artifacts.value = []; artifactTotal.value = 0
  artifactError.value = ''; loadingArtifacts.value = false; artifactFilter.value = ''; artifactPage.value = 1
}
function resetRepositories() {
  gates.repositories.invalidate(); resetArtifacts()
  repositories.value = []; selectedProject.value = ''; repositoryTotal.value = 0
  repositoryError.value = ''; loadingRepositories.value = false; repositoryFilter.value = ''; repositoryPage.value = 1
}
async function loadStatus() {
  const ticket = gates.status.begin()
  gates.projects.invalidate(); resetRepositories(); projects.value = []; projectTotal.value = 0
  loadingProjects.value = false; loadingStatus.value = true; statusError.value = ''; projectError.value = ''; traceId.value = ''
  try {
    const status = dataOf(await http.get('/api/harbor/status'))
    if (!gates.status.current(ticket)) return
    configured.value = Boolean(status.configured)
    if (!configured.value) { connection.value = { state: 'UNCONFIGURED' }; return }
    try {
      const check = dataOf(await http.get('/api/harbor/connection-check'))
      if (!gates.status.current(ticket)) return
      connection.value = check
    } catch {
      if (!gates.status.current(ticket)) return
      connection.value = { state: 'FAILED' }
    }
    await loadProjects(1)
  } catch {
    if (gates.status.current(ticket)) { configured.value = false; connection.value = { state: 'FAILED' }; statusError.value = '无法读取配置状态，请检查登录状态或联系管理员。' }
  } finally { if (gates.status.current(ticket)) loadingStatus.value = false }
}
async function loadProjects(page = 1) {
  const ticket = gates.projects.begin()
  resetRepositories(); projects.value = []; loadingProjects.value = true; projectError.value = ''; traceId.value = ''
  try {
    const data = dataOf(await http.get('/api/harbor/projects', { params: { page } }))
    if (!gates.projects.current(ticket)) return
    projects.value = data.items; projectTotal.value = data.total; projectPage.value = data.page; projectPages.value = pages(data); traceId.value = data.traceId
  } catch {
    if (gates.projects.current(ticket)) { projectError.value = 'Harbor 不可达或读取权限不足，请重新检查连接。'; connection.value = { state: 'FAILED' } }
  } finally { if (gates.projects.current(ticket)) loadingProjects.value = false }
}
function selectProject(name) { resetRepositories(); selectedProject.value = name; loadRepositories(1) }
async function loadRepositories(page = 1) {
  const ticket = gates.repositories.begin(), project = selectedProject.value
  resetArtifacts(); repositories.value = []; loadingRepositories.value = true; repositoryError.value = ''; traceId.value = ''
  try {
    const data = dataOf(await http.get(`/api/harbor/projects/${encodeURIComponent(project)}/repositories`, { params: { page } }))
    if (!gates.repositories.current(ticket)) return
    repositories.value = data.items; repositoryTotal.value = data.total; repositoryPage.value = data.page; repositoryPages.value = pages(data); traceId.value = data.traceId
  } catch { if (gates.repositories.current(ticket)) repositoryError.value = '仓库读取失败，请检查项目权限后重试。' }
  finally { if (gates.repositories.current(ticket)) loadingRepositories.value = false }
}
function selectRepository(name) { resetArtifacts(); selectedRepository.value = name; loadArtifacts(1) }
async function loadArtifacts(page = 1) {
  const ticket = gates.artifacts.begin(), project = selectedProject.value
  const repository = repositoryWithinProject(project, selectedRepository.value)
  artifacts.value = []; artifactError.value = ''; traceId.value = ''
  if (!repository) { artifactError.value = '仓库路径不合法，未发送请求。'; return }
  loadingArtifacts.value = true
  try {
    const data = dataOf(await http.get(`/api/harbor/projects/${encodeURIComponent(project)}/artifacts`, { params: { repository, page } }))
    if (!gates.artifacts.current(ticket)) return
    artifacts.value = data.items; artifactTotal.value = data.total; artifactPage.value = data.page; artifactPages.value = pages(data); traceId.value = data.traceId
  } catch { if (gates.artifacts.current(ticket)) artifactError.value = '制品读取失败，请确认仓库权限或重试。' }
  finally { if (gates.artifacts.current(ticket)) loadingArtifacts.value = false }
}
let clock
onMounted(() => { loadStatus(); clock = setInterval(() => { now.value = Date.now() }, 15000) })
onUnmounted(() => { clearInterval(clock); Object.values(gates).forEach(gate => gate.invalidate()) })
</script>

<style scoped>
.harbor-browser{color:var(--smart-text);min-width:0}.harbor-head,.harbor-toolbar,.harbor-actions,.repository-head,.harbor-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.harbor-head p,.harbor-muted,.harbor-head small,.harbor-trace{color:var(--smart-muted);line-height:1.7}.harbor-head h3{margin:0;overflow-wrap:anywhere}.harbor-browser button,.harbor-browser input{min-height:44px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);border-radius:6px;padding:9px 12px;font:inherit}.harbor-browser button{cursor:pointer}.harbor-browser button:disabled{opacity:.55;cursor:not-allowed}.harbor-browser :is(button,input):focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:3px}.harbor-browser button[aria-pressed=true]{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 10%,var(--smart-surface))}.connection-status{display:grid;gap:7px;margin:18px 0;padding:16px;border:1px solid var(--smart-border-strong);background:var(--smart-surface)}.connection-status span,.connection-status small{color:var(--smart-muted)}.connection-status .readable{color:var(--smart-primary-strong)}.harbor-grid{display:grid;grid-template-columns:minmax(160px,1fr) minmax(0,3fr);gap:18px;margin-top:18px}.project-list{display:flex;flex-direction:column;gap:8px}.project-item{display:grid;text-align:left;gap:6px}.project-item small,.repository-row small{color:var(--smart-muted)}.repository-row{display:flex;width:100%;justify-content:space-between;gap:12px;text-align:left;margin:8px 0;overflow-wrap:anywhere}.repository-list{min-width:0}.harbor-pagination{justify-content:flex-end;margin:16px 0}.filter-label{display:grid;gap:7px;margin:14px 0;color:var(--smart-muted);font-size:13px}.filter-label input{width:100%;box-sizing:border-box}.artifact-panel{margin-top:24px;padding-top:20px;border-top:1px solid var(--smart-border-strong)}.artifact-card{display:grid;gap:10px;margin:12px 0;padding:16px;border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:8px;overflow-wrap:anywhere}.artifact-card code{font-size:12px;word-break:break-all}.artifact-card dl{display:flex;gap:24px;flex-wrap:wrap;margin:0}.artifact-card dt{color:var(--smart-muted);font-size:12px}.artifact-card dd{margin:5px 0 0;font-size:13px}.harbor-error{border-left:3px solid var(--smart-primary-strong);padding:12px;background:var(--smart-surface);color:var(--smart-text)}.harbor-empty{padding:20px;border:1px dashed var(--smart-border-strong)}.harbor-trace{display:block;overflow-wrap:anywhere}@media(max-width:640px){.harbor-grid{grid-template-columns:1fr}.repository-row{flex-direction:column}.harbor-head{align-items:flex-start}.harbor-actions{gap:6px}}
</style>
