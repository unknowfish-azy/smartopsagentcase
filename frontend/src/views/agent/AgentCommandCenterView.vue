<template>
  <div ref="agentShellRef" class="agent-shell" :data-theme="resolvedTheme">
    <CanvasAmbientField v-if="!isMobile" class="agent-ambient" :palette-root="agentShellRef" :star-multiplier="1.8" connect-particles :connect-max-dist="130" />
    <div v-if="!isMobile" class="agent-aurora" aria-hidden="true"></div>
    <MeteorShower v-if="!isMobile" class="agent-meteors" />
    <div class="agent-mask" aria-hidden="true"></div>

  <AgentSkillGuidance />
  <div class="page agent-page">
    <header>
      <div>
        <p class="eyebrow">AI AGENT · 决策闭环</p>
        <h1>Agent Command Center</h1>
        <p>分析 → 记忆 → 决策 → 复盘 → 学习回写，全部基于真实闭环记录</p>
      </div>
      <div class="actions">
        <button type="button" @click="openCreate">新建闭环</button>
        <button type="button" :disabled="loading" :aria-busy="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>
    </header>

    <el-alert v-if="error" :title="error" type="error" show-icon @close="error = ''" />

    <section class="stats">
      <article><span>闭环总数</span><strong>{{ stats.total ?? 0 }}</strong></article>
      <article><span>已复盘</span><strong>{{ stats.reviewed ?? 0 }}</strong></article>
      <article><span>复盘解决率</span><strong>{{ resolveRate }}</strong></article>
      <article><span>记忆回写次数</span><strong>{{ stats.learnedCount ?? 0 }}</strong></article>
    </section>

    <section class="pipeline">
      <div v-for="(stage, index) in stages" :key="stage.key" class="stage"
           :class="{ active: stageIndex >= index, current: stageIndex === index }">
        <b>{{ index + 1 }} · {{ stage.name }}</b>
        <small>{{ stage.desc }}</small>
      </div>
    </section>

    <div class="workspace">
      <aside class="loop-list">
        <div class="list-head"><h2>闭环记录</h2><span>{{ loops.length }}</span></div>
        <button v-for="loop in loops" :key="loop.id" type="button" class="loop-item"
                :class="{ active: loop.id === selectedId }" @click="select(loop)">
          <span class="loop-title">{{ loop.title }}</span>
          <span class="loop-meta">
            <em :class="loop.sourceType === 'INSPECTOR' ? 'src-auto' : 'src-manual'">{{ sourceLabel(loop.sourceType) }}</em>
            <em :class="'stage-' + loop.stage">{{ stageLabel(loop.stage) }}</em>
            <em :class="'sev-' + loop.severity">{{ loop.severity }}</em>
          </span>
          <small>{{ formatTime(loop.updatedAt) }}</small>
        </button>
        <AppEmpty v-if="!loops.length && !loading" description="暂无闭环记录，可从 Inspector 自动派生或手工新建" />
      </aside>

      <article v-if="detail" class="detail">
        <div class="detail-head">
          <div>
            <h2>{{ detail.title }}</h2>
            <p>{{ detail.incidentKey }} · {{ sourceLabel(detail.sourceType) }} · {{ formatTime(detail.createdAt) }}</p>
          </div>
          <div class="head-right">
            <RouterLink v-if="detail.sourceType === 'INSPECTOR'" class="trace-link"
                        :to="{ path: '/agent/trace', query: { inspectionId: detail.sourceRef } }">查看执行轨迹</RouterLink>
            <span class="outcome" :class="'outcome-' + (detail.outcome || 'PENDING')">{{ outcomeLabel(detail.outcome) }}</span>
          </div>
        </div>

        <section class="block">
          <h3>① 分析</h3>
          <p v-if="detail.symptom"><span class="key">现象</span>{{ detail.symptom }}</p>
          <p v-if="detail.analysis"><span class="key">分析</span>{{ detail.analysis }}</p>
          <ul v-if="detail.evidence?.length" class="evidence">
            <li v-for="(item, index) in detail.evidence" :key="index">
              <strong>{{ item.content }}</strong>
              <small>{{ item.source || '未知来源' }}<template v-if="item.score"> · 相关度 {{ Math.round(item.score * 100) }}%</template></small>
            </li>
          </ul>
          <p v-else class="muted">暂无证据</p>
        </section>

        <section class="block">
          <h3>② 记忆召回</h3>
          <ul v-if="detail.memories?.length" class="memories">
            <li v-for="memory in detail.memories" :key="memory.id">
              <div><strong>{{ memory.preferredAction }}</strong><small>{{ memory.incidentKey }} · {{ memory.memoryType }}</small></div>
              <span class="confidence">置信度 {{ Math.round(memory.confidence * 100) }}% · 证据 {{ memory.evidenceCount }} 次</span>
            </li>
          </ul>
          <p v-else class="muted">尚未召回历史处置记忆</p>
          <button v-if="stageIndex < 2" type="button" class="ghost" :disabled="submitting" @click="recall">召回记忆</button>
        </section>

        <section class="block">
          <h3>③ 决策</h3>
          <p v-if="detail.recommendation"><span class="key">建议</span>{{ detail.recommendation }}</p>
          <p v-if="detail.decision"><span class="key">决策</span>{{ detail.decision }}</p>
          <p v-if="detail.decisionBasis"><span class="key">依据</span>{{ detail.decisionBasis }}</p>
          <p v-if="detail.requiresHuman" class="warn">该处置需要人工审批后才能执行</p>
          <div v-if="stageIndex < 3" class="form">
            <el-input v-model="decideForm.recommendation" placeholder="处置建议（可留空沿用召回建议）" />
            <el-input v-model="decideForm.decision" placeholder="决策结论" />
            <el-input v-model="decideForm.decisionBasis" type="textarea" :rows="2" placeholder="决策依据：证据、风险、影响面" />
            <el-checkbox v-model="decideForm.requiresHuman">需要人工审批</el-checkbox>
            <button type="button" :disabled="submitting" @click="submitDecide">提交决策</button>
          </div>
        </section>

        <section class="block">
          <h3>④ 复盘</h3>
          <p v-if="detail.outcome" class="outcome-line">
            结论：{{ outcomeLabel(detail.outcome) }}<template v-if="detail.reviewedAt"> · {{ formatTime(detail.reviewedAt) }}</template>
          </p>
          <p v-if="detail.lesson"><span class="key">经验</span>{{ detail.lesson }}</p>
          <div v-if="stageIndex < 4" class="form">
            <el-radio-group v-model="reviewForm.outcome">
              <el-radio value="RESOLVED">已解决</el-radio>
              <el-radio value="UNRESOLVED">未解决</el-radio>
            </el-radio-group>
            <el-input v-model="reviewForm.lesson" type="textarea" :rows="2" placeholder="复盘经验：根因、有效动作、下次可复用点" />
            <button type="button" :disabled="submitting" @click="submitReview">提交复盘并学习</button>
          </div>
        </section>

        <section class="block">
          <h3>⑤ 学习回写</h3>
          <ul v-if="detail.learnedMemories?.length" class="memories">
            <li v-for="memory in detail.learnedMemories" :key="memory.id">
              <div><strong>{{ memory.preferredAction }}</strong><small>{{ memory.status }}</small></div>
              <span class="confidence">置信度 {{ Math.round(memory.confidence * 100) }}% · 证据 {{ memory.evidenceCount }} 次</span>
            </li>
          </ul>
          <p v-else class="muted">复盘后会真实回写 operator_memory：解决则置信度上调，未解决则降权或失效</p>
        </section>
      </article>

      <AppEmpty v-else-if="!loading" description="请选择一条闭环记录" />
    </div>
  </div>

  <el-dialog v-model="createVisible" title="新建决策闭环" width="620px">
    <div class="create-form">
      <el-input v-model="createForm.incidentKey" placeholder="事件标识，例如 nginx-502 或 TASK-1024" />
      <el-input v-model="createForm.title" placeholder="标题，例如 Nginx 502 排查" />
      <el-select v-model="createForm.severity" placeholder="严重级别">
        <el-option v-for="level in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']" :key="level" :label="level" :value="level" />
      </el-select>
      <el-input v-model="createForm.symptom" type="textarea" :rows="2" placeholder="现象：服务、时间、报错表现" />
      <el-input v-model="createForm.analysis" type="textarea" :rows="2" placeholder="初步分析：可能根因、影响面" />
      <el-input v-model="createForm.evidenceText" type="textarea" :rows="3" placeholder="证据：每行一条，例如 nginx error.log 出现 upstream timeout" />
    </div>
    <template #footer>
      <button type="button" class="ghost" @click="createVisible = false">取消</button>
      <button type="button" :disabled="submitting" @click="submitCreate">创建</button>
    </template>
  </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, defineAsyncComponent } from 'vue'
