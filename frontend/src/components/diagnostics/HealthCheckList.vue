<template>
  <section class="diagnostic-card health-card" aria-labelledby="health-card-title">
    <header><div><p class="diagnostic-kicker">{{ admin ? 'ADMIN DIAGNOSTICS' : 'SERVICE HEALTH' }}</p><h2 id="health-card-title">{{ admin ? '系统健康与依赖检查' : '我的服务状态' }}</h2></div><button type="button" :disabled="loading" @click="load">{{ loading ? '检查中…' : '重新检查' }}</button></header>
    <p v-if="loading" class="diagnostic-status" role="status">正在检查当前依赖，旧结果仅作为参考。</p>
    <p v-if="error" class="diagnostic-error" role="alert">{{ error }}</p>
    <p v-if="status && stale" class="diagnostic-stale" role="status">结果可能已过期{{ checkedAt ? ` · ${formatTime(checkedAt)}` : '' }}，请重新检查确认当前状态。</p>
    <p v-if="checkedAt" class="diagnostic-status">最近获取：{{ formatTime(checkedAt) }} · 五分钟内有效</p>
    <div v-if="status" class="health-list">
      <article v-for="item in status.checks" :key="item.id" class="health-row">
        <div><strong>{{ item.label }}</strong><small>{{ item.checkKind }} · {{ item.scope }}<span v-if="item.checkedAt"> · {{ formatTime(item.checkedAt) }}</span></small></div>
        <div>
          <span class="health-status" :class="{ [`health-status--${item.status.toLowerCase()}`]: !stale && !loading, 'health-status--stale': stale || loading }">{{ loading ? '检查中…' : healthStateLabel(item.status, stale) }}</span>
          <p>{{ item.summary }}</p><small>下一步：{{ item.nextAction }}</small>
        </div>
      </article>
    </div>
    <p v-else-if="!loading" class="diagnostic-empty">暂无检查结果。点击重新检查获取当前状态。</p>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { diagnosticsApi } from '../../api/diagnostics.ts'
import { createDiagnosticState, healthStateLabel } from './healthState.js'

const props = defineProps({ admin: { type: Boolean, default: false } })
const emit = defineEmits(['policy'])
const now = ref(Date.now())
let freshnessTimer
const { status, checkedAt, loading, stale, error, load } = createDiagnosticState(async () => {
  const result = props.admin ? await diagnosticsApi.adminHealth() : await diagnosticsApi.health()
  now.value = Date.now()
  emit('policy', props.admin ? result.policy || null : null)
  return result
}, now)

function formatTime(value) { return new Date(value).toLocaleString('zh-CN') }

onMounted(() => { load(); freshnessTimer = window.setInterval(() => { now.value = Date.now() }, 5000) })
onBeforeUnmount(() => window.clearInterval(freshnessTimer))
</script>

<style scoped>
.diagnostic-card { padding: 24px; border: 1px solid var(--smart-border-strong); border-radius: 14px; background: var(--smart-surface); color: var(--smart-text); box-shadow: 0 12px 28px color-mix(in srgb, var(--smart-text) 8%, transparent); }.diagnostic-card header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }.diagnostic-kicker { margin:0 0 8px; color:var(--smart-primary-strong); font:10px var(--font-mono); letter-spacing:.12em; }.diagnostic-card h2 { margin:0; font-size:22px; font-weight:500; }.diagnostic-card button { min-height:40px; border:1px solid var(--smart-border); border-radius:8px; padding:8px 14px; color:var(--smart-text); background:var(--smart-bg); cursor:pointer; }.diagnostic-status,.diagnostic-stale { margin:16px 0 0; color:var(--smart-muted); line-height:1.5; }.diagnostic-stale { color:var(--smart-warning); }.health-list { margin-top:22px; }.health-row { display:grid; grid-template-columns:minmax(150px,.45fr) minmax(0,1fr); gap:20px; padding:16px 0; border-top:1px solid var(--smart-border); }.health-row strong { display:block; font-size:14px; }.health-row small { display:block; margin-top:5px; color:var(--smart-muted); font-size:11px; line-height:1.5; }.health-status { display:inline-flex; padding:3px 8px; border:1px solid currentColor; border-radius:999px; font:10px var(--font-mono); }.health-status--healthy { color:var(--smart-success); }.health-status--unhealthy { color:var(--smart-danger); }.health-status--unconfigured,.health-status--not_checked { color:var(--smart-warning); }.health-status--forbidden { color:var(--smart-muted); }.health-status--stale { color:var(--smart-warning); }.health-row p { margin:8px 0 0; color:var(--smart-text); line-height:1.5; }.diagnostic-error { margin:18px 0 0; color:var(--smart-danger); }.diagnostic-empty { margin:24px 0 0; color:var(--smart-muted); }@media (max-width:700px){.diagnostic-card{padding:18px}.diagnostic-card header{flex-direction:column}.health-row{grid-template-columns:1fr;gap:10px}}
</style>
