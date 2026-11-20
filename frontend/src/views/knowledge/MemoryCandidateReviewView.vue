<template>
  <section class="memory-review">
    <header class="page-header">
      <div>
        <p class="eyebrow">MEMORY REVIEW · P0-2 情景记忆审核门</p>
        <h1>情景记忆审核</h1>
        <p class="muted">Agent 自动沉淀的经验处于 <code>PENDING_REVIEW</code> 状态，必须经人工审核后才能进入召回池。未审核经验不会参与检索。</p>
      </div>
      <button type="button" class="ghost" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新' }}</button>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading && !items.length" class="empty">正在读取待审核记忆…</div>
    <div v-else-if="!items.length" class="empty">没有待审核的记忆候选。Agent 处置完成后会自动沉淀经验到这里。</div>

    <div v-else class="candidate-list">
      <article v-for="item in items" :key="item.id" class="candidate">
        <header class="candidate__head">
          <span class="tag tag--pending">PENDING_REVIEW</span>
          <span class="candidate__id">#{{ item.id }}</span>
          <span class="candidate__type">{{ item.memoryType }}</span>
          <span class="candidate__confidence">置信度 {{ (item.confidence * 100).toFixed(0) }}%</span>
        </header>
        <div class="candidate__body">
          <div class="candidate__field">
            <label>故障特征</label>
            <p>{{ item.incidentKey }}</p>
          </div>
          <div class="candidate__field">
            <label>建议处置</label>
            <p>{{ item.preferredAction }}</p>
          </div>
          <div class="candidate__meta">
            <span>来源 <code>{{ item.sourceRefs || '—' }}</code></span>
            <span>证据数 {{ item.evidenceCount }}</span>
            <span>{{ formatTime(item.createdAt) }}</span>
          </div>
        </div>
        <footer class="candidate__foot">
          <button type="button" class="btn btn--approve" :disabled="acting === item.id" @click="onApprove(item)">
            {{ acting === item.id ? '处理中…' : '审核通过' }}
          </button>
          <button type="button" class="btn btn--reject" :disabled="acting === item.id" @click="onReject(item)">
            驳回
          </button>
        </footer>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listMemoryCandidates, approveMemory, rejectMemory } from '../../api/p0Modules.ts'

const items: any= ref<any[]>([]), loading = ref(false), error = ref(''), acting = ref(null)
const unwrap: any= (r: any) => r?.data ?? r

async function load(): Promise<any> {
  loading.value = true; error.value = ''
  try {
    const data: any= unwrap(await listMemoryCandidates())
    items.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (cause: any) { error.value = cause.message || '读取待审核记忆失败' }
  finally { loading.value = false }
}

async function onApprove(item: any) {
  acting.value = item.id
  try {
    await approveMemory(item.id)
    items.value = items.value.filter((i: any) => i.id !== item.id)
  } catch (cause: any) { error.value = cause.message || '审核失败' }
  finally { acting.value = null }
}

async function onReject(item: any) {
  const reason: any= window.prompt('驳回原因（可选）：')
  if (reason === null) return
  acting.value = item.id
  try {
    await rejectMemory(item.id, reason)
    items.value = items.value.filter((i: any) => i.id !== item.id)
  } catch (cause: any) { error.value = cause.message || '驳回失败' }
  finally { acting.value = null }
}

function formatTime(t: any) {
  if (!t) return '—'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

onMounted(load)
</script>

<style scoped>
.memory-review { color: var(--smart-text); }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; margin-bottom: 18px; }
.eyebrow { margin: 0 0 8px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .14em; }
.muted { color: var(--smart-muted); font-size: 12px; }
.muted code { padding: 1px 5px; background: var(--smart-surface); border-radius: 3px; font-size: 11px; }
.ghost { min-height: 30px; padding: 3px 10px; border: 1px solid var(--smart-border); border-radius: 6px; background: transparent; color: var(--smart-muted); cursor: pointer; }
.ghost:hover { color: var(--smart-text); border-color: var(--smart-primary-strong); }
.empty, .error { padding: 28px; text-align: center; color: var(--smart-muted); border: 1px dashed var(--smart-border); border-radius: 8px; }
.error { color: var(--ds-semantic-danger); border-color: var(--ds-semantic-danger); }

.candidate-list { display: flex; flex-direction: column; gap: 12px; }
.candidate { padding: 14px 16px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); }
.candidate__head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; font: 10px var(--font-mono); color: var(--smart-muted); }
.tag { padding: 2px 8px; border-radius: 4px; font: 10px var(--font-mono); letter-spacing: .08em; }
.tag--pending { background: rgba(255, 180, 0, .15); color: #ffb400; border: 1px solid rgba(255, 180, 0, .3); }
.candidate__id { color: var(--smart-muted); }
.candidate__type { padding: 2px 6px; background: var(--smart-border); border-radius: 3px; }
.candidate__confidence { margin-left: auto; color: var(--smart-primary-strong); }

.candidate__body { display: flex; flex-direction: column; gap: 10px; }
.candidate__field label { display: block; font: 10px var(--font-mono); color: var(--smart-muted); margin-bottom: 4px; letter-spacing: .08em; }
.candidate__field p { margin: 0; font-size: 13px; line-height: 1.6; }
.candidate__meta { display: flex; gap: 16px; flex-wrap: wrap; font: 10px var(--font-mono); color: var(--smart-muted); }
.candidate__meta code { padding: 1px 5px; background: var(--smart-border); border-radius: 3px; }

.candidate__foot { display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--smart-border); }
.btn { min-height: 30px; padding: 4px 14px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--approve { background: rgba(0, 200, 100, .12); color: #00c864; border-color: rgba(0, 200, 100, .3); }
.btn--approve:hover:not(:disabled) { background: rgba(0, 200, 100, .2); }
.btn--reject { background: rgba(255, 80, 80, .08); color: #ff5050; border-color: rgba(255, 80, 80, .25); }
.btn--reject:hover:not(:disabled) { background: rgba(255, 80, 80, .15); }
</style>
