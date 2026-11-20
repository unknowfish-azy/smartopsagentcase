<template>
  <section class="architecture-page">
    <header class="architecture-header">
      <p class="eyebrow">SMARTOPS AGENT / 6 PORTALS · 7 LAYERS</p>
      <h1>分层架构总览</h1>
      <p>六级平级入口接入统一后端与七层技术架构；每层有清晰职责、技术边界和训练波次。</p>
    </header>

    <div class="portal-access-band">
      <div class="band-head">
        <p class="eyebrow">接入门户 / ACCESS PORTALS</p>
        <h2>平级入口矩阵</h2>
        <p>所有入口共用同一后端、会话治理与审计链。仅用户层在公开登录页暴露；管理层及以上入口隐蔽，需独立地址访问；高敏入口强制 MFA 与更严登录限流。</p>
      </div>
      <div class="portal-grid">
        <article
          v-for="id in PORTAL_IDS"
          :key="id"
          class="portal-node"
          :class="{ 'is-public': PORTAL_REGISTRY[id].public, 'is-sensitive': PORTAL_REGISTRY[id].sensitive }"
        >
          <div class="portal-node-top">
            <strong>{{ PORTAL_REGISTRY[id].label }}</strong>
            <span class="portal-tag" :class="PORTAL_REGISTRY[id].public ? 'tag-public' : 'tag-restricted'">
              {{ PORTAL_REGISTRY[id].public ? '公开' : '受限' }}
            </span>
          </div>
          <small class="portal-meta">{{ PORTAL_REGISTRY[id].role }} · :{{ PORTAL_REGISTRY[id].port }} · 空闲 {{ Math.round(PORTAL_REGISTRY[id].idle / 60) }}min</small>
          <p class="portal-purpose">{{ PORTAL_REGISTRY[id].purpose }}</p>
          <span v-if="PORTAL_REGISTRY[id].sensitive" class="portal-sensitive-chip">高敏 · MFA · 严限流</span>
        </article>
      </div>
    </div>

    <div class="layer-stack">
      <article v-for="(layer, index) in ARCHITECTURE_LAYERS" :key="layer.id" class="layer-row">
        <span class="layer-number">0{{ index + 1 }}</span>
        <div class="layer-title"><strong>{{ layer.title }}</strong><small>{{ layer.english }}</small></div>
        <div><b>{{ layer.owner }}</b><p>{{ layer.technology }}</p></div>
        <span class="layer-wave">WAVE {{ layer.wave }}</span>
      </article>
    </div>
    <footer class="architecture-footer"><span>保障贯穿全层</span><strong>高可用 · 可观测 · 数据安全 · 合规</strong><RouterLink to="/admin">返回管理控制台 →</RouterLink></footer>
  </section>
</template>

<script setup>
import { ARCHITECTURE_LAYERS } from '../../security/accessModel.js'
import { PORTAL_REGISTRY, PORTAL_IDS } from '../../security/portalCatalog.js'
</script>

<style scoped>
.architecture-page{max-width:1240px;margin:0 auto;padding:20px 0 60px;color:var(--smart-text)}.architecture-header{padding:16px 0 30px;border-bottom:1px solid var(--smart-border)}.eyebrow{margin:0 0 12px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.14em}.architecture-header h1{margin:0;font:500 clamp(30px,4vw,52px)/1.05 var(--font-cn)}.architecture-header p:not(.eyebrow){max-width:620px;margin:16px 0 0;color:var(--smart-muted);font:13px/1.7 var(--font-cn)}.layer-stack{display:grid;margin-top:24px}.layer-row{display:grid;grid-template-columns:54px minmax(220px,1fr) minmax(320px,1.3fr) 90px;gap:18px;align-items:center;min-height:92px;padding:14px 18px;border-bottom:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 68%,transparent)}.layer-row:first-child{border-top:1px solid var(--smart-border)}.layer-row:hover{background:color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface))}.layer-number,.layer-wave{color:var(--smart-primary-strong);font:11px var(--font-mono)}.layer-title{display:grid;gap:5px}.layer-title strong{font:600 17px var(--font-cn)}.layer-title small{color:var(--smart-muted);font:9px var(--font-mono);letter-spacing:.12em}.layer-row b{font:12px var(--font-cn);font-weight:500}.layer-row p{margin:5px 0 0;color:var(--smart-muted);font:11px/1.5 var(--font-cn)}.layer-wave{text-align:right}.architecture-footer{display:flex;align-items:center;gap:18px;margin-top:26px;color:var(--smart-muted);font:11px var(--font-cn)}.architecture-footer strong{color:var(--smart-text);font-weight:500}.architecture-footer a{margin-left:auto;color:var(--smart-primary-strong);text-decoration:none}

/* 多门户接入带：从门户注册中心派生，与 ARCHITECTURE_LAYERS 解耦，不改 7 层断言 */
.portal-access-band{margin-top:26px;padding:8px 0 4px;border-top:1px dashed var(--smart-border)}.band-head{padding:8px 0 16px}.band-head h2{margin:6px 0 0;font:600 clamp(20px,2.6vw,30px)/1.1 var(--font-cn)}.band-head p:not(.eyebrow){max-width:760px;margin:10px 0 0;color:var(--smart-muted);font:12px/1.7 var(--font-cn)}.portal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(188px,1fr));gap:12px}.portal-node{display:flex;flex-direction:column;gap:8px;min-height:140px;padding:14px 14px 12px;border:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 72%,transparent)}.portal-node.is-public{border-color:var(--smart-primary-strong)}.portal-node.is-sensitive{border-style:dashed}.portal-node-top{display:flex;align-items:center;justify-content:space-between;gap:8px}.portal-node-top strong{font:600 16px var(--font-cn)}.portal-tag{padding:2px 8px;border-radius:999px;font:9px var(--font-mono);letter-spacing:.08em;white-space:nowrap}.portal-tag.tag-public{background:color-mix(in srgb,var(--smart-primary-strong) 16%,transparent);color:var(--smart-primary-strong)}.portal-tag.tag-restricted{background:color-mix(in srgb,var(--smart-muted) 20%,transparent);color:var(--smart-muted)}.portal-meta{color:var(--smart-muted);font:10px var(--font-mono);letter-spacing:.04em}.portal-purpose{margin:0;color:var(--smart-text);font:11.5px/1.6 var(--font-cn)}.portal-sensitive-chip{align-self:flex-start;margin-top:auto;padding:2px 8px;border:1px dashed var(--smart-primary-strong);border-radius:4px;color:var(--smart-primary-strong);font:9px var(--font-mono);letter-spacing:.06em}

@media(max-width:760px){.layer-row{grid-template-columns:38px 1fr 70px;gap:10px}.layer-row>div:nth-child(3){grid-column:2}.layer-wave{grid-column:3;grid-row:1}.architecture-footer{display:grid}.architecture-footer a{margin-left:0}.portal-grid{grid-template-columns:1fr 1fr}}
</style>
