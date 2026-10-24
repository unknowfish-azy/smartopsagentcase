<template>
  <section class="generation-center"><header><div><p class="eyebrow">ARTIFACT GENERATION</p><h1>生成中心</h1><p class="muted">从故障经验生成 Skill、脚本或插件草稿，审核前不会执行。</p></div><button class="primary" type="button" @click="openCreate">新建草稿</button></header><p v-if="error" class="error" role="alert">{{ error }}</p><div class="drafts"><article v-for="draft in drafts" :key="draft.id"><div><span class="type">{{ draft.artifactType }}</span><h2>{{ draft.title }}</h2><p>{{ draft.sourceRef || '手动创建' }}</p></div><div class="meta"><span>{{ draft.risk }}</span><strong>{{ draft.status }}</strong><button v-if="draft.status === 'DRAFT'" type="button" @click="submit(draft)">提交审核</button></div></article><p v-if="!drafts.length" class="empty">暂无产物草稿。</p></div></section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { createArtifactDraft, getArtifactDrafts, submitArtifactDraft } from '../../api/artifactDrafts.js'
const drafts = ref([]), error = ref('')
const unwrap = value => value?.data ?? value
async function load() { try { drafts.value = unwrap(await getArtifactDrafts()) || [] } catch (cause) { error.value = cause.message || '读取失败' } }
async function openCreate() { const title = window.prompt('草稿标题')?.trim(); if (!title) return; const content = window.prompt('草稿内容')?.trim(); if (!content) return; try { await createArtifactDraft({ type: 'SKILL', title, content, risk: 'READ_ONLY' }); await load() } catch (cause) { error.value = cause.message || '创建失败' } }
async function submit(draft) { try { await submitArtifactDraft(draft.id); await load() } catch (cause) { error.value = cause.message || '提交失败' } }
onMounted(load)
</script>
<style scoped>
.generation-center{max-width:1100px;margin:0 auto;padding:24px;color:var(--smart-text)}header{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.eyebrow{font:10px var(--font-mono);letter-spacing:.12em;color:var(--smart-primary-strong)}h1{margin:8px 0;font-size:30px}.muted{color:var(--smart-muted);font-size:12px}.primary,button{min-height:40px;padding:9px 13px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-surface);color:var(--smart-text);cursor:pointer}.primary{background:var(--smart-primary-strong);color:var(--smart-bg);border-color:transparent}.drafts{margin-top:28px;border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:10px}.drafts article{display:flex;justify-content:space-between;gap:18px;padding:18px;border-bottom:1px solid var(--smart-border)}.drafts article:last-child{border-bottom:0}.type{font:10px var(--font-mono);color:var(--smart-primary-strong)}h2{margin:7px 0;font-size:16px}.drafts p{color:var(--smart-muted);font-size:11px}.meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:10px}.meta strong{color:#d69a50}.empty{padding:38px;text-align:center}.error{color:var(--smart-danger);font-size:12px}@media(max-width:650px){header,.drafts article{flex-direction:column}.generation-center{padding:12px}}
</style>
