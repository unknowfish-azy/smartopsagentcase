<template>
  <section class="ensp-lab">
    <header class="page-header">
      <div>
        <p class="eyebrow">HCNA / eNSP LAB</p>
        <h1>网络设备安装与调试实验台</h1>
        <p class="muted">华为《网络设备安装与调试（eNSP 模拟器）（第二版）》结构化实验知识库：知识点、实验步骤、拓扑图与配置校验。</p>
      </div>
      <div class="stats" v-if="overview">
        <span v-for="stat in statChips" :key="stat.label" class="stat">{{ stat.value }}<small>{{ stat.label }}</small></span>
      </div>
    </header>

    <nav class="tabs" aria-label="功能切换">
      <button v-for="t in TABS" :key="t.id" :class="{ active: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
    </nav>

    <!-- ===================== 实验台 ===================== -->
    <div v-if="tab === 'lab'" class="lab-layout">
      <aside class="lab-side">
        <label class="field">
          <span>项目 / 模块</span>
          <select v-model="moduleFilter">
            <option value="">全部项目</option>
            <option v-for="m in modules" :key="m.module.id" :value="m.module.id">{{ m.module.code }} {{ m.module.title }}</option>
          </select>
        </label>
        <p class="side-count">{{ filteredExperiments.length }} 个实验</p>
        <ul class="exp-list">
          <li v-for="e in filteredExperiments" :key="e.experiment.id"
              :class="{ active: currentId === e.experiment.id }" @click="openExperiment(e.experiment.id)">
            <b>{{ e.experiment.code }}</b>
            <span>{{ e.experiment.title }}</span>
            <em>{{ e.experiment.difficulty }} · {{ e.experiment.durationMin }}分钟 · {{ e.experiment.steps.length }}步</em>
          </li>
          <li v-if="!filteredExperiments.length" class="empty">该项目下暂无实验</li>
        </ul>
      </aside>

      <div class="lab-main">
        <template v-if="detail">
          <div class="panel head">
            <div>
              <h2>{{ detail.experiment.code }} {{ detail.experiment.title }}</h2>
              <p class="muted">{{ detail.moduleTitle }} · 难度 {{ detail.experiment.difficulty }} · 建议 {{ detail.experiment.durationMin }} 分钟</p>
            </div>
            <span class="tag" :class="difficultyClass">{{ detail.experiment.difficulty }}</span>
          </div>

          <div class="grid two">
            <article class="panel">
              <h3>实验目标</h3>
              <ul class="goals">
                <li v-for="(g, i) in detail.experiment.goals" :key="i">{{ g }}</li>
              </ul>
              <h3>设备清单</h3>
              <table>
                <thead><tr><th>名称</th><th>型号</th><th>角色</th></tr></thead>
                <tbody>
                  <tr v-for="d in detail.experiment.devices" :key="d.name"><td>{{ d.name }}</td><td>{{ d.model }}</td><td>{{ d.role }}</td></tr>
                </tbody>
              </table>
              <template v-if="detail.answers.length">
                <h3>参考答案</h3>
                <ul class="answers">
                  <li v-for="a in detail.answers" :key="a.id"><code>{{ a.deviceHint || a.id }}</code></li>
                </ul>
              </template>
            </article>

            <article class="panel topo-panel">
              <h3>eNSP 拓扑图 <small class="muted" v-if="detail.topology">（{{ detail.topology.devices.length }} 台设备 / {{ detail.topology.links.length }} 条链路）</small></h3>
              <TopologyGraph v-if="detail.topology" :graph="detail.topology" />
              <p v-else class="muted">该实验未关联 .topo 拓扑文件。</p>
            </article>
          </div>

          <article class="panel">
            <h3>实验步骤</h3>
            <ol class="steps">
              <li v-for="step in detail.experiment.steps" :key="step.seq">
                <div class="step-title">
                  <span class="seq">{{ step.seq }}</span>
                  <b>{{ step.title }}</b>
                  <small>{{ step.device }} · {{ modeLabel(step.mode) }}</small>
                </div>
                <p v-if="step.hint" class="hint">提示：{{ step.hint }}</p>
                <div v-if="step.commands && step.commands.length" class="cmds">
                  <code v-for="(c, i) in step.commands" :key="i">{{ c }}</code>
                </div>
                <p v-if="step.expect" class="expect">预期：{{ step.expect }}</p>
              </li>
            </ol>
          </article>

          <article class="panel" v-if="detail.experiment.verification && detail.experiment.verification.length">
            <h3>验收命令</h3>
            <table>
              <thead><tr><th>命令</th><th>预期结果</th></tr></thead>
              <tbody>
                <tr v-for="(v, i) in detail.experiment.verification" :key="i"><td><code>{{ v.command }}</code></td><td>{{ v.expect }}</td></tr>
              </tbody>
            </table>
          </article>

          <article class="panel" v-if="detail.experiment.commonErrors && detail.experiment.commonErrors.length">
            <h3>常见错误</h3>
            <ul class="errors"><li v-for="(e, i) in detail.experiment.commonErrors" :key="i">{{ e }}</li></ul>
          </article>

          <article class="panel validator">
            <h3>配置校验</h3>
            <p class="muted">把你在 eNSP 里输入的配置整段粘贴进来（可带设备提示符），系统按教材命令规则逐行判定并与本实验期望命令比对。</p>
            <textarea v-model="configText" rows="9" placeholder="<Huawei>system-view&#10;[Huawei]sysname SWA&#10;..."></textarea>
            <div class="actions">
              <button class="primary" :disabled="validating" @click="runValidation('experiment')">按实验比对</button>
              <button class="ghost" :disabled="validating" @click="runValidation('syntax')">仅语法校验</button>
              <button class="ghost" :disabled="validating" @click="loadExpected">一键填入期望命令</button>
            </div>

            <div v-if="report" class="report">
              <div class="score-bar"><span :style="{ width: report.score + '%' }" :class="{ pass: report.pass }"></span></div>
              <p class="score-line">得分 <b>{{ report.score }}</b> / 100 · 判定 <b :class="report.pass ? 'ok' : 'bad'">{{ report.pass ? '通过' : '未通过' }}</b> · 视图 <code>{{ report.context }}</code></p>

              <div v-if="report.missing.length" class="chips">
                <span class="chip bad" v-for="(m, i) in report.missing" :key="'m' + i">缺失：{{ m }}</span>
              </div>
              <div v-if="report.extra.length" class="chips">
                <span class="chip warn" v-for="(e, i) in report.extra.slice(0, 12)" :key="'e' + i">多余：{{ e }}</span>
              </div>

              <div v-if="report.steps.length" class="step-progress">
                <p v-for="s in report.steps" :key="s.seq" :class="s.done ? 'done' : 'todo'">
                  {{ s.done ? '✓' : '○' }} 步骤 {{ s.seq }} {{ s.title }}
                </p>
              </div>

              <ul v-if="report.suggestions.length" class="suggestions">
                <li v-for="(s, i) in report.suggestions" :key="i">{{ s }}</li>
              </ul>

              <table class="lines">
                <thead><tr><th>#</th><th>输入</th><th>状态</th><th>说明</th></tr></thead>
                <tbody>
                  <tr v-for="l in report.lines" :key="l.line + l.input" :class="'st-' + l.status.toLowerCase()">
                    <td>{{ l.line || '-' }}</td>
                    <td><code>{{ l.input }}</code></td>
                    <td>{{ statusLabel(l.status) }}</td>
                    <td>{{ l.message }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </template>
        <div v-else class="panel empty">从左侧选择一个实验开始。</div>
      </div>
    </div>

    <!-- ===================== 知识库 ===================== -->
    <div v-else-if="tab === 'knowledge'" class="lab-layout">
      <aside class="lab-side">
        <label class="field">
          <span>关键词</span>
          <input v-model="keyword" placeholder="如 VLAN / OSPF / NAT" @input="loadKnowledge" />
        </label>
        <label class="field">
          <span>分类</span>
          <select v-model="category" @change="loadKnowledge">
            <option value="">全部分类</option>
            <option v-for="c in overview?.categories || []" :key="c.id" :value="c.id">{{ c.label || c.id }}</option>
          </select>
        </label>
        <p class="side-count">{{ knowledgeList.length }} 个知识点</p>
        <ul class="point-list">
          <li v-for="p in knowledgeList" :key="p.id" :class="{ active: pointId === p.id }" @click="pointId = p.id">
            <b>{{ p.title }}</b>
            <em>{{ p.category }}</em>
          </li>
        </ul>
      </aside>
      <div class="lab-main">
        <article v-if="currentPoint" class="panel">
          <h2>{{ currentPoint.title }}</h2>
          <p class="muted">{{ currentPoint.moduleId }} · 分类 {{ currentPoint.category }}</p>
          <h3>概述</h3>
          <p class="text">{{ currentPoint.summary }}</p>
          <h3>关键命令</h3>
          <div class="cmds" v-if="currentPoint.keyCommands && currentPoint.keyCommands.length">
            <code v-for="(c, i) in currentPoint.keyCommands" :key="i">{{ c }}</code>
          </div>
          <h3>相关实验</h3>
          <ul class="answers" v-if="currentPoint.experiments && currentPoint.experiments.length">
            <li v-for="(e, i) in currentPoint.experiments" :key="i">{{ e }}</li>
          </ul>
          <p v-else class="muted">暂无关联实验</p>
          <h3>验收标准</h3>
          <p class="text">{{ currentPoint.acceptance }}</p>
        </article>
        <div v-else class="panel empty">从左侧选择一个知识点。</div>
      </div>
    </div>

    <!-- ===================== 命令校验 ===================== -->
    <div v-else class="lab-layout">
      <aside class="lab-side">
        <label class="field">
          <span>当前视图</span>
          <select v-model="checkContext">
            <option v-for="c in ruleDoc?.contexts || []" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
        <input v-model="checkLine" class="check-input" placeholder="输入一条命令，如 interface Vlanif 10" @keyup.enter="runCheck" />
        <button class="primary" @click="runCheck">校验</button>
        <div v-if="checkResult" class="check-result" :class="'st-' + checkResult.status.toLowerCase()">
          <b>{{ statusLabel(checkResult.status) }}</b>
          <p>{{ checkResult.message }}</p>
          <p class="muted">执行后视图：<code>{{ checkResult.contextAfter }}</code></p>
        </div>
        <p class="side-count">规则数 {{ ruleDoc?.rules?.length || 0 }}</p>
      </aside>
      <div class="lab-main">
        <article class="panel">
          <h3>命令规则库</h3>
          <table>
            <thead><tr><th>命令</th><th>适用视图</th><th>说明 / 示例</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in filteredRules" :key="i">
                <td><code>{{ r.cmd }}</code></td>
                <td>{{ (r.contexts && r.contexts.length) ? r.contexts.join(', ') : '任意' }}</td>
                <td>{{ r.desc }}<br /><small class="muted">{{ r.example }}</small></td>
              </tr>
            </tbody>
          </table>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  getEnspOverview, getEnspModules, getEnspKnowledge, getEnspExperiments,
  getEnspExperiment, getEnspCommands, validateEnspConfig, validateEnspExperiment
} from '../../api/ensp'
import TopologyGraph from '../../components/study/TopologyGraph.vue'

