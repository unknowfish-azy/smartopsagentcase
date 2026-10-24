<template>
  <section class="team-page" aria-labelledby="team-detail-title">
    <RouterLink to="/teams">← 返回团队空间</RouterLink>
    <header class="team-heading"><div><p class="team-eyebrow">TEAM / MEMBERS & ACCESS</p><h1 id="team-detail-title">{{ detail?.team.name || '团队工作台' }}</h1><p class="team-muted">成员权限只在当前团队生效，不授予平台管理或个人资源访问权。</p></div><RouterLink class="team-button" :to="`/teams/${teamId}/workspace`">进入协作</RouterLink><button :disabled="busy || loading" @click="load">{{ loading ? '加载中…' : '刷新团队详情' }}</button></header>
    <p v-if="error" class="team-error" role="alert">{{ error }}</p><p v-if="message" class="team-success" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取成员与授权…</p>
    <template v-if="detail">
      <p v-if="frozen" class="team-notice">团队已被平台冻结。可查看基础信息，暂不能修改或接受邀请；非所有者仍可退出。</p>
      <div class="team-grid"><div class="team-col team-col--primary">
        <section class="team-panel"><div class="team-row"><h2>团队成员 · {{ detail.members.length }}</h2><span class="team-badge">我的角色：{{ TEAM_ROLE_LABELS[detail.team.role] }}</span></div>
          <article v-for="member in detail.members" :key="member.userId" class="team-member"><div><strong>{{ member.username }}</strong><p class="team-muted">{{ TEAM_ROLE_LABELS[member.role] }}{{ member.enabled ? '' : ' · 账号已禁用' }}{{ member.userId === currentSession?.id ? ' · 我' : '' }}</p></div>
            <div v-if="canManageMember(detail.team.role, member.role, member.userId === currentSession?.id) && !frozen" class="team-member-controls"><select v-model="roleDraft[member.userId]" :aria-label="`${member.username} 的团队角色`" :disabled="busy || loading"><option v-for="role in roles" :key="role" :value="role">{{ TEAM_ROLE_LABELS[role] }}</option></select><button :disabled="busy || loading || roleDraft[member.userId] === member.role" @click="changeRole(member)">保存角色</button><button class="danger" :disabled="busy || loading" @click="remove(member)">移除成员</button></div>
          </article>
          <button v-if="detail.team.role !== 'owner'" class="danger" :disabled="busy || loading" @click="leave">退出当前团队</button>
        </section>
        <section v-if="manager" class="team-panel"><h2>发出的邀请</h2><p v-if="!detail.invitations.length" class="team-muted">暂无待处理邀请。角色变更或移除邀请人时，其未接受的邀请会被撤销。</p><article v-for="item in detail.invitations" :key="item.id" class="team-member"><div><strong>{{ item.username }}</strong><p class="team-muted">{{ TEAM_ROLE_LABELS[item.role] }} · {{ new Date(item.expiresAt).toLocaleDateString('zh-CN') }} 到期</p></div><button v-if="roles.includes(item.role)" :disabled="busy || loading || frozen" @click="mutate(() => teamApi.cancelInvite(teamId, item.id), '邀请已撤销。')">撤销邀请</button></article></section>
      </div><div class="team-col team-col--secondary">
        <section class="team-panel"><h2>团队资料</h2><form v-if="manager && !frozen" @submit.prevent="mutate(() => teamApi.update(teamId, { ...settings }), '团队资料已更新。')"><fieldset :disabled="busy || loading" class="team-form"><label>团队名称<input v-model="settings.name" required maxlength="80" /></label><label>团队描述<textarea v-model="settings.description" maxlength="500" /></label><button type="submit">保存团队资料</button></fieldset></form><p v-else>{{ detail.team.description || '暂无描述' }}</p><p class="team-muted">所有者 {{ detail.team.ownerName }} · {{ frozen ? '已冻结' : '正常' }}</p></section>
        <section v-if="manager && !frozen" class="team-panel"><h2>邀请成员</h2><form @submit.prevent="invite"><fieldset :disabled="busy || loading" class="team-form"><label>已有账号的用户名<input v-model="invitation.username" required maxlength="64" autocomplete="off" /></label><label>授予角色<select v-model="invitation.role"><option v-for="role in roles" :key="role" :value="role">{{ TEAM_ROLE_LABELS[role] }}</option></select></label><p class="team-muted">对方在团队空间接受后才会加入，邀请七天有效。团队管理员不能授予管理员角色。</p><button type="submit" class="primary">发送站内邀请</button></fieldset></form></section>
        <section class="team-panel"><h2>协作工作台</h2><p class="team-muted">共享 Agent 草稿与发布、工具目录和团队会话已经单独归属当前团队。服务器授权和协作执行仍以服务端权限为准。</p><RouterLink :to="`/teams/${teamId}/workspace`">进入协作工作台</RouterLink></section>
        <section class="team-panel"><div class="team-row"><h2>团队通知</h2><button :disabled="notificationLoading" @click="loadNotifications">刷新通知</button></div><p v-if="notificationError" class="team-error" role="alert">{{ notificationError }}</p><p v-else-if="!notifications.length" class="team-muted">暂无未读通知。</p><article v-for="item in notifications" :key="item.id" class="team-member"><div><strong>{{ item.message }}</strong><p class="team-muted">{{ new Date(item.createdAt).toLocaleString('zh-CN') }}</p></div><button :disabled="notificationLoading" @click="markNotificationRead(item)">标记已读</button></article></section>
        <section class="team-panel"><div class="team-row"><h2>团队活动</h2><button :disabled="activityLoading" @click="loadActivity">{{ activityLoading ? '读取中…' : '刷新记录' }}</button></div><p v-if="activityError" class="team-error" role="alert">{{ activityError }}</p><p v-else-if="!activities.length" class="team-muted">暂无活动记录。</p><article v-for="item in activities" :key="item.id" class="team-member"><div><strong>{{ item.action }}</strong><p class="team-muted">{{ item.actorUsername }} · {{ new Date(item.createdAt).toLocaleString('zh-CN') }}<span v-if="item.targetId"> · {{ item.targetId }}</span></p></div></article></section>
      </div></div>
    </template>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { RouterLink, onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { currentSession } from '../../security/session.js'
import { teamApi, teamNotificationsApi } from '../../api/teams.ts'
import { TEAM_ROLE_LABELS, assignableRoles, canManageMember, isTeamManager } from '../../domain/team/permissions.ts'
import '../../assets/styles/team-workspace.css'
const route = useRoute(), router = useRouter()
const teamId = computed(() => route.params.teamId)
const detail = ref(null), busy = ref(false), loading = ref(false), error = ref(''), message = ref('')
const activities = ref([]), activityLoading = ref(false), activityError = ref('')
const notifications = ref([]), notificationLoading = ref(false), notificationError = ref('')
const settings = reactive({ name: '', description: '' }), invitation = reactive({ username: '', role: 'member' }), roleDraft = ref({})
const manager = computed(() => isTeamManager(detail.value?.team.role)), frozen = computed(() => detail.value?.team.status === 'frozen'), roles = computed(() => assignableRoles(detail.value?.team.role))
let generation = 0, disposed = false
async function load() {
  const current = ++generation; loading.value = true; error.value = ''; detail.value = null
  try { const result = await teamApi.detail(teamId.value); if (!disposed && current === generation) { detail.value = result; Object.assign(settings, { name: result.team.name, description: result.team.description }); roleDraft.value = Object.fromEntries(result.members.map(member => [member.userId, member.role])); await Promise.all([loadActivity(), loadNotifications()]) } }
  catch (failure) { if (!disposed && current === generation) error.value = failure.message || '团队不存在或无权访问' }
  finally { if (!disposed && current === generation) loading.value = false }
}
async function loadActivity() { activityLoading.value = true; activityError.value = ''; try { activities.value = await teamApi.activity(teamId.value, { limit: 30 }) } catch (failure) { activityError.value = failure.message || '活动记录加载失败' } finally { activityLoading.value = false } }
async function loadNotifications() { notificationLoading.value = true; notificationError.value = ''; try { notifications.value = await teamNotificationsApi.list(true) } catch (failure) { notificationError.value = failure.message || '通知加载失败' } finally { notificationLoading.value = false } }
async function markNotificationRead(item) { notificationLoading.value = true; try { await teamNotificationsApi.markRead(item.id); notifications.value = notifications.value.filter(entry => entry.id !== item.id) } catch (failure) { notificationError.value = failure.message || '通知更新失败' } finally { notificationLoading.value = false } }
async function mutate(operation, success) {
  if (busy.value || loading.value) return false
  busy.value = true; error.value = ''; message.value = ''
  try { await operation(); if (!disposed) { await load(); message.value = success } return true }
  catch (failure) { if (!disposed) { await load(); error.value = failure.message || '操作失败，请刷新权限后重试' } return false }
  finally { busy.value = false }
}
async function invite() { if (await mutate(() => teamApi.invite(teamId.value, { username: invitation.username.trim(), role: invitation.role }), '邀请已发送，等待对方接受。')) invitation.username = '' }
async function changeRole(member) { if (window.confirm(`确认将 ${member.username} 调整为${TEAM_ROLE_LABELS[roleDraft.value[member.userId]]}？该成员发出的待处理邀请将撤销。`)) await mutate(() => teamApi.changeRole(teamId.value, member.userId, roleDraft.value[member.userId]), '成员角色已更新。') }
async function remove(member) { if (window.confirm(`确认移除 ${member.username}？其团队访问权立即失效。`)) await mutate(() => teamApi.removeMember(teamId.value, member.userId), '成员已移除。') }
async function leave() {
  if (busy.value || loading.value || !window.confirm('确认退出当前团队？再次加入需要新的邀请。')) return
  busy.value = true; error.value = ''
  try { await teamApi.removeMember(teamId.value, currentSession.value.id); busy.value = false; if (!disposed) await router.push('/teams') }
  catch (failure) { if (!disposed) error.value = failure.message || '退出失败' }
  finally { busy.value = false }
}
onBeforeRouteLeave(() => !busy.value)
onBeforeRouteUpdate(() => !busy.value)
onBeforeUnmount(() => { disposed = true; generation++ })
watch(teamId, () => { message.value = ''; invitation.username = ''; load() }, { immediate: true })
</script>
