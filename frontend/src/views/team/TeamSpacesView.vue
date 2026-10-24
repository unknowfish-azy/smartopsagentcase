<template>
  <section class="team-page" aria-labelledby="teams-title">
    <header class="team-heading"><div><p class="team-eyebrow">TEAM WORKSPACES</p><h1 id="teams-title">团队空间</h1><p class="team-muted">独立的成员关系与权限。加入团队不会自动分享个人知识、会话、凭据或服务器。</p></div><button :disabled="busy || loading" @click="load">{{ loading ? '加载中…' : '刷新团队' }}</button></header>
    <p v-if="error" class="team-error" role="alert">{{ error }}</p><p v-if="message" class="team-success" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取团队与邀请…</p>
    <div class="team-grid">
      <div class="team-col team-col--primary">
        <section class="team-panel" aria-labelledby="my-teams"><h2 id="my-teams">我加入的团队 <span class="team-badge">{{ teams.total }}</span></h2>
          <p v-if="!loading && !teams.items.length" class="team-muted">还没有加入团队。可以创建团队，或请团队所有者邀请你的账号。</p>
          <article v-for="team in teams.items" :key="team.id" class="team-card"><div class="team-row"><h3><RouterLink :to="`/teams/${team.id}`">{{ team.name }}</RouterLink></h3><span class="team-badge">{{ team.status === 'frozen' ? '已冻结' : '正常' }}</span></div><p>{{ team.description || '暂无团队描述' }}</p><p class="team-muted">{{ TEAM_ROLE_LABELS[team.role] }} · {{ team.memberCount }} 名成员 · 所有者 {{ team.ownerName }}</p><RouterLink :to="`/teams/${team.id}/workspace`">进入协作</RouterLink></article>
          <div v-if="teams.total > 20" class="team-pagination"><button :disabled="loading || busy || teamPage === 1" @click="teamPage--; load()">上一页团队</button><span>{{ teamPage }} / {{ Math.ceil(teams.total / 20) }}</span><button :disabled="loading || busy || teamPage * 20 >= teams.total" @click="teamPage++; load()">下一页团队</button></div>
        </section>
        <section class="team-panel" aria-labelledby="team-inbox"><h2 id="team-inbox">待处理邀请 <span class="team-badge">{{ invitations.total }}</span></h2>
          <p v-if="!loading && !invitations.items.length" class="team-muted">暂无有效邀请。邀请七天过期，不会自动加入。</p>
          <article v-for="item in invitations.items" :key="item.id" class="team-card"><h3>{{ item.teamName }}</h3><p class="team-muted">邀请角色：{{ TEAM_ROLE_LABELS[item.role] }} · 到期 {{ date(item.expiresAt) }}</p><p v-if="item.teamStatus === 'frozen'">团队已冻结，暂时不能接受。</p><div class="team-actions"><button :disabled="busy || loading || item.teamStatus !== 'active'" @click="respond(item, true)">接受邀请</button><button :disabled="busy || loading" @click="respond(item, false)">拒绝邀请</button></div></article>
          <div v-if="invitations.total > 20" class="team-pagination"><button :disabled="loading || busy || invitePage === 1" @click="invitePage--; load()">上一页邀请</button><span>{{ invitePage }} / {{ Math.ceil(invitations.total / 20) }}</span><button :disabled="loading || busy || invitePage * 20 >= invitations.total" @click="invitePage++; load()">下一页邀请</button></div>
        </section>
      </div>
      <div class="team-col team-col--secondary"><section class="team-panel"><h2>创建团队</h2><form @submit.prevent="create"><fieldset :disabled="busy || loading" class="team-form"><label>团队名称<input v-model="form.name" required maxlength="80" autocomplete="off" /></label><label>团队描述<textarea v-model="form.description" maxlength="500" placeholder="说明团队用途，不要填写密码或密钥" /></label><p class="team-muted">你将成为团队所有者。每人最多创建 10 个团队，每队最多 100 名成员。</p><button class="primary" type="submit">{{ busy ? '处理中…' : '创建团队空间' }}</button></fieldset></form></section>
        <section class="team-panel"><h2>团队协作</h2><p>团队 Agent 草稿与版本、工具目录和成员协作记录。</p><p class="team-muted">个人空间的知识、连接和会话保持独立。</p></section></div>
    </div>
  </section>
</template>
<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { RouterLink, onBeforeRouteLeave, useRouter } from 'vue-router'
import { teamApi } from '../../api/teams.ts'
import { TEAM_ROLE_LABELS } from '../../domain/team/permissions.ts'
import '../../assets/styles/team-workspace.css'
const router = useRouter()
const teams = ref({ items: [], total: 0 }), invitations = ref({ items: [], total: 0 })
const teamPage = ref(1), invitePage = ref(1), loading = ref(false), busy = ref(false), error = ref(''), message = ref('')
const form = reactive({ name: '', description: '' })
let generation = 0, disposed = false
const date = value => new Date(value).toLocaleDateString('zh-CN')
async function load() {
  const current = ++generation; loading.value = true; error.value = ''
  try { const result = await Promise.all([teamApi.list({ page: teamPage.value, pageSize: 20 }), teamApi.invitations({ page: invitePage.value, pageSize: 20 })]); if (!disposed && current === generation) { teams.value = result[0]; invitations.value = result[1] } }
  catch (failure) { if (!disposed && current === generation) { error.value = failure.message || '团队暂时无法加载'; teams.value = { items: [], total: 0 }; invitations.value = { items: [], total: 0 } } }
  finally { if (!disposed && current === generation) loading.value = false }
}
async function create() {
  if (busy.value || loading.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { const team = await teamApi.create({ name: form.name.trim(), description: form.description }); if (!disposed) { busy.value = false; await router.push(`/teams/${team.id}`) } }
  catch (failure) { if (!disposed) error.value = failure.message || '创建失败，请重试' }
  finally { busy.value = false }
}
async function respond(item, accept) {
  if (busy.value || loading.value) return
  busy.value = true; message.value = ''; error.value = ''
  try { await teamApi.respond(item.id, accept); if (!disposed) { invitePage.value = 1; teamPage.value = 1; await load(); message.value = accept ? '已加入团队，个人资料未被分享。' : '已拒绝邀请。' } }
  catch (failure) { if (!disposed) { await load(); error.value = failure.message || '邀请处理失败' } }
  finally { busy.value = false }
}
onBeforeRouteLeave(() => !busy.value)
onBeforeUnmount(() => { disposed = true; generation++ })
onMounted(load)
</script>