const TABS = [
  { id: 'lab', label: '实验台' },
  { id: 'knowledge', label: '知识库' },
  { id: 'check', label: '命令校验' }
]

const tab = ref('lab')
const overview = ref(null)
const modules = ref([])
const experiments = ref([])
const detail = ref(null)
const currentId = ref('')
const moduleFilter = ref('')
const validating = ref(false)
const configText = ref('')
const report = ref(null)

const keyword = ref('')
const category = ref('')
const knowledgeList = ref([])
const pointId = ref('')

const ruleDoc = ref(null)
const checkContext = ref('user')
const checkLine = ref('')
const checkResult = ref(null)

const statChips = computed(() => {
  const c = overview.value?.counts
  if (!c) return []
  return [
    { label: '项目', value: c.modules },
    { label: '知识点', value: c.knowledgePoints },
    { label: '实验', value: c.experiments },
    { label: '步骤', value: c.steps },
    { label: '拓扑', value: c.topologies }
  ]
})

const filteredExperiments = computed(() => {
  const list = experiments.value.map(e => ({
    ...e,
    _key: `${e.moduleTitle}/${e.experiment.code}/${e.experiment.title}`
  }))
  if (!moduleFilter.value) return list
  return list.filter(e => e.experiment.moduleId === moduleFilter.value)
})

