<template>
  <section class="team-page" aria-labelledby="team-join-title">
    <RouterLink to="/teams">← 返回团队空间</RouterLink>
    <header class="team-heading"><div><p class="team-eyebrow">TEAM INVITE / ACCEPT</p><h1 id="team-join-title">加入团队</h1><p class="team-muted">邀请链接仅用于当前团队，不授予平台管理或个人资源访问权。</p></div></header>
    <p v-if="loading" role="status">正在读取邀请链接…</p>
    <p v-else-if="error" class="team-error" role="alert">{{ error }}</p>
    <section v-else-if="invite" class="team-panel">
      <h2>{{ invite.teamName }}</h2>
      <p class="team-muted">邀请人 {{ invite.creatorName }} · 授予角色 {{ TEAM_ROLE_LABELS[invite.role] }} · {{ new Date(invite.expiresAt).toLocaleString('zh-CN') }} 到期</p>
      <p v-if="invite.member" class="team-notice">你已经是该团队成员。<RouterLink :to="`/teams/${invite.teamId}`">进入团队</RouterLink></p>
      <p v-else-if="invite.teamStatus !== 'active'" class="team-notice">团队已被平台冻结，暂时无法加入。</p>
      <p v-else-if="!invite.valid" class="team-notice">该邀请链接已使用、撤销或过期，请联系团队管理员重新生成。</p>
      <button v-else type="button" class="primary" :disabled="busy" @click="accept">{{ busy ? '正在加入…' : '接受邀请并加入团队' }}</button>
    </section>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { teamInviteLinksApi } from '../../api/teams.ts'
import { TEAM_ROLE_LABELS } from '../../domain/team/permissions.ts'
import '../../assets/styles/team-workspace.css'
const route = useRoute(), router = useRouter()
const invite = ref(null), loading = ref(true), busy = ref(false), error = ref('')
const token = () => String(route.params.token || '')
onMounted(async () => {
  try { invite.value = await teamInviteLinksApi.preview(token()) }
  catch (failure) { error.value = failure.message || '邀请链接无效或已失效' }
  finally { loading.value = false }
})
async function accept() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const result = await teamInviteLinksApi.accept(token()); await router.push(`/teams/${result.teamId}`) }
  catch (failure) { error.value = failure.message || '加入团队失败'; await teamInviteLinksApi.preview(token()).then(value => { invite.value = value }).catch(() => {}) }
  finally { busy.value = false }
}
</script>
