<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import http from '../../utils/request'
import { summarizePrometheusResult } from './observabilityResults'
const metricPresets = [
  { label: '目标状态', query: 'up{job="windows"}', unit: '' },
  { label: 'CPU 使用率', query: '100 * (1 - avg by (instance) (rate(windows_cpu_time_total{mode="idle",core!="_Total"}[1m])))', unit: '%' },
  { label: '可用内存', query: 'windows_memory_available_bytes / 1024^3', unit: 'GiB' },
  { label: '磁盘剩余', query: 'windows_logical_disk_free_bytes{volume=~"[A-Z]:"} / 1024^3', unit: 'GiB' },
  { label: '网络接收', query: 'rate(windows_net_bytes_received_total[1m]) * 8 / 1e6', unit: 'Mb/s' }
]
const props = defineProps({ source: { type: String, required: true } })
const query = ref(''), minutes = ref(15), limit = ref(200)
const configured = ref(false), checking = ref(false), running = ref(false)
const error = ref(''), result = ref(null), resultQuery = ref(''), resultUnit = ref('')
let generation = 0
const unwrap = value => value?.data ?? value
const isPrometheus = computed(() => props.source === 'prometheus')
const activePreset = computed(() => metricPresets.find(preset => preset.query === query.value))
const summaryRows = computed(() => isPrometheus.value ? summarizePrometheusResult(result.value?.response, resultUnit.value) : [])
const sampleTime = timestamp => new Date(timestamp * 1000).toLocaleString('zh-CN')
function choosePreset(preset) {
  query.value = preset.query
  execute(false)
}
async function checkConfiguration() {
  const epoch = ++generation
  checking.value = true; configured.value = false; error.value = ''; result.value = null
  try {
    const list = unwrap(await http.get('/api/observability/sources'))
    if (epoch === generation) configured.value = list.some(item => item.id === props.source && item.configured)
  } catch (ex) { if (epoch === generation) error.value = ex.message }
  finally { if (epoch === generation) checking.value = false }
}
watch(() => props.source, () => {
  running.value = false
  query.value = props.source === 'prometheus' ? 'up' : '{job="smartops-backend"}'
  checkConfiguration()
}, { immediate: true })
onBeforeUnmount(() => { generation++ })
async function execute(test = false) {
  if (running.value || !configured.value || checking.value) return
  const text = test && isPrometheus.value ? 'vector(1)' : query.value.trim()
  if (!text || text.length > 2000 || !Number.isInteger(minutes.value) || minutes.value < 1 || minutes.value > 60
      || !Number.isInteger(limit.value) || limit.value < 1 || limit.value > 500) {
    error.value = '请输入查询，时间范围为 1–60 分钟，日志数量为 1–500。'; return
  }
  const epoch = generation
  running.value = true; error.value = ''; result.value = null
  try {
    const value = unwrap(await http.post(`/api/observability/${props.source}/query`, {
      query: text, minutes: test ? 1 : minutes.value, limit: test ? 1 : limit.value
    }, { timeout: 30000 }))
    if (epoch === generation) {
      result.value = value
      resultQuery.value = text
      resultUnit.value = test ? '' : activePreset.value?.unit ?? ''
    }
  } catch (ex) { if (epoch === generation) error.value = ex.message || '观测查询失败' }
  finally { if (epoch === generation) running.value = false }
}
</script>