const difficultyClass = computed(() => {
  const d = detail.value?.experiment?.difficulty || ''
  return 'd-' + String(d).toLowerCase()
})

const currentPoint = computed(() => knowledgeList.value.find(p => p.id === pointId.value))

const filteredRules = computed(() => {
  const rules = ruleDoc.value?.rules || []
  if (!checkContext.value) return rules
  return rules.filter(r => !r.contexts || !r.contexts.length || r.contexts.includes(checkContext.value))
})

function modeLabel(mode) {
  return ({ system: '系统视图', interface: '接口视图', user: '用户视图', acl: 'ACL 视图',
            ospf: 'OSPF 视图', rip: 'RIP 视图', dhcp: 'DHCP 地址池', aaa: 'AAA 视图',
            vlan: 'VLAN 视图', wlan: 'WLAN 视图' })[mode] || mode || '-'
}

function statusLabel(status) {
  return ({ OK: '合法', UNKNOWN: '未识别', WRONG_CONTEXT: '视图错误', IGNORED: '忽略' })[status] || status
}

async function openExperiment(id) {
  currentId.value = id
  detail.value = null
  report.value = null
  configText.value = ''
  const res = await getEnspExperiment(id)
  detail.value = res.data?.data ?? res.data
}

async function runValidation(kind) {
  const lines = configText.value.split(/\r?\n/).filter(l => l.trim())
  if (!lines.length) return
  validating.value = true
  try {
    const res = kind === 'experiment'
      ? await validateEnspExperiment(currentId.value, lines)
      : await validateEnspConfig(lines, 'user')
    report.value = res.data?.data ?? res.data
  } finally {
    validating.value = false
  }
}