import AgentSkillGuidance from '../../components/agent/AgentSkillGuidance.vue'
import AppEmpty from '../../components/common/AppEmpty.vue'
import { resolvedTheme as _resolvedTheme } from '../../theme.js'
import {
  createDecisionLoop,
  decideDecisionLoop,
  getDecisionLoop,
  getDecisionLoopStats,
  getDecisionLoops,
  recallDecisionMemories,
  reviewDecisionLoop
} from '../../api/decisionLoop'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))
const MeteorShower = defineAsyncComponent(() => import('../../components/common/MeteorShower.vue'))

const agentShellRef = ref(null)
const resolvedTheme = computed(() => _resolvedTheme.value)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

const stages = [
  { key: 'ANALYZE', name: '分析', desc: '现象、证据、影响面' },
  { key: 'MEMORIZE', name: '记忆', desc: '召回同类历史处置' },
  { key: 'DECIDE', name: '决策', desc: '处置建议与风险审批' },
  { key: 'REVIEW', name: '复盘', desc: '处置后验证结论' },
  { key: 'LEARNED', name: '学习', desc: '置信度回写记忆' }
]
const stageOrder = stages.map(stage => stage.key)

const loops = ref([])
const stats = ref({})
const detail = ref(null)
const selectedId = ref('')
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const createVisible = ref(false)

