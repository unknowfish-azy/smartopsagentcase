<template>
  <section class="admin-readiness-page">
    <p class="admin-eyebrow">SERVICE READINESS</p>
    <h1>服务接入检查</h1>
    <p class="admin-notice">所有主动检查均为手动、只读、受白名单控制。</p>
    <HealthCheckList admin @policy="policy = $event" />
    <section v-if="policy" class="admin-policy-summary" aria-labelledby="admin-policy-title">
      <header><div><p class="admin-eyebrow">POLICY BOUNDARY</p><h2 id="admin-policy-title">策略边界</h2></div><span class="admin-badge">只读摘要</span></header>
      <dl class="admin-policy-grid">
        <div><dt>授权目标数量</dt><dd>{{ policy.targetCount }}</dd></div>
        <div><dt>每用户并发</dt><dd>{{ policy.perUserConcurrency }}</dd></div>
        <div><dt>全局并发</dt><dd>{{ policy.globalConcurrency }}</dd></div>
        <div><dt>连接超时</dt><dd>{{ policy.connectTimeoutMs }} ms</dd></div>
        <div><dt>读取超时</dt><dd>{{ policy.readTimeoutMs }} ms</dd></div>
        <div><dt>响应上限</dt><dd>{{ formatBytes(policy.maxResponseBytes) }}</dd></div>
      </dl>
      <ul class="admin-policy-flags"><li>智维 Mini：{{ policy.miniConfigured ? '已配置' : '未配置' }}</li><li>观测数据源：{{ policy.observabilityConfigured ? '已配置' : '未配置' }}</li><li>Harbor：{{ policy.harborConfigured ? '已配置' : '未配置' }}</li></ul>
      <p class="admin-muted">策略只展示限制值和配置状态，不展示凭据、地址或响应正文。<a :href="diagnosticGuideUrl" download="health-and-diagnostic-tools.md">下载诊断操作说明</a>。</p>
    </section>
    <AdminReadiness />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import AdminReadiness from '../../components/ai/AdminReadiness.vue'
import HealthCheckList from '../../components/diagnostics/HealthCheckList.vue'
import diagnosticGuideUrl from '../../../../docs/operations/health-and-diagnostic-tools.md?url'

const policy = ref(null)
function formatBytes(value) { return `${Math.round(Number(value || 0) / 1024)} KiB` }
</script>

<style scoped>
.admin-readiness-page { display: grid; gap: 18px; }.admin-readiness-page > h1 { margin-bottom: 0; }.admin-policy-summary { padding: 22px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); box-shadow: var(--admin-shadow); }.admin-policy-summary header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.admin-policy-summary h2 { margin: 0; }.admin-policy-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }.admin-policy-grid div { min-width: 0; padding: 14px 16px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius-sm); background: var(--admin-surface-2); transition-property: border-color, background-color, transform, box-shadow; transition-duration: .3s; transition-timing-function: cubic-bezier(.4, 0, .2, 1); }.admin-policy-grid div:hover { border-color: color-mix(in srgb, var(--admin-accent) 30%, var(--admin-border)); background: var(--admin-panel); box-shadow: var(--admin-shadow); transform: translateY(var(--admin-lift)); }.admin-policy-grid dt { color: var(--admin-muted); font-size: 12px; }.admin-policy-grid dd { margin: 6px 0 0; color: var(--admin-text); font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }.admin-policy-flags { display: flex; flex-wrap: wrap; gap: 10px 16px; padding: 0; margin: 0 0 12px; color: var(--admin-text); list-style: none; }.admin-policy-flags li { display: inline-flex; align-items: center; min-height: 24px; padding: 0 10px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius-pill); background: var(--admin-soft); color: var(--admin-accent-text); font-size: 12px; }.admin-policy-summary code { overflow-wrap: anywhere; }@media (max-width: 767px) { .admin-policy-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.admin-policy-grid div:hover { transform: none; } }
@media (prefers-reduced-motion: reduce) { .admin-policy-grid div { transition: none; } .admin-policy-grid div:hover { transform: none; } }
</style>
