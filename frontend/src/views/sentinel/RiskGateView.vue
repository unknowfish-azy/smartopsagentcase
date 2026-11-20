<template>
  <section class="risk-gate">
    <header class="page-header">
      <div>
        <p class="eyebrow">RISK GATE · P0-3 处置动作风险评估门</p>
        <h1>风险门</h1>
        <p class="muted">确定性硬规则 + 可解释评分。<code>BLOCK</code> 级拦截不可被 Kimi 或任何下游覆盖。风险门在 OperationToolService.executeInternal 渲染后、执行前拦截。</p>
      </div>
      <button type="button" class="ghost" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新' }}</button>
    </header>

    <!-- 在线测试工具 -->
    <section class="tester">
      <h2 class="tester__title">在线风险评估</h2>
      <div class="tester__form">
        <input v-model="testCommand" class="tester__input" placeholder="输入要评估的命令，如：rm -rf /tmp/logs" @keyup.enter="onTest" />
        <select v-model="testEnv" class="tester__select">
          <option value="dev">dev 环境</option>
          <option value="staging">staging 环境</option>
          <option value="prod">prod 环境</option>
        </select>
        <button type="button" class="btn btn--primary" :disabled="testing || !testCommand.trim()" @click="onTest">
          {{ testing ? '评估中…' : '评估' }}
        </button>
      </div>
      <div v-if="testResult" class="tester__result" :class="'tester__result--' + testResult.level.toLowerCase()">
        <div class="tester__level">
          <span class="level-tag" :class="'level-tag--' + testResult.level.toLowerCase()">{{ testResult.level }}</span>
          <span class="tester__score">评分 {{ testResult.score }}</span>
          <span class="tester__allowed">{{ testResult.allowed ? '允许执行' : '禁止执行' }}</span>
        </div>
        <p class="tester__reason">{{ testResult.reason }}</p>
        <p v-if="testResult.hitRules?.length" class="tester__rules">
          命中规则：<code v-for="r in testResult.hitRules" :key="r">{{ r }}</code>
        </p>
      </div>
    </section>

    <!-- 历史记录 -->
    <h2 class="section-title">评估历史</h2>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading && !items.length" class="empty">正在读取评估历史…</div>
    <div v-else-if="!items.length" class="empty">还没有风险评估记录。Agent 每次执行命令前都会自动评估。</div>

    <div v-else class="history-table">
      <div class="history-row history-row--head">
        <span>时间</span><span>等级</span><span>评分</span><span>命令</span><span>命中规则</span><span>结果</span>
      </div>
      <div v-for="row in items" :key="row.id" class="history-row" :class="'history-row--' + (row.risk_level || row.riskLevel || '').toLowerCase()">
        <span class="mono">{{ formatTime(row.created_at || row.createdAt) }}</span>
        <span><span class="level-tag" :class="'level-tag--' + (row.risk_level || row.riskLevel || '').toLowerCase()">{{ row.risk_level || row.riskLevel }}</span></span>
        <span class="mono">{{ row.risk_score ?? row.riskScore }}</span>
        <span class="history-row__cmd"><code>{{ truncate(row.command_text || row.commandText, 80) }}</code></span>
        <span class="mono">{{ row.hit_rules || row.hitRules || '—' }}</span>
        <span :class="(row.allowed ? 'text-allow' : 'text-deny')">{{ row.allowed ? '允许' : '拒绝' }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { assessRisk, listRiskHistory } from '../../api/p0Modules.ts'

const items: any= ref<any[]>([]), loading = ref(false), error = ref('')
const testCommand: any= ref(''), testEnv = ref('dev'), testing = ref(false), testResult: any = ref<any>(null)
const unwrap: any= (r: any) => r?.data ?? r

async function load(): Promise<any> {
  loading.value = true; error.value = ''
  try {
    const data: any= unwrap(await listRiskHistory(50))
    items.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (cause: any) { error.value = cause.message || '读取评估历史失败' }
  finally { loading.value = false }
}

async function onTest(): Promise<any> {
  if (!testCommand.value.trim()) return
  testing.value = true; testResult.value = null
  try {
    const data: any= unwrap(await assessRisk(testCommand.value, 'manual', { environment: testEnv.value }))
    testResult.value = data
    await load()
  } catch (cause: any) { error.value = cause.message || '评估失败' }
  finally { testing.value = false }
}

function formatTime(t: any) {
  if (!t) return '—'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}
function truncate(s: any,   n: any) { return !s ? '—' : (s.length > n ? s.slice(0, n) + '…' : s) }

onMounted(load)
</script>

<style scoped>
.risk-gate { color: var(--smart-text); }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; margin-bottom: 18px; }
.eyebrow { margin: 0 0 8px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .14em; }
.muted { color: var(--smart-muted); font-size: 12px; }
.muted code { padding: 1px 5px; background: var(--smart-surface); border-radius: 3px; font-size: 11px; }
.ghost { min-height: 30px; padding: 3px 10px; border: 1px solid var(--smart-border); border-radius: 6px; background: transparent; color: var(--smart-muted); cursor: pointer; }
.ghost:hover { color: var(--smart-text); border-color: var(--smart-primary-strong); }
.empty, .error { padding: 28px; text-align: center; color: var(--smart-muted); border: 1px dashed var(--smart-border); border-radius: 8px; }
.error { color: var(--ds-semantic-danger); border-color: var(--ds-semantic-danger); }
.section-title { margin: 24px 0 12px; font-size: 14px; color: var(--smart-text); }

/* 测试工具 */
.tester { padding: 16px; border: 1px solid var(--smart-border); border-radius: 8px; background: var(--smart-surface); }
.tester__title { margin: 0 0 12px; font-size: 13px; color: var(--smart-text); }
.tester__form { display: flex; gap: 8px; }
.tester__input { flex: 1; padding: 8px 12px; background: transparent; border: 1px solid var(--smart-border); border-radius: 6px; color: var(--smart-text); font: 12px var(--font-mono); }
.tester__input:focus { outline: none; border-color: var(--smart-primary-strong); }
.tester__select { padding: 8px 10px; background: var(--smart-surface); border: 1px solid var(--smart-border); border-radius: 6px; color: var(--smart-text); font-size: 12px; }
.btn { padding: 8px 18px; border: 1px solid transparent; border-radius: 6px; cursor: pointer; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--primary { background: var(--smart-primary-strong); color: #fff; }
.btn--primary:hover:not(:disabled) { filter: brightness(1.1); }

.tester__result { margin-top: 14px; padding: 12px; border-radius: 6px; border: 1px solid; }
.tester__result--low { background: rgba(0, 200, 100, .06); border-color: rgba(0, 200, 100, .25); }
.tester__result--medium { background: rgba(255, 180, 0, .06); border-color: rgba(255, 180, 0, .25); }
.tester__result--high { background: rgba(255, 120, 0, .08); border-color: rgba(255, 120, 0, .3); }
.tester__result--block { background: rgba(255, 80, 80, .1); border-color: rgba(255, 80, 80, .4); }
.tester__level { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.tester__score { font: 11px var(--font-mono); color: var(--smart-muted); }
.tester__allowed { margin-left: auto; font: 11px var(--font-mono); }
.tester__reason { margin: 6px 0; font-size: 12px; }
.tester__rules { margin: 6px 0 0; font: 10px var(--font-mono); color: var(--smart-muted); }
.tester__rules code { padding: 1px 5px; background: var(--smart-border); border-radius: 3px; margin-right: 4px; }

/* 等级标签 */
.level-tag { padding: 2px 8px; border-radius: 4px; font: 10px var(--font-mono); letter-spacing: .08em; }
.level-tag--low { background: rgba(0, 200, 100, .15); color: #00c864; }
.level-tag--medium { background: rgba(255, 180, 0, .15); color: #ffb400; }
.level-tag--high { background: rgba(255, 120, 0, .18); color: #ff7800; }
.level-tag--block { background: rgba(255, 80, 80, .2); color: #ff5050; }

/* 历史表格 */
.history-table { border: 1px solid var(--smart-border); border-radius: 8px; overflow: hidden; }
.history-row { display: grid; grid-template-columns: 150px 80px 60px 1fr 180px 60px; gap: 10px; padding: 10px 14px; align-items: center; border-bottom: 1px solid var(--smart-border); font-size: 12px; }
.history-row:last-child { border-bottom: none; }
.history-row--head { background: var(--smart-surface); color: var(--smart-muted); font: 10px var(--font-mono); letter-spacing: .08em; }
.history-row--block { background: rgba(255, 80, 80, .04); }
.history-row--high { background: rgba(255, 120, 0, .03); }
.history-row__cmd code { font: 11px var(--font-mono); color: var(--smart-text); word-break: break-all; }
.mono { font: 10px var(--font-mono); color: var(--smart-muted); }
.text-allow { color: #00c864; font: 11px var(--font-mono); }
.text-deny { color: #ff5050; font: 11px var(--font-mono); }
</style>