function loadExpected() {
  if (!detail.value) return
  const lines = detail.value.experiment.steps.flatMap(s => s.commands || [])
  configText.value = lines.join('\n')
  report.value = null
}

async function loadKnowledge() {
  const res = await getEnspKnowledge({
    moduleId: moduleFilter.value || undefined,
    category: category.value || undefined,
    keyword: keyword.value || undefined
  })
  knowledgeList.value = res.data?.data ?? res.data ?? []
  pointId.value = knowledgeList.value[0]?.id || ''
}

async function runCheck() {
  if (!checkLine.value.trim()) return
  const res = await validateEnspConfig([checkLine.value], checkContext.value)
  const r = res.data?.data ?? res.data
  checkResult.value = r.lines?.[0] || null
}

onMounted(async () => {
  const [ov, mod, exp, cmds] = await Promise.all([
    getEnspOverview(), getEnspModules(), getEnspExperiments(), getEnspCommands()
  ])
  overview.value = ov.data?.data ?? ov.data
  modules.value = mod.data?.data ?? mod.data ?? []
  experiments.value = exp.data?.data ?? exp.data ?? []
  ruleDoc.value = cmds.data?.data ?? cmds.data
  await loadKnowledge()
  if (experiments.value.length) {
    await openExperiment(experiments.value[0].experiment.id)
  }
})
</script>

