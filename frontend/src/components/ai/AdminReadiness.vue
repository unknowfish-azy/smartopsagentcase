<template>
  <section class="readiness" aria-labelledby="readiness-title">
    <header><h2 id="readiness-title">服务接入与安全检查</h2><button type="button" :disabled="loading" @click="load">{{ loading ? '检查中…' : '重新检查' }}</button></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <dl v-if="status">
      <div><dt>数据库关键表</dt><dd>{{ status.unavailableTables.length ? `不可用：${status.unavailableTables.join('、')}` : '检查通过' }}</dd></div>
      <div><dt>用户认证</dt><dd>服务端会话 · CSRF 校验 · 管理角色校验</dd></div>
      <div><dt>服务间认证</dt><dd>{{ status.internalAuthenticationConfigured ? '已配置；内部调用仍需携带有效凭据' : '未配置；内部接口拒绝访问，不影响已登录用户聊天入口' }}</dd></div>
      <div v-for="source in status.observability" :key="source.id"><dt>{{ source.id }}</dt><dd>{{ source.configured ? '已配置，数据查询时验证连通性' : '未配置数据源' }}</dd></div>
      <div><dt>Harbor</dt><dd>{{ status.harbor.configured ? '已配置，项目读取时验证连通性与权限' : '未配置镜像仓库' }}</dd></div>
      <div><dt>SSH / SFTP</dt><dd>未自动探测目标；请在连接中心显式建立测试连接。</dd></div>
    </dl>
    <p>此页面区分配置状态与真实连通性，不自动调用模型、不执行远程命令。公网部署还需要 HTTPS、安全 Cookie 与独立的部署安全检查。</p>
    <nav><RouterLink to="/model-settings">模型接入</RouterLink><RouterLink to="/connections">连接中心</RouterLink><RouterLink to="/tools/prometheus-query">指标查询</RouterLink><RouterLink to="/tools/harbor-browser">仓库浏览</RouterLink></nav>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import request from '../../utils/request.ts'
const status = ref(null)
const loading = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  status.value = null
  try { status.value = (await request.get('/api/admin/readiness')).data } catch (failure) { error.value = failure.message } finally { loading.value = false }
}
onMounted(load)
</script>

<style scoped>
.readiness { margin-top: 24px; padding: 24px; border: 1px solid var(--smart-border-strong); border-radius: 12px; color: var(--smart-text); background: var(--smart-surface); }
header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; } h2 { margin: 0; font-size: 20px; } button { min-height: 44px; border: 1px solid var(--smart-border); border-radius: 7px; padding: 8px 12px; color: var(--smart-text); background: var(--smart-bg); cursor: pointer; } dl > div { display: grid; grid-template-columns: 140px 1fr; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--smart-border); font-size: 13px; line-height: 1.6; } dd { margin: 0; overflow-wrap: anywhere; } p { color: var(--smart-muted); font-size: 13px; line-height: 1.7; } [role='alert'] { color: var(--smart-danger); } nav { display: flex; gap: 20px; flex-wrap: wrap; } a { color: var(--smart-primary-strong); font-size: 13px; }
@media (max-width: 600px) { .readiness { padding: 16px; } dl > div { grid-template-columns: 1fr; gap: 6px; } }
</style>
