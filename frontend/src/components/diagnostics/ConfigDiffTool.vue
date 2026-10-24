<template>
  <section class="diagnostic-card diff-card" aria-labelledby="diff-title">
    <header><div><p class="diagnostic-kicker">LOCAL BROWSER TOOL / 本地工具</p><h2 id="diff-title">配置差异检查</h2><p>文本只在当前浏览器内比较，不上传、不保存、不发送给 AI。</p></div><button type="button" @click="clear">清空</button></header>
    <div class="diff-inputs"><label>基准配置<textarea v-model="left" spellcheck="false" placeholder="粘贴基准配置"></textarea></label><label>待检查配置<textarea v-model="right" spellcheck="false" placeholder="粘贴待检查配置"></textarea></label></div>
    <label class="diff-option"><input v-model="ignoreTrailingWhitespace" type="checkbox"> 忽略行尾空白</label><p v-if="error" class="diagnostic-error" role="alert">{{ error }}</p><div v-if="diff" class="diff-summary"><strong>新增 {{ diff.added }} 行</strong><strong>删除 {{ diff.removed }} 行</strong><span>敏感值已脱敏，仅保留变更证据</span></div><div v-if="diff" class="diff-rows"><div v-for="(row,index) in diff.rows" :key="`${index}-${row.type}`" :class="`diff-row diff-row--${row.type}`"><span>{{ row.before ?? '·' }}</span><span>{{ row.after ?? '·' }}</span><code>{{ row.text }}</code></div></div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { compareConfigTexts } from '../../domain/diagnostics/configDiff.ts'
const left = ref(''); const right = ref(''); const ignoreTrailingWhitespace = ref(false)
const error = ref('')
const diff = computed(() => { error.value = ''; try { if (!left.value && !right.value) return null; return compareConfigTexts(left.value, right.value, { ignoreTrailingWhitespace: ignoreTrailingWhitespace.value }) } catch (failure) { error.value = failure.message || '差异计算失败'; return null } })
function clear() { left.value = ''; right.value = ''; error.value = '' }
</script>

<style scoped>
.diagnostic-card{padding:24px;border:1px solid var(--smart-border-strong);border-radius:14px;background:var(--smart-surface);color:var(--smart-text);box-shadow:0 12px 28px rgba(16,53,70,.08)}.diagnostic-card header{display:flex;justify-content:space-between;gap:16px}.diagnostic-kicker{margin:0 0 8px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.12em}.diagnostic-card h2{margin:0;font-size:22px;font-weight:500}.diagnostic-card header p:not(.diagnostic-kicker){color:var(--smart-muted);font-size:12px}.diagnostic-card button{min-height:38px;border:1px solid var(--smart-border);border-radius:8px;padding:7px 12px;background:var(--smart-bg);color:var(--smart-text);cursor:pointer}.diff-inputs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px}.diff-inputs label{display:grid;gap:7px;color:var(--smart-muted);font-size:12px}.diff-inputs textarea{min-height:230px;resize:vertical;border:1px solid var(--smart-border);border-radius:8px;padding:12px;background:var(--smart-bg);color:var(--smart-text);font:12px/1.55 var(--font-mono)}.diff-option{display:inline-flex;gap:7px;align-items:center;margin-top:14px;color:var(--smart-muted);font-size:12px}.diagnostic-error{color:var(--smart-danger)}.diff-summary{display:flex;flex-wrap:wrap;gap:16px;margin-top:18px;padding:12px;border:1px solid var(--smart-border);border-radius:8px}.diff-summary span{color:var(--smart-muted);font-size:12px}.diff-rows{max-height:360px;margin-top:14px;overflow:auto;border:1px solid var(--smart-border);border-radius:8px}.diff-row{display:grid;grid-template-columns:32px 32px minmax(0,1fr);gap:8px;padding:4px 10px;font:12px/1.5 var(--font-mono);white-space:pre-wrap;overflow-wrap:anywhere}.diff-row--added{background:color-mix(in srgb,var(--smart-success) 12%,transparent)}.diff-row--removed{background:color-mix(in srgb,var(--smart-danger) 12%,transparent)}.diff-row>span{color:var(--smart-muted)}.diff-row code{color:var(--smart-text)}@media(max-width:700px){.diagnostic-card{padding:18px}.diagnostic-card header{flex-direction:column}.diff-inputs{grid-template-columns:1fr}.diff-inputs textarea{min-height:170px}}
</style>