const decideForm = reactive({ recommendation: '', decision: '', decisionBasis: '', requiresHuman: false })
const reviewForm = reactive({ outcome: 'RESOLVED', lesson: '' })
const createForm = reactive({ incidentKey: '', title: '', severity: 'MEDIUM', symptom: '', analysis: '', evidenceText: '' })

const stageIndex = computed(() => {
  const index = stageOrder.indexOf(detail.value?.stage)
  return index < 0 ? 0 : index
})
const resolveRate = computed(() => {
  const rate = Number(stats.value.resolveRate || 0)
  return `${Math.round(rate * 100)}%`
})

const sourceLabel = type => (type === 'INSPECTOR' ? '自动派生' : '手工创建')
const stageLabel = stage => stages.find(item => item.key === stage)?.name || stage || '分析'
const outcomeLabel = outcome => (outcome === 'RESOLVED' ? '已解决' : outcome === 'UNRESOLVED' ? '未解决' : '待复盘')
const formatTime = value => (value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [listResponse, statsResponse] = await Promise.all([getDecisionLoops(30), getDecisionLoopStats()])
    loops.value = listResponse.data || []
    stats.value = statsResponse.data || {}
    if (loops.value.length) {
      const keep = loops.value.find(item => item.id === selectedId.value)
      await select(keep || loops.value[0])
    } else {
      detail.value = null
      selectedId.value = ''
    }
  } catch (err) {
    error.value = err.message || '决策闭环服务不可用'
  } finally {
    loading.value = false
  }
}

async function select(loop) {
  selectedId.value = loop.id
  try {
    applyDetail((await getDecisionLoop(loop.id)).data)
  } catch (err) {
    error.value = err.message || '闭环详情加载失败'
  }
}

function applyDetail(data) {
  detail.value = data || null
  decideForm.recommendation = data?.recommendation || ''
  decideForm.decision = data?.decision || ''
  decideForm.decisionBasis = data?.decisionBasis || ''
  decideForm.requiresHuman = Boolean(data?.requiresHuman)
  reviewForm.outcome = data?.outcome === 'UNRESOLVED' ? 'UNRESOLVED' : 'RESOLVED'
  reviewForm.lesson = data?.lesson || ''
}

async function recall() {
  submitting.value = true
  error.value = ''
  try {
    applyDetail((await recallDecisionMemories(selectedId.value)).data)
    await load()
  } catch (err) {
    error.value = err.message || '记忆召回失败'
  } finally {
    submitting.value = false
  }
}

