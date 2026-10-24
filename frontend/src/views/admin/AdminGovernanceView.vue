<template>
  <section class="admin-governance" aria-labelledby="governance-title">
    <header class="admin-page-header"><div><p class="admin-eyebrow">GOVERNANCE / PLATFORM ADMINS</p><h1 id="governance-title">管理员与授权</h1><p class="admin-muted">平台身份与团队职务分离；当前页面只展示授权，不显示密钥或私人资源。</p></div><button @click="load" :disabled="loading">{{ loading ? '读取中…' : '刷新' }}</button></header>
    <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
    <form class="admin-filters" @submit.prevent="appoint"><label>目标管理员账号 ID<input v-model.number="form.id" type="number" min="1" required></label><label>级别<select v-model="form.level"><option value="deputy">副管理员</option><option value="specialist">专项管理员</option></select></label><label>平台能力（逗号分隔）<input v-model="form.capabilities" placeholder="teams.view,teams.audit"></label><label>当前管理员密码<input v-model="form.password" type="password" required autocomplete="current-password"></label><button type="submit" :disabled="loading">任命或更新</button></form>
    <div class="admin-table-wrap" v-if="items.length"><table><thead><tr><th>账号</th><th>级别</th><th>状态</th><th>平台能力</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>{{ item.username }}</td><td><span class="admin-badge">{{ labels[item.level] || item.level }}</span></td><td>{{ item.enabled ? '启用' : '禁用' }}</td><td><span v-if="!item.capabilities.length" class="admin-muted">未授予专项能力</span><span v-else>{{ item.capabilities.join(' · ') }}</span></td><td><button v-if="item.level !== 'root'" @click="selected = item">撤销管理员</button></td></tr></tbody></table></div>
    <form v-if="selected" class="admin-filters" @submit.prevent="revoke"><strong>撤销 {{ selected.username }}</strong><label>当前管理员密码<input v-model="revokePassword" type="password" required autocomplete="current-password"></label><button type="submit" :disabled="loading">确认撤销</button><button type="button" @click="selected = null">取消</button></form>
    <p v-else-if="!loading" class="admin-muted">暂无管理员授权资料。</p>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { adminApi } from '../../api/admin.js'
const labels = { root: '最高管理员', deputy: '副管理员', specialist: '专项管理员' }
const items = ref([]), loading = ref(false), error = ref(''), form = ref({ id: '', level: 'deputy', capabilities: '', password: '' }), selected = ref(null), revokePassword = ref('')
async function load() { loading.value = true; error.value = ''; try { items.value = await adminApi.governance() } catch (failure) { error.value = failure.message || '管理员授权加载失败' } finally { loading.value = false } }
onMounted(load)
async function appoint() { const value = form.value; loading.value = true; error.value = ''; try { await adminApi.appointAdmin(value.id, { level: value.level, capabilities: value.capabilities.split(',').map(item => item.trim()).filter(Boolean) }, value.password); value.password = ''; await load() } catch (failure) { error.value = failure.message || '管理员任命失败' } finally { loading.value = false } }
async function revoke() { if (!selected.value) return; loading.value = true; error.value = ''; try { await adminApi.revokeAdmin(selected.value.id, revokePassword.value); selected.value = null; revokePassword.value = ''; await load() } catch (failure) { error.value = failure.message || '管理员撤销失败' } finally { loading.value = false } }
</script>
