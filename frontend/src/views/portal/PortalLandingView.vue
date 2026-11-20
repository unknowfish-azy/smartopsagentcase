<script setup>
import { computed } from 'vue'
import { currentPortal } from '../../security/portalSwitch.js'
import { portalSpec } from '../../security/portalCatalog.js'
import { ROLE_CAPABILITIES, ROLE_LABELS } from '../../security/accessModel.js'

const portal = computed(() => currentPortal())
const spec = computed(() => portalSpec(portal.value))
const role = computed(() => spec.value?.role)
const capabilities = computed(() => ROLE_CAPABILITIES[role.value] || [])
</script>

<template>
  <section class="portal-landing">
    <header class="portal-landing__hero">
      <p class="portal-landing__eyebrow">{{ spec?.label }}</p>
      <h1>欢迎进入{{ spec?.label }}</h1>
      <p class="portal-landing__purpose">{{ spec?.purpose }}</p>
    </header>

    <div class="portal-landing__notice" role="note">
      <strong>当前为门户骨架版本。</strong>
      本门户的独立登录入口、鉴权、人机验证与会话隔离均已就绪；
      专属业务页面将按模块分批落地，此处不展示任何模拟或占位数据。
    </div>

    <div class="portal-landing__caps">
      <h2>已定义的能力范围（{{ ROLE_LABELS[role] }}）</h2>
      <ul>
        <li v-for="cap in capabilities" :key="cap">{{ cap }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.portal-landing { max-width: 880px; }
.portal-landing__hero { margin-bottom: 24px; }
.portal-landing__eyebrow { margin: 0 0 6px; font-size: 12px; letter-spacing: 2px; text-transform: uppercase; color: var(--smart-muted, #7e869c); }
.portal-landing h1 { margin: 0 0 10px; font-size: 26px; }
.portal-landing__purpose { margin: 0; font-size: 15px; color: var(--smart-muted, #9aa3b8); line-height: 1.7; }
.portal-landing__notice { margin: 20px 0; padding: 14px 16px; border-radius: 10px; background: rgba(255,196,0,0.08); border: 1px solid rgba(255,196,0,0.25); color: #ffe7a3; font-size: 13px; line-height: 1.7; }
.portal-landing__caps { margin-top: 28px; }
.portal-landing__caps h2 { font-size: 15px; margin: 0 0 10px; color: var(--smart-text, #e6e9f2); }
.portal-landing__caps ul { margin: 0; padding-left: 20px; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px 18px; }
.portal-landing__caps li { font-size: 13px; color: var(--smart-muted, #9aa3b8); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