<template>
  <section class="observability-query">
    <h2>{{ isPrometheus ? 'Prometheus 指标查询' : 'Loki 日志查询' }}</h2>
    <p>后端 HTTP 只读查询，不需要 SSH。返回数据来自配置的数据源。</p>
    <p role="status">{{ checking ? '检查配置中…' : configured ? '地址已配置，连通性需要实际查询验证' : '尚未配置数据源' }}</p>
    <details><summary>数据源配置说明</summary><p>在后端启动环境中设置 {{ isPrometheus ? 'SMARTOPS_PROMETHEUS_URL' : 'SMARTOPS_LOKI_URL' }}；如需 Bearer Token，设置对应的 {{ isPrometheus ? 'SMARTOPS_PROMETHEUS_TOKEN' : 'SMARTOPS_LOKI_TOKEN' }}，然后重启后端。地址填写服务基础 URL，不附加查询 API 路径。</p><p>凭据不传给浏览器。Loki 多租户请求头与其他认证方式尚未接入。当前沿用项目开发环境身份模型，仅用于受信任的本地开发环境。</p></details>
    <button type="button" :disabled="checking || running" @click="checkConfiguration">重新检查配置</button>
    <div v-if="isPrometheus" class="metric-presets" role="group" aria-label="Windows 主机指标快捷查询">
      <button v-for="preset in metricPresets" :key="preset.label" type="button" :aria-pressed="activePreset?.label === preset.label" :disabled="!configured || checking || running" @click="choosePreset(preset)">{{ preset.label }}</button>
    </div>
    <form @submit.prevent="execute(false)">
      <label>{{ isPrometheus ? 'PromQL' : 'LogQL' }}<textarea v-model="query" maxlength="2000" rows="3" :disabled="running" /></label>
      <label>最近多少分钟<input v-model.number="minutes" type="number" min="1" max="60" :disabled="running" /></label>
      <label v-if="!isPrometheus">最多日志行数<input v-model.number="limit" type="number" min="1" max="500" :disabled="running" /></label>
      <p>结果上限 1 MiB。Prometheus 查询最多约 600 个时间点/序列；Loki 返回最近日志，可能未覆盖范围内所有数据。空结果不等同于服务健康。</p>
      <div><button type="button" :disabled="!configured || running || checking" @click="execute(true)">测试连接（最小查询）</button> <button type="submit" :disabled="!configured || running || checking">{{ running ? '查询中…' : '查询真实数据' }}</button></div>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
    <section v-if="result" aria-live="polite">
      <h3>查询结果</h3><p class="result-query">{{ resultQuery }}</p><p>TraceId：{{ result.traceId }}</p><p>时间：{{ result.start }} — {{ result.end }}</p>
      <template v-if="isPrometheus">
        <p v-if="!summaryRows.length" role="status">当前时间范围没有返回样本。请检查指标名、抓取目标和采集时间。</p>
        <div v-else class="sample-table-wrap"><table class="sample-table"><thead><tr><th scope="col">序列标签</th><th scope="col">最新值</th><th scope="col">样本时间</th></tr></thead><tbody><tr v-for="(row, index) in summaryRows" :key="`${row.labels}-${index}`"><td>{{ row.labels }}</td><td>{{ row.value }}</td><td>{{ sampleTime(row.timestamp) }}</td></tr></tbody></table></div>
      </template>
      <p>运行记录保存结果摘要；原始日志和查询表达式不持久化。</p>
      <RouterLink to="/operations/runs">查看运行记录</RouterLink>
      <details class="raw-response"><summary>原始响应</summary><pre>{{ JSON.stringify(result.response, null, 2) }}</pre></details>
    </section>
  </section>
</template>

<style scoped>
.observability-query{padding:24px;color:var(--smart-text)}h2{font-size:20px}p,details{font-size:13px;line-height:1.8;color:var(--smart-muted)}form,label{display:grid;gap:10px}form{margin-top:20px}input,textarea{box-sizing:border-box;max-width:100%;padding:10px;color:var(--smart-text);background:var(--smart-surface);border:1px solid var(--smart-border);border-radius:6px}button{padding:10px;margin-top:10px;cursor:pointer;color:var(--smart-text);background:var(--smart-surface);border:1px solid var(--smart-border);border-radius:6px}button:disabled{opacity:.5;cursor:not-allowed}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto;padding:12px;background:var(--smart-surface)}[role=alert]{color:var(--smart-danger,#b03949)}
.metric-presets{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}.metric-presets button{margin:0;padding:8px 10px;font-size:12px}.metric-presets button[aria-pressed="true"]{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong)}.result-query{overflow-wrap:anywhere;font-family:var(--font-mono)}.sample-table-wrap{overflow-x:auto;margin:12px 0}.sample-table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}.sample-table th,.sample-table td{padding:10px 12px;border-bottom:1px solid var(--smart-border);vertical-align:top}.sample-table td:first-child{overflow-wrap:anywhere;max-width:360px;font-family:var(--font-mono)}.sample-table td:nth-child(2){white-space:nowrap;font-variant-numeric:tabular-nums}.raw-response{margin-top:14px}.raw-response summary{cursor:pointer}.raw-response pre{margin-top:8px}
</style>