async function submitDecide() {
  submitting.value = true
  error.value = ''
  try {
    applyDetail((await decideDecisionLoop(selectedId.value, { ...decideForm })).data)
    await load()
  } catch (err) {
    error.value = err.message || '提交决策失败'
  } finally {
    submitting.value = false
  }
}

async function submitReview() {
  submitting.value = true
  error.value = ''
  try {
    applyDetail((await reviewDecisionLoop(selectedId.value, { ...reviewForm })).data)
    await load()
  } catch (err) {
    error.value = err.message || '提交复盘失败'
  } finally {
    submitting.value = false
  }
}

function openCreate() {
  Object.assign(createForm, { incidentKey: '', title: '', severity: 'MEDIUM', symptom: '', analysis: '', evidenceText: '' })
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.incidentKey.trim() || !createForm.title.trim()) {
    error.value = '事件标识与标题不能为空'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const evidence = createForm.evidenceText.split('\n').map(item => item.trim()).filter(Boolean)
    const response = await createDecisionLoop({
      incidentKey: createForm.incidentKey.trim(),
      title: createForm.title.trim(),
      severity: createForm.severity,
      symptom: createForm.symptom,
      analysis: createForm.analysis,
      evidence
    })
    createVisible.value = false
    selectedId.value = response.data?.id || ''
    await load()
  } catch (err) {
    error.value = err.message || '创建闭环失败'
  } finally {
    submitting.value = false
  }
}

onMounted(() => { updateMobile(); window.addEventListener('resize', updateMobile); load() })
onBeforeUnmount(() => window.removeEventListener('resize', updateMobile))
</script>

