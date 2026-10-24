<template>
  <section aria-labelledby="audit-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">AUDIT / 安全元数据</p><h1 id="audit-title">审计记录</h1></div></header>
    <p class="admin-muted">仅展示操作元数据，不包含请求正文、密码或认证令牌。审计记录不可删除。</p>
    <form class="admin-filters" @submit.prevent="search">
      <label>搜索审计账号<input v-model.trim="filters.q" type="search" maxlength="64" placeholder="按账号子串搜索"></label>
      <label>审计动作<select v-model="filters.action"><option value="">全部动作</option><option v-for="item in AUDIT_ACTIONS" :key="item.value" :value="item.value">{{ item.label }} · {{ item.value }}</option></select></label>
      <label>审计结果<select v-model="filters.outcome"><option value="">全部结果</option><option v-for="item in AUDIT_OUTCOMES" :key="item.value" :value="item.value">{{ item.label }} · {{ item.value }}</option></select></label>
      <button type="submit" :disabled="loading">查询</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p><p v-if="loading" role="status">正在加载审计…</p>
    <p v-if="data" id="audit-scroll-hint" class="admin-table-hint">左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="审计列表，可横向滚动" aria-describedby="audit-scroll-hint"><table><thead><tr><th scope="col">时间</th><th scope="col">操作者</th><th scope="col">动作</th><th scope="col">目标 ID</th><th scope="col">结果</th></tr></thead><tbody><tr v-for="event in data.items" :key="event.id"><td>{{ formatAdminTime(event.createdAt) }}</td><td>{{ event.actorUsername || '—' }}</td><td>{{ event.action }}</td><td>{{ event.targetId ?? '—' }}</td><td>{{ event.outcome }}</td></tr></tbody></table><p v-if="!data.items.length" class="admin-empty">没有匹配的审计记录。</p></div>
    <AdminPagination :total="data?.total || 0" :page="query.page" :page-size="query.pageSize" :loading="loading || !!error" @page="changePage" @resize="resize" />
  </section>
</template>
<script setup>
import { onMounted, reactive } from 'vue'
import { adminApi, AUDIT_ACTIONS, AUDIT_OUTCOMES } from '../../api/admin.ts'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
import AdminPagination from '../../components/admin/AdminPagination.vue'
const filters = reactive({ q: '', action: '', outcome: '' })
const query = reactive({ ...filters, page: 1, pageSize: 20 })
const { data, loading, error, load } = useAdminResource(() => adminApi.audit({ ...query }))
function search() { Object.assign(query, filters, { page: 1 }); load() }
function changePage(page) { query.page = page; load() }
function resize(pageSize) { query.pageSize = pageSize; changePage(1) }
onMounted(load)
</script>