<style scoped>
.ensp-lab{max-width:1400px;margin:0 auto;padding:clamp(16px,3vw,32px);color:var(--smart-text);overflow-wrap:anywhere}
.page-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}
.eyebrow{font:10px var(--font-mono);letter-spacing:.12em;color:var(--smart-primary-strong)}
h1{margin:8px 0;font-size:clamp(22px,3vw,28px)}
h2{margin:0 0 6px;font-size:18px}
h3{margin:14px 0 10px;font-size:14px}
.muted{color:var(--smart-muted);font-size:12px;line-height:1.7}
.stats{display:flex;gap:8px;flex-wrap:wrap}
.stat{min-width:72px;border:1px solid var(--smart-border);border-radius:9px;padding:8px 12px;background:var(--smart-surface);font-weight:700;font-size:18px;display:flex;flex-direction:column;gap:2px}
.stat small{font-weight:400;font-size:10px;color:var(--smart-muted)}
.tabs{display:flex;gap:6px;margin-top:18px;border-bottom:1px solid var(--smart-border);padding-bottom:0}
.tabs button{border:1px solid transparent;border-bottom:none;background:transparent;color:var(--smart-muted);padding:10px 14px;border-radius:8px 8px 0 0;font-size:13px;cursor:pointer}
.tabs button.active{background:var(--smart-surface);border-color:var(--smart-border);color:var(--smart-primary-strong)}
.lab-layout{display:grid;grid-template-columns:300px minmax(0,1fr);gap:16px;margin-top:18px;align-items:start}
.lab-side{border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:10px;padding:14px;position:sticky;top:12px;display:flex;flex-direction:column;gap:10px;max-height:calc(100vh - 40px);overflow:auto}
.field{display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--smart-muted)}
.field select,.field input,textarea,.check-input{min-height:38px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-bg);color:var(--smart-text);padding:8px 10px;font-size:13px;width:100%;box-sizing:border-box}
textarea{font-family:var(--font-mono);resize:vertical}
.side-count{font-size:11px;color:var(--smart-muted);margin:0}
.exp-list,.point-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.exp-list li,.point-list li{border:1px solid var(--smart-border);border-radius:8px;padding:9px 11px;cursor:pointer;display:flex;flex-direction:column;gap:3px;font-size:12px}
.exp-list li:hover,.point-list li:hover{border-color:var(--smart-primary-strong)}
.exp-list li.active,.point-list li.active{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 8%,transparent)}
.exp-list b,.point-list b{font-size:13px}
.exp-list span,.point-list span{color:var(--smart-text)}
.exp-list em,.point-list em{font-style:normal;color:var(--smart-muted);font-size:11px}
.empty{color:var(--smart-muted);text-align:center;padding:12px}
.lab-main{display:flex;flex-direction:column;gap:14px;min-width:0}
.grid.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.panel{border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:10px;padding:16px}
.panel.head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.tag{font-size:11px;border:1px solid var(--smart-border);border-radius:999px;padding:4px 10px;color:var(--smart-muted)}
.tag.d-容易{color:#4caf7d;border-color:#4caf7d}
.tag.d-中等{color:#d99000;border-color:#d99000}
.tag.d-较难{color:#d9534f;border-color:#d9534f}
.goals{margin:0 0 6px;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--smart-muted)}
.answers{margin:0;padding-left:18px;font-size:12px;color:var(--smart-muted);display:flex;flex-direction:column;gap:5px}
.text{font-size:12px;line-height:1.8;color:var(--smart-muted);margin:0}
.errors{margin:0;padding-left:18px;font-size:12px;color:#d9534f;line-height:1.8}
.topo-panel svg{width:100%;height:auto;display:block}
.steps{margin:0;padding-left:0;list-style:none;display:flex;flex-direction:column;gap:12px}
.steps li{border-left:2px solid var(--smart-border);padding-left:12px}
.step-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px}
.step-title small{color:var(--smart-muted);font-size:11px}
.seq{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;border-radius:6px;background:var(--smart-primary-strong);color:#fff;font-size:11px}
.hint{margin:6px 0 0;font-size:12px;color:#d99000}
.cmds{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.cmds code{font:11px var(--font-mono);background:color-mix(in srgb,var(--smart-primary-strong) 12%,transparent);color:var(--smart-primary-strong);padding:3px 7px;border-radius:5px}
.expect{margin:6px 0 0;font-size:12px;color:var(--smart-muted)}
.validator .actions{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
button,.ghost,.primary{min-height:38px;display:inline-flex;align-items:center;justify-content:center;padding:8px 13px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-surface);color:var(--smart-text);cursor:pointer;font-size:13px}
.primary{background:var(--smart-primary-strong);color:#fff;border-color:transparent}
button:disabled{opacity:.6;cursor:not-allowed}
.report{margin-top:16px;border-top:1px solid var(--smart-border);padding-top:14px}
.score-bar{height:8px;border-radius:999px;background:var(--smart-border);overflow:hidden}
.score-bar span{display:block;height:100%;background:#d9534f;transition:width .3s}
.score-bar span.pass{background:#4caf7d}
.score-line{font-size:12px;margin:10px 0}
.score-line .ok{color:#4caf7d}.score-line .bad{color:#d9534f}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:11px;border-radius:999px;padding:4px 9px;border:1px solid}
.chip.bad{color:#d9534f;border-color:#d9534f}
.chip.warn{color:#d99000;border-color:#d99000}
.step-progress{display:flex;flex-direction:column;gap:4px;margin-top:10px;font-size:12px}
.step-progress .done{color:#4caf7d}.step-progress .todo{color:#d99000}
.suggestions{margin:10px 0 0;padding-left:18px;font-size:12px;color:var(--smart-muted);line-height:1.8}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--smart-border);vertical-align:top}
th{color:var(--smart-muted);font:10px var(--font-mono);letter-spacing:.06em}
td{color:var(--smart-muted)}
code{font:11px var(--font-mono);color:var(--smart-primary-strong);overflow-wrap:anywhere}
.lines td.st-ok{color:#4caf7d}
.lines td.st-unknown{color:#d9534f}
.lines td.st-wrong_context{color:#d99000}
.lines td.st-ignored{color:var(--smart-muted)}
.check-result{margin-top:4px;border:1px solid var(--smart-border);border-radius:8px;padding:12px;font-size:12px;display:flex;flex-direction:column;gap:6px}
.check-result.st-ok{border-color:#4caf7d}
.check-result.st-unknown{border-color:#d9534f}
.check-result.st-wrong_context{border-color:#d99000}
@media(max-width:900px){.lab-layout{grid-template-columns:1fr}.lab-side{position:static;max-height:none}}
</style>
