<template>
  <section aria-labelledby="overview-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">GOVERNANCE / 管理概览</p><h1 id="overview-title">管理总览</h1></div><button :disabled="loading" @click="load">刷新统计</button></header>
    <p class="admin-muted">账户生命周期、活动会话与安全事件。统计来自当前服务，不代表外部系统连通性。</p>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载统计…</p>
    <div v-if="data" class="admin-stat-region"><h2 class="admin-section-title">关键指标</h2><div class="admin-stats"><dl v-for="metric in metrics" :key="metric.key" class="admin-stat"><dt>{{ metric.label }}</dt><dd>{{ data[metric.key] }}</dd></dl></div></div>
    <p class="admin-notice">禁用、角色变更或重置密码会撤销目标账户的旧会话及终端连接。最后一个启用管理员受服务端保护。</p>
    <section class="admin-entry-region" aria-labelledby="overview-entries-title"><h2 class="admin-section-title" id="overview-entries-title">管理快捷入口</h2><div class="admin-governance-grid"><RouterLink v-for="entry in entries" :key="entry.path" :to="entry.path"><strong>{{ entry.title }}</strong><span>{{ entry.description }}</span></RouterLink></div></section>
  </section>
</template>
<script setup>
import { onMounted } from 'vue'
import { adminApi } from '../../api/admin.js'
import { useAdminResource } from '../../composables/useAdminResource.js'
const { data, loading, error, load } = useAdminResource(adminApi.overview)
const metrics = [{ key: 'usersTotal', label: '账户总数' }, { key: 'usersEnabled', label: '启用账户' }, { key: 'adminsEnabled', label: '启用管理员' }, { key: 'activeSessions', label: '活动会话' }, { key: 'recentFailures', label: '近期登录失败' }, { key: 'pendingPasswordChanges', label: '待首次改密' }]
const entries = [
  { path: '/admin/teams', title: '团队与成员治理', description: '检索团队、核对成员角色、冻结或恢复团队；不读取私人资料。' },
  { path: '/admin/users', title: '账户与注册策略', description: '创建、停用和管理账号；团队角色与平台管理员权限独立。' },
  { path: '/admin/sessions', title: '活动会话处置', description: '查看当前登录会话，必要时撤销访问。' },
  { path: '/admin/audit', title: '安全与团队审计', description: '追踪登录、角色调整、成员移除和团队状态变更。' },
  { path: '/admin/security', title: '管理员二次认证', description: '管理当前账号的认证器与恢复码。' },
  { path: '/admin/readiness', title: '服务接入检查', description: '区分未配置、未知与可用状态，不将缺少数据视为正常。' }
]
onMounted(load)
</script>

<style scoped>
.admin-stat-region { display: grid; gap: 10px; margin: 22px 0 18px; }
.admin-stat-region > h2 { padding-bottom: 12px; }
.admin-stat-region .admin-stats { margin: 0; }
.admin-entry-region { display: grid; gap: 10px; margin-top: 22px; }
.admin-entry-region > h2 { padding-bottom: 12px; }
.admin-entry-region .admin-governance-grid { margin-top: 0; }
</style>
