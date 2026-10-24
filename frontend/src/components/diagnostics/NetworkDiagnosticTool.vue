<template>
  <section class="diagnostic-card network-card" aria-labelledby="network-title">
    <header><div><p class="diagnostic-kicker">SERVICE PROBE / 受控探测</p><h2 id="network-title">{{ certificateMode ? 'HTTPS 证书检查' : 'HTTP / API 可用性检查' }}</h2></div><span class="security-note">仅使用管理员授权目标</span></header>
    <p v-if="!targets.length && !loadingTargets" class="diagnostic-empty">当前没有授权目标。请联系管理员配置固定探测目标。</p>
    <form v-else class="network-form" @submit.prevent="run">
      <label>目标<select v-model="form.targetId" required><option value="" disabled>选择已授权目标</option><option v-for="target in targets" :key="target.id" :value="target.id">{{ target.label }} / {{ target.scheme }}</option></select></label>
      <template v-if="!certificateMode"><label>方法<select v-model="form.method"><option>GET</option><option>HEAD</option></select></label><label>JSON 字段（可选）<input v-model.trim="form.assertionPath" :disabled="form.method === 'HEAD'" placeholder="例如 data.status"></label><label v-if="form.assertionPath">断言<select v-model="form.assertionType"><option value="exists">字段存在</option><option value="equals">标量相等</option></select></label><label v-if="form.assertionType === 'equals'">期望值<input v-model="form.expectedValue" placeholder="true / healthy / 200"></label></template>
      <button type="submit" :disabled="running || !form.targetId">{{ running ? '检查中…' : error ? '重试检查' : '开始检查' }}</button>
    </form>
    <p v-if="error" class="diagnostic-error" role="alert">{{ error }}</p>
    <p v-if="running" role="status">检查中…</p>
    <p v-if="result?.errorCategory" role="status">{{ normalizeDiagnosticFailure(result).message }}</p>
    <article v-if="result" class="probe-result"><span class="health-status" :class="`health-status--${(result.status || '').toLowerCase()}`">{{ result.status }}</span><p>{{ result.summary }}</p><dl v-if="!certificateMode"><div><dt>HTTP</dt><dd>{{ result.statusCode || '—' }}</dd></div><div><dt>耗时</dt><dd>{{ result.durationMs }} ms</dd></div><div><dt>正文</dt><dd>{{ result.responseBytes }} bytes{{ result.truncated ? '（已截断）' : '' }}</dd></div><div><dt>断言</dt><dd>{{ result.assertion }}</dd></div></dl><dl v-else-if="result.certificate"><div><dt>颁发者</dt><dd>{{ result.certificate.issuer }}</dd></div><div><dt>有效期</dt><dd>{{ result.certificate.notBefore }} → {{ result.certificate.notAfter }}</dd></div><div><dt>域名</dt><dd>{{ result.certificate.names.join('、') || '未知' }}</dd></div></dl><p class="next-action">下一步：{{ result.nextAction }}</p></article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { diagnosticsApi } from '../../api/diagnostics.ts'
import { normalizeDiagnosticFailure } from './healthState.js'

const props = defineProps({ certificateMode: { type: Boolean, default: false } })
const targets = ref([]); const loadingTargets = ref(true); const running = ref(false); const error = ref(''); const result = ref(null)
const form = reactive({ targetId: '', method: 'GET', assertionPath: '', assertionType: 'exists', expectedValue: '' })

onMounted(async () => { try { targets.value = await diagnosticsApi.targets(); form.targetId = targets.value[0]?.id || '' } catch (failure) { error.value = normalizeDiagnosticFailure(failure).message } finally { loadingTargets.value = false } })
async function run() {
  if (running.value || !form.targetId) return
  running.value = true; error.value = ''; result.value = null
  const hasAssertion = form.method !== 'HEAD' && Boolean(form.assertionPath)
  const payload = { targetId: form.targetId, method: form.method, assertionPath: hasAssertion ? form.assertionPath : null, assertionType: hasAssertion ? form.assertionType : null, expectedValue: hasAssertion && form.assertionType === 'equals' && form.expectedValue !== '' ? parseValue(form.expectedValue) : null }
  try { result.value = props.certificateMode ? await diagnosticsApi.certificate(payload.targetId) : await diagnosticsApi.http(payload) }
  catch (failure) { error.value = `${normalizeDiagnosticFailure(failure).message}，请重试。` }
  finally { running.value = false }
}
function parseValue(value) { if (value === 'true') return true; if (value === 'false') return false; if (/^-?\d+(?:\.\d+)?$/.test(value)) return Number(value); return value }
</script>

<style scoped>
.diagnostic-card{padding:24px;border:1px solid var(--smart-border-strong);border-radius:14px;background:var(--smart-surface);color:var(--smart-text);box-shadow:0 12px 28px rgba(16,53,70,.08)}.diagnostic-card header{display:flex;justify-content:space-between;gap:16px}.diagnostic-kicker{margin:0 0 8px;color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.12em}.diagnostic-card h2{margin:0;font-size:22px;font-weight:500}.security-note{color:var(--smart-muted);font-size:11px}.network-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:24px}.network-form label{display:grid;gap:6px;color:var(--smart-muted);font-size:12px}.network-form input,.network-form select{min-height:42px;border:1px solid var(--smart-border);border-radius:8px;padding:8px 10px;background:var(--smart-bg);color:var(--smart-text)}.network-form button{grid-column:1/-1;min-height:44px;border:1px solid var(--smart-primary);border-radius:8px;background:var(--smart-primary);color:var(--smart-primary-foreground);cursor:pointer}.diagnostic-error{margin-top:16px;color:var(--smart-danger)}.probe-result{margin-top:24px;padding-top:20px;border-top:1px solid var(--smart-border)}.health-status{display:inline-flex;padding:3px 8px;border:1px solid currentColor;border-radius:999px;font:10px var(--font-mono)}.health-status--healthy{color:var(--smart-success)}.health-status--unhealthy{color:var(--smart-danger)}.probe-result p{line-height:1.6}.probe-result dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.probe-result dl div{padding:10px;border:1px solid var(--smart-border);border-radius:8px}.probe-result dt{color:var(--smart-muted);font-size:11px}.probe-result dd{margin:4px 0 0;overflow-wrap:anywhere}.next-action{color:var(--smart-muted)}@media(max-width:700px){.diagnostic-card{padding:18px}.diagnostic-card header{flex-direction:column}.network-form{grid-template-columns:1fr}.probe-result dl{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
