<template>
  <section aria-labelledby="loginlog-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">SYSTEM / 安全审计</p><h1 id="loginlog-title">登录日志</h1></div></header>
    <p class="admin-muted">记录每一次登录成功与失败、来源 IP，用于异常登录排查。</p>
    <form class="admin-filters" @submit.prevent="search">
      <label>搜索账号<input v-model.trim="filters.q" type="search" placeholder="按账号子串搜索" maxlength="64"></label>
      <button type="submit" :disabled="loading">查询</button>
    </form>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载登录日志…</p>
    <div v-if="data" class="admin-table-wrap" tabindex="0" aria-label="登录日志列表">
      <table><thead><tr><th scope="col">账号</th><th scope="col">来源 IP</th><th scope="col">结果</th><th scope="col">说明</th><th scope="col">时间</th></tr></thead>
        <tbody><tr v-for="log in data.items" :key="log.id"><td>{{ log.username }}</td><td><code>{{ log.ip || '—' }}</code></td><td><span :class="log.status === 1 ? 'admin-badge' : 'admin-badge admin-badge--warn'">{{ log.status === 1 ? '成功' : '失败' }}</span></td><td>{{ log.message || '—' }}</td><td>{{ formatAdminTime(log.login_at) }}</td></tr></tbody>
      </table><p v-if="!data.items.length" class="admin-empty">没有匹配的登录记录。</p>
    </div>
    <AdminPagination :total="data?.total || 0" :page="query.page" :page-size="query.pageSize" :loading="loading || !!error" @page="changePage" @resize="resize" />
  </section>
</template>

<script setup>
import { reactive } from 'vue'
import { systemApi } from '../../../api/adminSystem.ts'
import { useAdminResource, formatAdminTime } from '../../../composables/useAdminResource.js'
import AdminPagination from '../../../components/admin/AdminPagination.vue'
const filters = reactive({ q: '' })
const query = reactive({ q: '', page: 1, pageSize: 20 })
const { data, loading, error, load } = useAdminResource(() => systemApi.loginLogs({ ...query }))
function search() { Object.assign(query, filters, { page: 1 }); load() }
function changePage(page) { query.page = page; load() }
function resize(pageSize) { query.pageSize = pageSize; changePage(1) }
</script>
