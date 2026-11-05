<template>
  <section class="readiness" aria-labelledby="readiness-title">
    <header><h2 id="readiness-title">服务接入与安全检查</h2><button type="button" :disabled="loading" @click="load">{{ loading ? '检查中…' : '重新检查' }}</button></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="status?.checkedAt" class="readiness-time">检查时间：{{ checkedAt }} · 手动触发，非持续监控</p>
    <h3>配置状态</h3>
    <dl v-if="status">
      <div><dt>用户认证</dt><dd>服务端会话 · CSRF 校验 · 管理角色校验</dd></div>
      <div><dt>服务间认证</dt><dd>{{ status.internalAuthenticationConfigured ? '已配置；内部调用仍需携带有效凭据' : '未配置；内部接口拒绝访问，不影响已登录用户聊天入口' }}</dd></div>
      <div v-for="source in status.observability" :key="`cfg-${source.id}`"><dt>{{ source.id }}</dt><dd>{{ source.configured ? '已配置（连通性未验证）' : '未配置数据源' }}</dd></div>
      <div><dt>Harbor</dt><dd>{{ status.harbor.configured ? '已配置（连通性与权限未验证）' : '未配置镜像仓库' }}</dd></div>
    </dl>
    <h3>探测结果</h3>
    <dl v-if="status">
      <div><dt>数据库关键表</dt><dd><span class="readiness-tag" :class="status.unavailableTables.length ? 'is-bad' : 'is-ok'">{{ status.unavailableTables.length ? '探测失败' : '探测通过' }}</span><span v-if="status.unavailableTables.length" class="readiness-reason">不可用：{{ status.unavailableTables.join('、') }}</span></dd></div>
      <div v-for="source in status.observability" :key="`probe-${source.id}`"><dt>{{ source.id }} 连通性</dt><dd><span class="readiness-tag is-unknown">未验证</span><span class="readiness-reason">{{ source.configured ? '配置已存在，首次查询时才会验证连通性' : '没有可探测的配置' }}</span></dd></div>
      <div><dt>Harbor 连通性</dt><dd><span class="readiness-tag is-unknown">未验证</span><span class="readiness-reason">{{ status.harbor.configured ? '项目读取时验证连通性与权限' : '没有可探测的配置' }}</span></dd></div>
      <div><dt>SSH / SFTP</dt><dd><span class="readiness-tag is-unknown">未验证</span><span class="readiness-reason">{{ status.remoteConnectivity === 'NOT_VERIFIED' ? '请在连接中心显式建立测试连接，此处不自动探测目标' : status.remoteConnectivity }}</span></dd></div>
    </dl>
    <p>“已配置”不等于“已连通”：本页不自动调用模型、不执行远程命令，失败项不会标记为通过。公网部署还需要 HTTPS、安全 Cookie 与独立的部署安全检查。</p>
    <nav><RouterLink to="/admin/readiness">服务接入检查</RouterLink><RouterLink to="/admin/security">管理员二次认证</RouterLink></nav>
    <p class="readiness-portal">模型接入、连接中心、指标查询与仓库浏览属于用户门户：需切换到用户门户并重新登录后访问，管理端不注册这些页面。</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import request from '../../utils/request.ts'
const status = ref(null)
const loading = ref(false)
const error = ref('')
const checkedAt = computed(() => {
  const value = status.value?.checkedAt
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
})
// 每次检查都重新取数，不用上一次结果冒充本次结论。
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
header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; } h2 { margin: 0; font-size: 20px; } h3 { margin: 20px 0 8px; font-size: 15px; } button { min-height: 44px; border: 1px solid var(--smart-border); border-radius: 7px; padding: 8px 12px; color: var(--smart-text); background: var(--smart-bg); cursor: pointer; } dl > div { display: grid; grid-template-columns: 140px 1fr; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--smart-border); font-size: 13px; line-height: 1.6; } dd { margin: 0; overflow-wrap: anywhere; } p { color: var(--smart-muted); font-size: 13px; line-height: 1.7; } .readiness-time { margin: 8px 0 0; } [role='alert'] { color: var(--smart-danger); } nav { display: flex; gap: 20px; flex-wrap: wrap; } a { color: var(--smart-primary-strong); font-size: 13px; }
.readiness-tag { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; margin-right: 8px; border: 1px solid var(--smart-border); border-radius: 999px; font-size: 12px; }
.readiness-tag.is-ok { border-color: var(--smart-success-border, var(--smart-border)); color: var(--smart-success, var(--smart-text)); }
.readiness-tag.is-bad { border-color: var(--smart-danger); color: var(--smart-danger); }
.readiness-tag.is-unknown { color: var(--smart-muted); }
.readiness-reason { color: var(--smart-muted); font-size: 12px; }
@media (max-width: 600px) { .readiness { padding: 16px; } dl > div { grid-template-columns: 1fr; gap: 6px; } }
</style>
