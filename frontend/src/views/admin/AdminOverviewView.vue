<template>
  <section aria-labelledby="overview-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">GOVERNANCE / 管理概览</p><h1 id="overview-title">管理总览</h1></div><button :disabled="loading || refreshing" @click="refreshAll">{{ refreshing ? '刷新中…' : '刷新统计' }}</button></header>
    <p class="admin-muted">账户生命周期、活动会话与安全事件。统计来自当前服务，不代表外部系统连通性。</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载统计…</p>
    <section class="admin-todo-region" aria-labelledby="overview-todo-title">
      <div class="admin-todo-heading">
        <h2 id="overview-todo-title" class="admin-section-title">待办与风险</h2>
        <p v-if="workbenchUpdatedAt && !workbenchLoading" class="admin-muted">来源：服务端聚合 · 最近读取 {{ formatAdminTime(workbenchUpdatedAt) }}</p>
      </div>
      <p v-if="workbenchLoading" role="status">正在加载治理待办…</p>
      <AdminErrorState v-else-if="workbenchError" :message="workbenchError" :busy="workbenchLoading" @retry="loadWorkbench()" />
      <ol v-else-if="workbench?.items?.length" class="admin-todo-list">
        <li v-for="item in workbench.items" :key="item.type">
          <div>
            <strong>{{ item.label }}</strong><span class="admin-todo-count">{{ item.count }}</span>
            <p>{{ item.detail }}</p>
            <p class="admin-muted">来源：{{ item.source }} · 观测时间：{{ formatAdminTime(item.observedAt) }}</p>
            <p v-if="item.samples?.length" class="admin-muted">示例：<span v-for="(sample, index) in item.samples" :key="index">{{ sample.teamName ? (sample.teamName + ' #' + sample.runId) : sample.table }}<span v-if="index < item.samples.length - 1">、</span></span></p>
          </div>
          <RouterLink :to="item.link">前往处理</RouterLink>
        </li>
      </ol>
      <p v-else class="admin-empty">当前没有需要你处理的治理事项（已按你的平台能力与团队批准资格过滤）。</p>
    </section>
    <div v-if="data" class="admin-stat-region"><h2 class="admin-section-title">关键指标</h2><div class="admin-stats"><dl v-for="metric in metrics" :key="metric.key" class="admin-stat"><dt>{{ metric.label }}</dt><dd>{{ data[metric.key] }}</dd></dl></div><p class="admin-muted">口径：当前数据库的账户与会话统计，读取于 {{ formatAdminTime(updatedAt) }}；不含外部系统连通性。</p></div>
    <p class="admin-notice">禁用、角色变更或重置密码会撤销目标账户的旧会话及终端连接。最后一个启用管理员受服务端保护。</p>
    <section class="admin-entry-region" aria-labelledby="overview-entries-title"><h2 class="admin-section-title" id="overview-entries-title">管理快捷入口</h2><div class="admin-governance-grid"><RouterLink v-for="entry in entries" :key="entry.path" :to="entry.path"><strong>{{ entry.title }}</strong><span>{{ entry.description }}</span></RouterLink></div></section>
  </section>
</template>
<script setup>
import { onMounted } from 'vue'
import { adminApi } from '../../api/admin.ts'
import AdminErrorState from '../../components/admin/AdminErrorState.vue'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'
const { data, loading, refreshing, error, updatedAt, load } = useAdminResource(adminApi.overview)
// 待办聚合逐项按能力过滤；没有对应能力的项不会返回，因此这里不展示任何伪造的 0 值统计。
const { data: workbench, loading: workbenchLoading, error: workbenchError, updatedAt: workbenchUpdatedAt, load: loadWorkbench } = useAdminResource(adminApi.workbench)
const metrics = [{ key: 'usersTotal', label: '账户总数' }, { key: 'usersEnabled', label: '启用账户' }, { key: 'adminsEnabled', label: '启用管理员' }, { key: 'activeSessions', label: '活动会话' }, { key: 'recentFailures', label: '近期登录失败' }, { key: 'pendingPasswordChanges', label: '待首次改密' }]
const entries = [
  { path: '/admin/teams', title: '团队与成员治理', description: '检索团队、核对成员角色、冻结或恢复团队；不读取私人资料。' },
  { path: '/admin/users', title: '账户与注册策略', description: '创建、停用和管理账号；团队角色与平台管理员权限独立。' },
  { path: '/admin/sessions', title: '活动会话处置', description: '查看当前登录会话，必要时撤销访问。' },
  { path: '/admin/audit', title: '安全与团队审计', description: '追踪登录、角色调整、成员移除和团队状态变更。' },
  { path: '/admin/security', title: '管理员二次认证', description: '管理当前账号的认证器与恢复码。' },
  { path: '/admin/readiness', title: '服务接入检查', description: '区分未配置、未知与可用状态，不将缺少数据视为正常。' }
]
onMounted(() => { load(); loadWorkbench() })
function refreshAll() {
  load({ preserve: true })
  loadWorkbench({ preserve: true })
}
</script>

<style scoped>
.admin-todo-region { display: grid; gap: 10px; margin: 18px 0 20px; }
.admin-todo-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.admin-todo-heading .admin-section-title { padding-bottom: 12px; }
.admin-todo-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.admin-todo-list li { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius-sm); background: var(--admin-surface-2); }
.admin-todo-list li p { margin: 4px 0 0; }
.admin-todo-count { margin-left: 8px; padding: 1px 8px; border-radius: 999px; background: var(--admin-soft); color: var(--admin-accent-text); font-variant-numeric: tabular-nums; }
.admin-todo-list li > a { flex: 0 0 auto; align-self: center; }
.admin-stat-region { display: grid; gap: 10px; margin: 22px 0 18px; }
.admin-stat-region > h2 { padding-bottom: 12px; }
.admin-stat-region .admin-stats { margin: 0; }
.admin-entry-region { display: grid; gap: 10px; margin-top: 22px; }
.admin-entry-region > h2 { padding-bottom: 12px; }
.admin-entry-region .admin-governance-grid { margin-top: 0; }
@media (max-width: 640px) { .admin-todo-list li { flex-direction: column; } }
</style>
