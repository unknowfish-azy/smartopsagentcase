<template>
  <section class="architecture-page">
    <header class="architecture-header"><p class="eyebrow">SMARTOPS AGENT / 7 LAYERS</p><h1>分层架构总览</h1><p>从基础设施到用户交互，每层有清晰职责、技术边界和训练波次。</p></header>
    <div class="layer-stack"><article v-for="(layer, index) in ARCHITECTURE_LAYERS" :key="layer.id" class="layer-row"><span class="layer-number">0{{ index + 1 }}</span><div class="layer-title"><strong>{{ layer.title }}</strong><small>{{ layer.english }}</small></div><div><b>{{ layer.owner }}</b><p>{{ layer.technology }}</p></div><span class="layer-wave">WAVE {{ layer.wave }}</span></article></div>
    <footer class="architecture-footer"><span>保障贯穿全层</span><strong>高可用 · 可观测 · 数据安全 · 合规</strong><RouterLink to="/admin">返回管理控制台 →</RouterLink></footer>
  </section>
</template>

<script setup>
import { ARCHITECTURE_LAYERS } from '../../security/accessModel.js'
</script>

<style scoped>
.architecture-page{max-width:1240px;margin:0 auto;padding:20px 0 60px;color:var(--smart-text)}.architecture-header{padding:16px 0 30px;border-bottom:1px solid var(--smart-border)}.eyebrow{margin:0 0 12px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.14em}.architecture-header h1{margin:0;font:500 clamp(30px,4vw,52px)/1.05 var(--font-cn)}.architecture-header p:not(.eyebrow){max-width:620px;margin:16px 0 0;color:var(--smart-muted);font:13px/1.7 var(--font-cn)}.layer-stack{display:grid;margin-top:24px}.layer-row{display:grid;grid-template-columns:54px minmax(220px,1fr) minmax(320px,1.3fr) 90px;gap:18px;align-items:center;min-height:92px;padding:14px 18px;border-bottom:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 68%,transparent)}.layer-row:first-child{border-top:1px solid var(--smart-border)}.layer-row:hover{background:color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface))}.layer-number,.layer-wave{color:var(--smart-primary-strong);font:11px var(--font-mono)}.layer-title{display:grid;gap:5px}.layer-title strong{font:600 17px var(--font-cn)}.layer-title small{color:var(--smart-muted);font:9px var(--font-mono);letter-spacing:.12em}.layer-row b{font:12px var(--font-cn);font-weight:500}.layer-row p{margin:5px 0 0;color:var(--smart-muted);font:11px/1.5 var(--font-cn)}.layer-wave{text-align:right}.architecture-footer{display:flex;align-items:center;gap:18px;margin-top:26px;color:var(--smart-muted);font:11px var(--font-cn)}.architecture-footer strong{color:var(--smart-text);font-weight:500}.architecture-footer a{margin-left:auto;color:var(--smart-primary-strong);text-decoration:none}@media(max-width:760px){.layer-row{grid-template-columns:38px 1fr 70px;gap:10px}.layer-row>div:nth-child(3){grid-column:2}.layer-wave{grid-column:3;grid-row:1}.architecture-footer{display:grid}.architecture-footer a{margin-left:0}}
</style>
