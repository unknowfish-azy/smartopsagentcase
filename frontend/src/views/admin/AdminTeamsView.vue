<template>
  <section class="team-page" aria-labelledby="admin-teams-title">
    <header class="team-heading"><div><p class="team-eyebrow">GOVERNANCE / TEAMS</p><h1 id="admin-teams-title">团队管理</h1><p class="team-muted">集中管理团队状态与成员元数据；不读取私人知识、会话或凭据。</p></div><button :disabled="loading || busy" @click="load">{{ loading ? '读取中…' : '刷新团队列表' }}</button></header>
    <p v-if="error" class="team-error" role="alert">{{ error }}</p><p v-if="message" class="team-success" role="status">{{ message }}</p>
    <form class="team-panel team-admin-filters" @submit.prevent="page = 1; load()"><label>搜索团队<input v-model="query" maxlength="80" placeholder="按团队名称搜索" :disabled="busy" /></label><label>状态<select v-model="status" :disabled="busy"><option value="">全部状态</option><option value="active">正常</option><option value="frozen">已冻结</option></select></label><button type="submit" :disabled="loading || busy">查询</button></form>
    <section class="team-panel" aria-label="团队清单"><h2>团队清单 <span class="team-badge">{{ result.total }}</span></h2><p v-if="!loading && !result.items.length" class="team-muted">没有匹配的团队。</p>
      <article v-for="team in result.items" :key="team.id" class="team-card"><div class="team-row"><div><h3>{{ team.name }}</h3><p class="team-muted">#{{ team.id }} · 所有者 {{ team.ownerName }} · {{ team.memberCount }} 名成员 · {{ team.status === 'frozen' ? '已冻结' : '正常' }}</p></div><div class="team-actions"><button :disabled="busy" @click="showMembers(team)">查看成员</button><button :disabled="busy" @click="prepare(team)">{{ team.status === 'frozen' ? '恢复团队' : '冻结团队' }}</button></div></div><p>{{ team.description || '暂无描述' }}</p></article>
      <div class="team-pagination"><button :disabled="busy || loading || page === 1" @click="page--; load()">上一页</button><span>{{ page }} / {{ Math.max(1, Math.ceil(result.total / 20)) }}</span><button :disabled="busy || loading || page * 20 >= result.total" @click="page++; load()">下一页</button></div>
    </section>
    <section v-if="selectedMembers" class="team-panel" aria-labelledby="team-members-title"><div class="team-row"><h2 id="team-members-title">{{ selectedMembers.name }} · 成员角色</h2><button @click="closeMembers">关闭成员列表</button></div><p v-if="memberLoading" role="status">正在读取成员…</p><p v-if="memberError" class="team-error" role="alert">{{ memberError }}</p><article v-for="member in members" :key="member.userId" class="team-member"><strong>{{ member.username }}</strong><span>{{ TEAM_ROLE_LABELS[member.role] }} · {{ member.enabled ? '账号启用' : '账号已禁用' }}</span></article></section>
    <section v-if="pending" ref="confirmationPanel" class="team-panel" aria-labelledby="team-confirm-title"><h2 id="team-confirm-title">确认{{ pending.status === 'frozen' ? '恢复' : '冻结' }}「{{ pending.name }}」</h2><p class="team-notice">{{ pending.status === 'frozen' ? '恢复后成员可继续修改团队和接受有效邀请。' : '冻结后禁止团队资料、成员和邀请变更；成员可查看基础信息或退出。不会冻结成员的个人账号。' }}</p><form @submit.prevent="commit"><fieldset :disabled="busy" class="team-form"><label>当前管理员密码<input ref="passwordInput" v-model="password" type="password" autocomplete="current-password" required maxlength="128" /></label><div class="team-actions"><button type="submit">{{ busy ? '提交中…' : '确认状态变更' }}</button><button type="button" @click="cancel">取消</button></div></fieldset></form></section>
  </section>
