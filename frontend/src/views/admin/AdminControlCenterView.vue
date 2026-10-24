<template>
  <section class="admin-page">
    <header class="admin-header">
      <div><p class="eyebrow">MANAGEMENT LAYER / 管理层</p><h1>系统管控中心</h1><p>把身份、配置、审计和安全策略集中到一个可追溯的管理入口。</p></div>
      <div class="admin-badge"><strong>ADMIN</strong><span>最小权限 · 全程留痕</span></div>
    </header>
    <div class="domain-grid">
      <article v-for="domain in domains" :key="domain.id" class="domain-row">
        <div class="domain-index">{{ domain.index }}</div><div><p>{{ domain.kicker }}</p><h2>{{ domain.title }}</h2><span>{{ domain.description }}</span></div><button type="button" :aria-label="`打开${domain.title}`" @click="openDomain(domain.id)">{{ domain.action }} <span aria-hidden="true">→</span></button>
      </article>
    </div>
    <AdminAccounts v-if="activeDomain === 'users'" />
    <AdminReadiness v-else-if="activeDomain === 'config' || activeDomain === 'security'" />
    <section class="training-strip"><div><p class="eyebrow">DEVELOPMENT PLAN / 非实时状态</p><h2>开发路线</h2></div><div class="wave-list"><span v-for="wave in TRAINING_WAVES" :key="wave.id" :class="`wave wave--${wave.status}`"><b>0{{ wave.id }}</b><small>{{ wave.title }}</small></span></div></section>
  </section>
</template>

<script setup>
import { TRAINING_WAVES } from '../../security/accessModel.js'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AdminAccounts from '../../components/ai/AdminAccounts.vue'
import AdminReadiness from '../../components/ai/AdminReadiness.vue'

const router = useRouter()
const activeDomain = ref('users')
function openDomain(id) {
  if (id === 'audit') router.push('/operations/runs')
  else activeDomain.value = id
}

const domains = [
  { id: 'users', index: '01', kicker: 'IDENTITY / 身份', title: '用户与权限', description: '账号、角色、菜单和能力授权，按最小权限分配。', action: '进入配置' },
  { id: 'config', index: '02', kicker: 'CONTROL / 配置', title: '服务接入检查', description: '检查数据库关键表、监控数据源与模型入口配置。', action: '检查接入' },
  { id: 'audit', index: '03', kicker: 'EVIDENCE / 证据', title: '审计与运营', description: '全链路操作记录、风险事件和运营统计报表。', action: '打开审计' },
  { id: 'security', index: '04', kicker: 'GOVERNANCE / 治理', title: '认证与安全状态', description: '查看已实现的会话与内部接口保护，不代表合规认证。', action: '检查状态' }
]
</script>

<style scoped>
.admin-page{max-width:1240px;margin:0 auto;padding:20px 0 60px;color:var(--smart-text)}.admin-header{display:flex;justify-content:space-between;gap:30px;padding:16px 0 34px;border-bottom:1px solid var(--smart-border)}.eyebrow{margin:0 0 10px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.14em}.admin-header h1{margin:0;font:500 clamp(30px,4vw,52px)/1.05 var(--font-cn)}.admin-header p:not(.eyebrow){max-width:600px;margin:16px 0 0;color:var(--smart-muted);font:13px/1.7 var(--font-cn)}.admin-badge{display:grid;align-content:center;gap:6px;min-width:180px;padding-left:20px;border-left:1px solid var(--smart-border)}.admin-badge strong{color:var(--smart-primary-strong);font:14px var(--font-mono);letter-spacing:.14em}.admin-badge span{color:var(--smart-muted);font:11px var(--font-cn)}.domain-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:24px}.domain-row{display:grid;grid-template-columns:48px 1fr auto;gap:16px;align-items:center;min-height:150px;padding:20px;border:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 76%,transparent)}.domain-row:hover{border-color:var(--smart-primary-strong)}.domain-index{color:var(--smart-primary-strong);font:18px var(--font-mono)}.domain-row p{margin:0 0 7px;color:var(--smart-muted);font:9px var(--font-mono);letter-spacing:.12em}.domain-row h2{margin:0 0 8px;font:600 20px var(--font-cn)}.domain-row span{color:var(--smart-muted);font:12px/1.6 var(--font-cn)}.domain-row button{border:0;background:transparent;color:var(--smart-primary-strong);font:11px var(--font-cn);cursor:pointer;white-space:nowrap}.training-strip{display:grid;grid-template-columns:220px 1fr;gap:28px;margin-top:34px;padding-top:24px;border-top:1px solid var(--smart-border)}.training-strip h2{margin:0;font:500 24px var(--font-cn)}.wave-list{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:8px}.wave{display:grid;gap:8px;min-height:86px;padding:10px;border-top:2px solid var(--smart-border);background:var(--smart-surface)}.wave b{font:12px var(--font-mono)}.wave small{color:var(--smart-muted);font:11px var(--font-cn)}.wave--ready{border-top-color:var(--smart-success)}.wave--active{border-top-color:var(--smart-primary-strong);box-shadow:0 0 20px rgba(122,215,245,.12)}.wave--planned{opacity:.6}@media(max-width:800px){.admin-header{display:block}.admin-badge{margin-top:20px;padding:14px 0 0;border-top:1px solid var(--smart-border);border-left:0}.domain-grid{grid-template-columns:1fr}.training-strip{grid-template-columns:1fr}.wave-list{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:480px){.wave-list{grid-template-columns:repeat(2,minmax(0,1fr))}.domain-row{grid-template-columns:34px 1fr}.domain-row button{grid-column:2;text-align:left}}
</style>