<style scoped>
.page{display:grid;gap:18px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
h1{margin:0;font-size:30px}
header p{color:var(--smart-muted);margin:6px 0 0}
.eyebrow{color:var(--smart-primary);font-weight:700;margin:0 0 6px}
.actions{display:flex;gap:8px}
.actions button,.form button,.ghost,.detail-head+.block button{padding:9px 14px;border:1px solid var(--smart-border);background:var(--smart-surface);color:var(--smart-text);border-radius:8px;cursor:pointer;min-height:38px}
.actions button:hover:not(:disabled),.form button:hover:not(:disabled),.ghost:hover:not(:disabled){border-color:var(--smart-primary-strong)}
button:disabled{cursor:wait;opacity:.65}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stats article{padding:16px 18px;background:var(--smart-surface);border:1px solid var(--smart-border);border-radius:12px}
.stats span{display:block;color:var(--smart-muted);font-size:13px}
.stats strong{display:block;margin-top:8px;font-size:26px}
.pipeline{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.stage{padding:14px;background:var(--smart-surface);border:1px dashed var(--smart-border);border-radius:10px;display:grid;gap:4px;opacity:.55}
.stage b{font-size:14px}
.stage small{color:var(--smart-muted)}
.stage.active{opacity:1;border-style:solid;background:var(--smart-primary-soft)}
.stage.current{border-color:var(--smart-primary-strong);box-shadow:0 0 0 2px var(--smart-primary-soft) inset}
.workspace{display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start}
.loop-list{padding:16px;background:var(--smart-surface);border:1px solid var(--smart-border);border-radius:12px;display:grid;gap:8px;max-height:70vh;overflow:auto}
.list-head{display:flex;justify-content:space-between;align-items:baseline}
.list-head h2{margin:0;font-size:16px}
.list-head span{color:var(--smart-muted);font-size:13px}
.loop-item{display:grid;gap:6px;text-align:left;padding:12px;border:1px solid var(--smart-border);border-radius:9px;background:transparent;color:var(--smart-text);cursor:pointer}
.loop-item:hover{border-color:var(--smart-primary-strong)}
.loop-item.active{border-color:var(--smart-primary-strong);background:var(--smart-primary-soft)}
.loop-title{font-weight:600;overflow-wrap:anywhere}
.loop-meta{display:flex;gap:6px;flex-wrap:wrap}
.loop-meta em{font-style:normal;font-size:11px;padding:2px 6px;border-radius:5px;background:var(--smart-primary-soft);color:var(--smart-muted)}
.loop-meta .src-auto{color:var(--smart-success)}
.loop-meta .sev-HIGH,.loop-meta .sev-CRITICAL{color:var(--smart-danger)}
.loop-item small{color:var(--smart-muted);font-size:11px}
.detail{padding:18px;background:var(--smart-surface);border:1px solid var(--smart-border);border-radius:12px;display:grid;gap:14px}
.detail-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.detail-head h2{margin:0;font-size:20px}
.detail-head p{margin:6px 0 0;color:var(--smart-muted);font-size:12px}
.head-right{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end}
.trace-link{font-size:12px;color:var(--smart-primary-strong);text-decoration:none;border-bottom:1px dashed currentColor}
.trace-link:hover{opacity:.8}
.outcome{font-size:12px;padding:4px 10px;border-radius:999px;background:var(--smart-primary-soft);color:var(--smart-muted);white-space:nowrap}
.outcome-RESOLVED{color:var(--smart-success)}
.outcome-UNRESOLVED{color:var(--smart-danger)}
.block{border-top:1px solid var(--smart-border);padding-top:12px;display:grid;gap:8px}
.block h3{margin:0;font-size:15px}
.block p{margin:0;line-height:1.6;overflow-wrap:anywhere}
.block .key{display:inline-block;min-width:52px;color:var(--smart-muted);font-size:12px;margin-right:8px}
.muted{color:var(--smart-muted)}
.warn{color:var(--smart-warning);font-size:13px}
.outcome-line{color:var(--smart-text)}
.evidence,.memories{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.evidence li,.memories li{padding:10px 12px;border:1px solid var(--smart-border);border-radius:8px;background:var(--smart-primary-soft);display:grid;gap:4px}
.memories li{grid-template-columns:1fr auto;align-items:center}
.memories div{display:grid;gap:3px}
.evidence small,.memories small{color:var(--smart-muted);font-size:12px}
.confidence{color:var(--smart-muted);font-size:12px;white-space:nowrap}
.form{display:grid;gap:8px;margin-top:4px}
.create-form{display:grid;gap:10px}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.pipeline{grid-template-columns:repeat(2,1fr)}.workspace{grid-template-columns:1fr}}

/* === 启佑风格背景层 === */
.agent-shell{position:relative;min-height:calc(100vh - 64px);overflow:hidden;background:radial-gradient(ellipse at 80% 10%,color-mix(in srgb,var(--smart-primary-strong) 10%,transparent) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,color-mix(in srgb,var(--ds-semantic-success) 7%,transparent) 0%,transparent 50%),var(--smart-bg)}
.agent-shell[data-theme='light']{background:radial-gradient(ellipse at 80% 10%,color-mix(in srgb,var(--smart-primary) 7%,transparent) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,color-mix(in srgb,var(--ds-semantic-success) 4%,transparent) 0%,transparent 50%),var(--smart-bg)}
.agent-ambient{position:absolute;inset:0;z-index:0;opacity:.48;pointer-events:none}
.agent-meteors{position:absolute;inset:0;z-index:0;opacity:.35;pointer-events:none}
.agent-aurora{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at 75% 15%,rgba(122,215,245,.22) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(63,185,80,.16) 0%,transparent 45%);filter:blur(24px);background-size:240% 240%;animation:agent-drift 22s ease-in-out infinite alternate}
.agent-aurora::after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(122,215,245,.35),transparent 70%);filter:blur(18px);animation:agent-sweep 32s ease-in-out infinite}
.agent-shell[data-theme='light'] .agent-aurora{background:radial-gradient(ellipse at 75% 15%,rgba(26,110,154,.14) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(26,127,55,.10) 0%,transparent 45%)}
.agent-shell[data-theme='light'] .agent-aurora::after{background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(26,110,154,.22),transparent 70%)}
@keyframes agent-drift{0%{background-position:0% 0%,100% 100%;transform:translate3d(0,0,0)}100%{background-position:30% 10%,70% 90%;transform:translate3d(-2%,2%,0)}}
@keyframes agent-sweep{0%,100%{opacity:.55;transform:translate3d(0,0,0)}50%{opacity:1;transform:translate3d(-8%,4%,0)}}
@media(prefers-reduced-motion:reduce){.agent-aurora,.agent-aurora::after{animation:none}}
.agent-mask{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(4,11,22,.42) 100%)}
.agent-shell[data-theme='light'] .agent-mask{background:radial-gradient(ellipse at center,transparent 40%,rgba(234,243,250,.42) 100%)}
.agent-shell>.agent-page,.agent-shell>AgentSkillGuidance{position:relative;z-index:1}
</style>