</template>
<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { adminTeamsApi } from '../../api/teams.js'
import { TEAM_ROLE_LABELS } from '../../domain/team/permissions.js'
import '../../assets/styles/team-workspace.css'
const query = ref(''), status = ref(''), page = ref(1), result = ref({ items: [], total: 0 })
const loading = ref(false), busy = ref(false), error = ref(''), message = ref(''), pending = ref(null), password = ref(''), passwordInput = ref(null), confirmationPanel = ref(null)
const selectedMembers = ref(null), members = ref([]), memberLoading = ref(false), memberError = ref('')
let disposed = false, generation = 0, memberGeneration = 0
async function load() {
  const current = ++generation; loading.value = true; error.value = ''
  try { const response = await adminTeamsApi.list({ q: query.value, status: status.value, page: page.value, pageSize: 20 }); if (!disposed && generation === current) result.value = response }
  catch (failure) { if (!disposed && generation === current) { error.value = failure.message || '团队列表加载失败'; result.value = { items: [], total: 0 } } }
  finally { if (!disposed && generation === current) loading.value = false }
}
function closeMembers() { memberGeneration++; selectedMembers.value = null; members.value = []; memberLoading.value = false }
async function showMembers(team) {
  const current = ++memberGeneration; selectedMembers.value = team; members.value = []; memberError.value = ''; memberLoading.value = true
  try { const response = await adminTeamsApi.members(team.id); if (!disposed && current === memberGeneration) members.value = response }
  catch (failure) { if (!disposed && current === memberGeneration) memberError.value = failure.message || '成员加载失败' }
  finally { if (!disposed && current === memberGeneration) memberLoading.value = false }
}
async function prepare(team) { pending.value = { ...team }; password.value = ''; message.value = ''; await nextTick(); confirmationPanel.value?.scrollIntoView({ block: 'center' }); passwordInput.value?.focus() }
function cancel() { password.value = ''; pending.value = null }
async function commit() {
  if (busy.value || !pending.value) return
  const target = pending.value, supplied = password.value; password.value = ''; busy.value = true; error.value = ''; message.value = ''
  try { await adminTeamsApi.setStatus(target.id, target.status === 'frozen' ? 'active' : 'frozen', supplied); if (!disposed) { cancel(); await load(); message.value = '团队状态已更新，变更已记录审计。' } }
  catch (failure) { if (!disposed) error.value = failure.message || '状态更新失败，请重新输入密码后重试' }
  finally { busy.value = false }
}
onBeforeRouteLeave(() => !busy.value)
onBeforeUnmount(() => { disposed = true; generation++; memberGeneration++; password.value = ''; members.value = [] })
onMounted(load)
</script>
<style scoped>
.team-admin-filters{display:flex;align-items:end;gap:16px;flex-wrap:wrap}.team-admin-filters label{display:grid;gap:6px;flex:1;min-width:140px}.team-page{padding:0;max-width:none}
/* 管理台团队页沿用 koi-ui 卡片语言；team-workspace.css 与用户层团队页共用，此处不做全局修改 */
.team-page .team-panel{border-radius:10px;box-shadow:0 2px 8px rgb(48 49 51 / 6%)}
.team-page .team-card{padding:16px 18px;border:1px solid var(--admin-border);border-radius:8px;margin-bottom:10px;background:var(--admin-surface-2)}
.team-page .team-card:first-of-type{border-top:1px solid var(--admin-border)}
.team-page .team-card:last-of-type{margin-bottom:0}
.team-page .team-card:hover{border-color:color-mix(in srgb,var(--admin-accent) 28%,var(--admin-border))}
.team-page .team-heading h1{padding-bottom:12px}
.team-page .team-badge{border-radius:999px;background:var(--admin-soft);color:var(--admin-accent-text);padding:2px 10px}
.team-page .team-admin-filters{padding:18px 20px;margin-bottom:20px;border-radius:10px;background:var(--admin-panel);box-shadow:0 2px 8px rgb(48 49 51 / 6%)}
.team-page .team-admin-filters label{color:var(--admin-muted);font-size:12px}
.team-page fieldset.team-form label{color:var(--admin-muted);font-size:12px}
:root[data-theme='dark'] .team-page .team-panel,:root[data-theme='dark'] .team-page .team-admin-filters{box-shadow:0 2px 8px rgb(0 0 0 / 28%)}
@media (prefers-reduced-motion: reduce){.team-page .team-card{transition:none}}
</style>
