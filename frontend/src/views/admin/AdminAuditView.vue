<template>
  <section aria-labelledby="audit-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">AUDIT / 安全元数据</p><h1 id="audit-title">审计记录</h1></div><button type="button" :disabled="loading || refreshing" @click="load({ preserve: true })">{{ refreshing ? '刷新中…' : '刷新' }}</button></header>
    <p class="admin-muted">仅展示操作元数据，不包含请求正文、密码或认证令牌。审计记录不可删除；结果与审批依据分列展示。</p>
    <AdminFilterBar :loading="loading || refreshing" @search="search" @reset="reset">
      <label>搜索审计账号<input v-model.trim="filters.q" type="search" maxlength="64" placeholder="按账号子串搜索"></label>
      <label>审计动作<select v-model="filters.action"><option value="">全部动作</option><option v-for="item in AUDIT_ACTIONS" :key="item.value" :value="item.value">{{ item.label }} · {{ item.value }}</option></select></label>
      <label>审计结果<select v-model="filters.outcome"><option value="">全部结果</option><option v-for="item in AUDIT_OUTCOMES" :key="item.value" :value="item.value">{{ item.label }} · {{ item.value }}</option></select></label>
      <label>目标标识<input v-model.trim="filters.target" type="search" maxlength="64" placeholder="精确匹配 target_id"></label>
      <label>起始日期<input v-model="filters.from" type="date"></label>
      <label>结束日期<input v-model="filters.to" type="date" :min="filters.from || undefined"></label>
    </AdminFilterBar>
    <p v-if="refreshing" class="admin-muted admin-refresh-hint" role="status">正在刷新审计记录…</p>
    <p v-else-if="updatedAt" class="admin-muted admin-refresh-hint">最近更新：{{ formatAdminTime(updatedAt) }} · 共 {{ data?.total ?? 0 }} 条匹配记录</p>
    <AdminErrorState :message="error" :busy="loading || refreshing" @retry="load()" />
    <p v-if="loading" role="status">正在加载审计…</p>
    <p v-if="data" id="audit-scroll-hint" class="admin-table-hint">左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="审计列表，可横向滚动" aria-describedby="audit-scroll-hint">
      <table><thead><tr><th scope="col">时间</th><th scope="col">操作者</th><th scope="col">动作</th><th scope="col">目标 ID</th><th scope="col">结果</th><th scope="col">操作</th></tr></thead>
        <tbody><tr v-for="event in data.items" :key="event.id"><td>{{ formatAdminTime(event.createdAt) }}</td><td>{{ event.actorUsername || '—' }}</td><td><span>{{ actionLabel(event.action) }}</span><span v-if="actionLabel(event.action) !== event.action" class="admin-muted admin-raw">{{ event.action }}</span></td><td>{{ event.targetId ?? '—' }}</td><td><span class="admin-status" :class="outcomeTone(event.outcome)">{{ outcomeLabel(event.outcome) }}</span></td><td><div class="admin-actions"><button type="button" @click="openDetail(event)">详情</button></div></td></tr></tbody>
      </table><p v-if="!data.items.length" class="admin-empty">{{ hasFilters ? '没有匹配的审计记录，请调整筛选条件。' : '当前时间范围内还没有审计记录。' }}</p>
    </div>
    <AdminPagination :total="data?.total || 0" :page="query.page" :page-size="query.pageSize" :loading="loading || refreshing" @page="changePage" @resize="resize" />
    <AdminDialog v-if="detailOpen" title="审计详情" @close="closeDetail">
      <p v-if="detailLoading" role="status">正在加载审计详情…</p>
      <AdminErrorState v-else-if="detailError" :message="detailError" @retry="loadDetail" />
      <template v-else-if="detail">
        <dl class="audit-detail-grid">
          <dt>记录编号</dt><dd>{{ detail.id }}</dd>
          <dt>时间</dt><dd>{{ formatAdminTime(detail.createdAt) }}</dd>
          <dt>操作者</dt><dd>{{ detail.actorUsername || '—' }}<span class="admin-muted"> · ID {{ detail.actorId ?? '—' }}</span></dd>
          <dt>动作</dt><dd>{{ actionLabel(detail.action) }}<span class="admin-muted"> · {{ detail.action }}</span></dd>
          <dt>目标标识</dt><dd>{{ detail.targetId || '—' }}</dd>
          <dt>结果</dt><dd><span class="admin-status" :class="outcomeTone(detail.outcome)">{{ outcomeLabel(detail.outcome) }}</span></dd>
          <dt>审批依据 / 上下文</dt><dd>{{ detail.detail || '未记录' }}</dd>
          <dt>来源地址</dt><dd>{{ detail.ip || '未记录' }}</dd>
        </dl>
        <p class="admin-muted">审计记录只读，不包含请求正文、密码或认证令牌。受控导出需要单独授权并冻结保留策略，本轮不提供。</p>
      </template>
      <footer><button type="button" @click="closeDetail">关闭</button></footer>
    </AdminDialog>
  </section>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminApi, AUDIT_ACTIONS, AUDIT_OUTCOMES } from '../../api/admin.ts'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
import AdminDialog from '../../components/admin/AdminDialog.vue'
import AdminErrorState from '../../components/admin/AdminErrorState.vue'
import AdminFilterBar from '../../components/admin/AdminFilterBar.vue'
import AdminPagination from '../../components/admin/AdminPagination.vue'
const route = useRoute()
const router = useRouter()
const FILTER_KEYS = ['q', 'action', 'outcome', 'target', 'from', 'to']
const filters = reactive({ q: '', action: '', outcome: '', target: '', from: '', to: '' })
const query = reactive({ ...filters, page: 1, pageSize: 20 })
const { data, loading, refreshing, error, updatedAt, load } = useAdminResource(() => adminApi.audit({ ...query }))
const hasFilters = computed(() => FILTER_KEYS.some(key => filters[key]))
const actionLabel = value => AUDIT_ACTIONS.find(item => item.value === value)?.label || value
const outcomeLabel = value => AUDIT_OUTCOMES.find(item => item.value === value)?.label || value
const outcomeTone = value => value === 'SUCCESS' ? 'admin-status--success' : value === 'DENIED' ? 'admin-status--warning' : value === 'FAILURE' ? 'admin-status--danger' : 'admin-status--muted'
// 详情与列表走同一作用域；审计只读，详情只补充已脱敏的元数据。
const detailOpen = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
let detailId = 0
function openDetail(event) { detailId = event.id; detailOpen.value = true; detail.value = null; loadDetail() }
async function loadDetail() {
  detailLoading.value = true
  detailError.value = ''
  try { detail.value = await adminApi.auditDetail(detailId) }
  catch (failure) { detailError.value = failure.message || '审计详情加载失败' }
  finally { detailLoading.value = false }
}
function closeDetail() { detailOpen.value = false; detail.value = null; detailError.value = '' }

// 非秘密筛选条件进 URL；从详情或账号页跳回时保留同一查询。
function readQuery() {
  for (const key of FILTER_KEYS) {
    const value = route.query[key]
    if (typeof value === 'string') filters[key] = value
  }
  const page = Number(route.query.page)
  if (Number.isInteger(page) && page > 0) query.page = page
  Object.assign(query, filters)
}
function syncQuery() {
  const next = {}
  for (const key of FILTER_KEYS) if (filters[key]) next[key] = filters[key]
  if (query.page > 1) next.page = String(query.page)
  router.replace({ query: next })
}
function search() { Object.assign(query, filters, { page: 1 }); syncQuery(); load() }
function reset() { Object.assign(filters, { q: '', action: '', outcome: '', target: '', from: '', to: '' }); search() }
function changePage(page) { query.page = page; syncQuery(); load() }
function resize(pageSize) { query.pageSize = pageSize; changePage(1) }
onMounted(() => { readQuery(); load() })
</script>

<style scoped>
.admin-refresh-hint { margin: 6px 0 12px; font-size: 13px; }
.admin-raw { margin-left: 6px; font-size: 12px; }
.audit-detail-grid { display: grid; grid-template-columns: minmax(96px, 130px) 1fr; gap: 8px 14px; margin: 0 0 12px; }
.audit-detail-grid dt { color: var(--admin-muted); font-size: 13px; }
.audit-detail-grid dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
</style>
