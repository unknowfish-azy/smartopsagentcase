<template>
  <section class="sentinel-surface" aria-labelledby="scripts-title">
    <header class="sentinel-page-header">
      <div>
        <p class="sentinel-eyebrow">SENTINEL / 脚本库</p>
        <h1 id="scripts-title">自定义脚本执行</h1>
      </div>
      <button type="button" :disabled="state.loading" @click="reload">刷新</button>
    </header>
    <p class="sentinel-lede">
      在线编写 Shell / Python / Bat / PowerShell 脚本，带版本、标签与风险级别。
      执行仍然走既有的受控链路：<strong>预览 → 二次确认 → 执行 → 记录 → 审计</strong>，本模块不新增执行通路。
    </p>

    <SentinelNotice v-if="state.status === 'unavailable'" tone="warn" title="后端未接入" :detail="state.reason" />

    <dl class="sentinel-stats">
      <div class="sentinel-stat"><dt>脚本总数</dt><dd>{{ state.scripts.length }}</dd></div>
      <div class="sentinel-stat"><dt>高危待审批</dt><dd>{{ pendingApproval }}</dd></div>
      <div class="sentinel-stat"><dt>已启用</dt><dd>{{ enabledCount }}</dd></div>
      <div class="sentinel-stat"><dt>最近执行</dt><dd>{{ state.runs.length }}</dd></div>
    </dl>

    <SentinelEmpty
      v-if="state.loaded && state.scripts.length === 0"
      title="还没有脚本"
      description="脚本保存后即产生 v1 版本。高危脚本需要管理员审批后才可用于告警联动。后端 /api/sentinel/scripts 接入后，这里会列出真实脚本与执行记录。"
    />

    <div v-else-if="state.scripts.length" class="sentinel-table-wrap">
      <table>
        <caption class="sentinel-caption">脚本与最近执行结果</caption>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">语言</th>
            <th scope="col">标签</th>
            <th scope="col">版本</th>
            <th scope="col">风险</th>
            <th scope="col">审批</th>
            <th scope="col">最近结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="script in state.scripts" :key="script.id">
            <td>{{ script.name }}</td>
            <td>{{ languageLabel(script.language) }}</td>
            <td class="sentinel-muted">{{ script.tags || '—' }}</td>
            <td class="sentinel-mono">v{{ script.currentVersion }}</td>
            <td><span class="sentinel-tag" :class="riskClass(script.riskLevel)">{{ riskLabel(script.riskLevel) }}</span></td>
            <td>{{ script.approved ? '已通过' : requiresApproval(script.riskLevel) ? '待管理员审批' : '无需' }}</td>
            <td>{{ lastResult(script.id) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <section class="sentinel-panel" aria-labelledby="scripts-editor-title">
      <h2 id="scripts-editor-title">在线编辑器与高危预检</h2>
      <p class="sentinel-hint">
        保存或执行前会做一次高危预检。这是<strong>防御性预检，不是沙箱</strong>：
        它拦住明显误操作，真正的边界在服务端（固定命令、参数校验、最小权限、超时与审批）。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field">
          <span>脚本语言</span>
          <select v-model="draft.language">
            <option v-for="item in SCRIPT_LANGUAGES" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
        </label>
        <label class="sentinel-field">
          <span>风险级别</span>
          <select v-model="draft.riskLevel">
            <option v-for="item in SCRIPT_RISKS" :key="item.id" :value="item.id">{{ item.label }}（{{ item.cn }}）</option>
          </select>
        </label>
        <label class="sentinel-field sentinel-field--wide">
          <span>脚本内容</span>
          <textarea v-model="draft.body" rows="9" spellcheck="false" placeholder="# 例如：df -h&#10;systemctl status nginx"></textarea>
        </label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" @click="runLint">运行高危预检</button>
        <span v-if="requiresApproval(draft.riskLevel)" class="sentinel-muted">高 RISK 脚本保存后需管理员审批才可用于告警联动</span>
      </div>
      <SentinelNotice
        v-if="lint"
        :tone="lint.verdict === 'ok' ? 'ok' : lint.verdict === 'blocked' ? 'danger' : 'warn'"
        :title="lint.verdict === 'ok' ? '预检通过' : lint.verdict === 'blocked' ? '命中高危规则，已拒绝' : '疑似语法问题'"
        :detail="lint.detail"
      />
      <ul v-if="lint?.matches?.length" class="sentinel-list sentinel-list--danger">
        <li v-for="(match, index) in lint.matches" :key="index">
          <strong>{{ match.label }}</strong><code class="sentinel-mono">{{ match.sample }}</code>
        </li>
      </ul>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-var-title">
      <h2 id="scripts-var-title">支持的平台变量</h2>
      <p class="sentinel-hint">告警联动执行时由平台注入，脚本里直接使用即可。未提供的变量会保持原样并在界面上提示未替换项。</p>
      <ul class="sentinel-list">
        <li v-for="variable in PLATFORM_VARIABLES" :key="variable.key">
          <code class="sentinel-mono">{{ variable.token }}</code>
          <span class="sentinel-muted">{{ variable.description }}</span>
        </li>
      </ul>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-modes-title">
      <h2 id="scripts-modes-title">三种执行模式</h2>
      <ul class="sentinel-list">
        <li><strong>手动执行</strong><span class="sentinel-muted">选择目标资产后执行，实时输出并落执行记录</span></li>
        <li><strong>定时执行</strong><span class="sentinel-muted">按 cron 计划执行，记录与手动执行同构</span></li>
        <li><strong>告警联动</strong><span class="sentinel-muted">由告警规则触发；P0/P1 与高危脚本必须人工确认</span></li>
      </ul>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-upload-title">
      <h2 id="scripts-upload-title">从文件导入脚本</h2>
      <p class="sentinel-hint">
        上传与手动编写走<strong>同一条预检路径</strong>，高危内容一样会被拒绝。
        只接受文本脚本（.sh / .bash / .py / .bat / .cmd / .ps1 / .psm1），二进制与超过 1 MiB 的文件会被拒。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field sentinel-field--wide">
          <span>选择脚本文件</span>
          <input type="file" accept=".sh,.bash,.py,.bat,.cmd,.ps1,.psm1" @change="pickFile" />
        </label>
        <label class="sentinel-field">
          <span>风险级别</span>
          <select v-model="upload.riskLevel">
            <option v-for="item in SCRIPT_RISKS" :key="item.id" :value="item.id">{{ item.label }}（{{ item.cn }}）</option>
          </select>
        </label>
        <label class="sentinel-field">
          <span>标签</span>
          <input v-model.trim="upload.tags" placeholder="可选，逗号分隔" />
        </label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="uploading || !upload.fileName" @click="submitUpload">
          {{ uploading ? '正在导入…' : `导入${upload.fileName ? `「${upload.fileName}」` : ''}` }}
        </button>
        <span class="sentinel-muted">{{ uploadMessage }}</span>
      </div>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-run-title">
      <h2 id="scripts-run-title">发起执行（受控）</h2>
      <p class="sentinel-hint">
        这里<strong>只生成预览、不执行命令</strong>。真正执行由人带确认码提交既有多机执行接口完成。
        三种模式共用同一个入口，所以定时与告警联动同样需要人工确认，不存在"自动跑起来"的旁路。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field">
          <span>选择脚本</span>
          <select v-model="plan.scriptId">
            <option :value="null" disabled>请选择脚本</option>
            <option v-for="script in state.scripts" :key="script.id" :value="script.id">
              {{ script.name }}（v{{ script.currentVersion }} · {{ riskLabel(script.riskLevel) }}）
            </option>
          </select>
        </label>
        <label class="sentinel-field">
          <span>触发方式</span>
          <select v-model="plan.trigger">
            <option v-for="mode in TRIGGER_MODES" :key="mode.id" :value="mode.id">{{ mode.label }}</option>
          </select>
        </label>
        <label class="sentinel-field sentinel-field--wide">
          <span>目标运行连接 ID</span>
          <input v-model.trim="plan.runtimeId" placeholder="在「远程运维」里建立连接后粘贴运行连接 ID，多个用逗号分隔" />
        </label>
        <label v-for="variable in variablesToFill" :key="variable.key" class="sentinel-field">
          <span>{{ variable.label }}</span>
          <input v-model.trim="plan.variables[variable.key]" :placeholder="variable.example" />
        </label>
        <label v-if="plan.trigger === 'ALERT'" class="sentinel-field">
          <span>关联告警 ID</span>
          <input v-model.trim="plan.alertId" placeholder="告警中心里的告警 ID" />
        </label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="preparing || !planReady" @click="prepareRun">
          {{ preparing ? '正在生成预览…' : '生成预览（不执行）' }}
        </button>
        <span class="sentinel-muted">{{ planHint }}</span>
      </div>
      <SentinelNotice v-if="planMessage" :tone="prepared ? 'info' : 'danger'" :title="prepared ? '已生成预览，等待人工确认' : '未发起'" :detail="planMessage" />
      <dl v-if="prepared" class="sentinel-stats sentinel-stats--compact">
        <div class="sentinel-stat"><dt>预览 ID</dt><dd class="sentinel-mono sentinel-small">{{ prepared.previewId }}</dd></div>
        <div class="sentinel-stat"><dt>风险</dt><dd>{{ prepared.risk }}</dd></div>
        <div class="sentinel-stat"><dt>需确认次数</dt><dd>{{ prepared.requiredApprovals }}</dd></div>
        <div class="sentinel-stat"><dt>人工确认</dt><dd>{{ prepared.humanApprovalRequired ? '必须' : '需一次确认' }}</dd></div>
      </dl>
      <p v-if="prepared" class="sentinel-hint">
        下一步：把 <code class="sentinel-mono">{{ prepared.previewId }}</code> 与确认码
        <code class="sentinel-mono sentinel-small">{{ prepared.confirmationNonce }}</code>
        提交到既有多机执行接口。页面关闭后确认码失效，需要重新生成预览。
      </p>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-schedule-title">
      <h2 id="scripts-schedule-title">定时计划</h2>
      <p class="sentinel-hint">
        定时到点后<strong>只生成待审批预览</strong>，不会自动执行命令。调度器默认关闭
        （<code class="sentinel-mono">smartops.sentinel.schedule.initial-delay-ms</code>），
        需部署方显式打开——"会自己发生"的行为不应默认替人发起。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field">
          <span>脚本</span>
          <select v-model="schedule.scriptId">
            <option :value="null" disabled>请选择脚本</option>
            <option v-for="script in state.scripts" :key="script.id" :value="script.id">{{ script.name }}</option>
          </select>
        </label>
        <label class="sentinel-field">
          <span>cron（5 段）</span>
          <input v-model.trim="schedule.cronExpr" placeholder="*/5 * * * *" />
        </label>
        <label class="sentinel-field">
          <span>目标运行连接 ID</span>
          <input v-model.trim="schedule.runtimeId" placeholder="与手动执行相同的运行连接 ID" />
        </label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="scheduling || !scheduleReady" @click="createSchedule">
          {{ scheduling ? '正在保存…' : '保存定时计划' }}
        </button>
        <span class="sentinel-muted">{{ scheduleReady ? '保存后到点生成待审批预览' : '请填写脚本、cron 与目标' }}</span>
      </div>
      <ul v-if="state.schedules.length" class="sentinel-list">
        <li v-for="item in state.schedules" :key="item.id">
          <strong>{{ item.scriptName }}</strong>
          <code class="sentinel-mono">{{ item.cronExpr }}</code>
          <span class="sentinel-muted">上次：{{ item.lastFireAt || '未触发' }}</span>
          <button type="button" @click="removeSchedule(item.id)">删除</button>
        </li>
      </ul>
      <p v-else class="sentinel-muted">还没有定时计划。</p>
    </section>

    <section class="sentinel-panel" aria-labelledby="scripts-runs-title">
      <h2 id="scripts-runs-title">执行记录与回放</h2>
      <p class="sentinel-hint">
        回放展示的是<strong>这次执行的记录</strong>，不是重新执行。确认码不落库，
        需要再次执行请重新生成预览并人工确认。
      </p>
      <div v-if="state.runs.length" class="sentinel-table-wrap">
        <table>
          <caption class="sentinel-caption">执行记录（执行人 / 目标 / 耗时 / 返回码 / 结果）</caption>
          <thead>
            <tr>
              <th scope="col">脚本</th><th scope="col">触发</th><th scope="col">版本</th>
              <th scope="col">目标</th><th scope="col">耗时</th><th scope="col">返回码</th>
              <th scope="col">结果</th><th scope="col">回放</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in state.runs" :key="run.id">
              <td>{{ scriptNameById(run.scriptId) }}</td>
              <td>{{ triggerLabel(run.triggerKind) }}</td>
              <td class="sentinel-mono">v{{ run.version }}</td>
              <td class="sentinel-muted">{{ shorten(run.targetRuntime) }}</td>
              <td>{{ run.durationMs == null ? '—' : `${run.durationMs} ms` }}</td>
              <td>{{ run.exitCode == null ? '—' : run.exitCode }}</td>
              <td>{{ run.result }}</td>
              <td><button type="button" @click="replay(run.id)">查看</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="sentinel-muted">还没有执行记录。这里只显示真实记录，不会为演示造数据。</p>

      <div v-if="replayed" class="sentinel-replay">
        <h3>回放 #{{ replayed.id }} · {{ replayed.scriptName }} v{{ replayed.version }}</h3>
        <dl class="sentinel-replay__meta">
          <div><dt>触发方式</dt><dd>{{ triggerLabel(replayed.trigger) }}</dd></div>
          <div><dt>目标</dt><dd class="sentinel-mono sentinel-small">{{ replayed.targetRuntime || '—' }}</dd></div>
          <div><dt>开始</dt><dd>{{ replayed.startedAt }}</dd></div>
          <div><dt>结束</dt><dd>{{ replayed.finishedAt || '未结束' }}</dd></div>
          <div><dt>耗时</dt><dd>{{ replayed.durationMs == null ? '—' : `${replayed.durationMs} ms` }}</dd></div>
          <div><dt>返回码</dt><dd>{{ replayed.exitCode == null ? '—' : replayed.exitCode }}</dd></div>
        </dl>
        <h4>使用的变量</h4>
        <ul v-if="Object.keys(replayed.variables || {}).length" class="sentinel-list sentinel-list--plain">
          <li v-for="(value, key) in replayed.variables" :key="key">
            <code class="sentinel-mono">{{ key }}</code><span class="sentinel-muted">{{ value }}</span>
          </li>
        </ul>
        <p v-else class="sentinel-muted">这次执行没有使用平台变量。</p>
        <h4>输出</h4>
        <pre class="sentinel-output">{{ replayed.output || '（无输出记录）' }}</pre>
        <p class="sentinel-hint">{{ replayed.replayNote }}</p>
        <button type="button" @click="replayed = null">收起回放</button>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import SentinelNotice from './SentinelNotice.vue'
import SentinelEmpty from './SentinelEmpty.vue'
import { loadSentinel, prepareScriptRun, sentinelState as state } from './sentinelStore.js'
import { addSchedule, deleteSchedule, loadRunDetail, uploadScript } from './sentinelStore.js'
import {
  PLATFORM_VARIABLES, SCRIPT_LANGUAGES, SCRIPT_RISKS, TRIGGER_MODES, lintScript, requiresApproval
} from './sentinelModel.js'
import './sentinel.css'

const draft = reactive({ language: 'shell', riskLevel: 'LOW', body: '' })
const lint = ref(null)

const pendingApproval = computed(() => state.scripts.filter(script => requiresApproval(script.riskLevel) && !script.approved).length)
const enabledCount = computed(() => state.scripts.filter(script => script.enabled !== false).length)

const languageLabel = id => SCRIPT_LANGUAGES.find(item => item.id === id)?.label ?? id ?? '—'
const riskLabel = id => SCRIPT_RISKS.find(item => item.id === id)?.label ?? id ?? '—'
const riskClass = id => `sentinel-tag--${(id || 'low').toLowerCase()}`
const lastResult = scriptId => state.runs.find(run => run.scriptId === scriptId)?.result ?? '—'
const runLint = () => { lint.value = lintScript(draft.body, draft.language) }
const reload = () => loadSentinel()

/* ── 发起执行（只生成预览） ─────────────────────────────────────────── */

const plan = reactive({ scriptId: null, trigger: 'MANUAL', runtimeId: '', alertId: '', variables: {} })
const preparing = ref(false)
const planMessage = ref('')
const prepared = ref(null)

/** 与该触发方式相关的变量：告警联动才需要指标/值，手动模式下也允许填写。 */
const variablesToFill = computed(() => PLATFORM_VARIABLES.filter(variable =>
  variable.key !== '时间' && variable.key !== '执行人'))

const planReady = computed(() => Boolean(plan.scriptId) && plan.runtimeId.trim().length > 0
  && (plan.trigger !== 'ALERT' || plan.alertId.trim().length > 0))

const planHint = computed(() => {
  if (!plan.scriptId) return '先选择一个脚本'
  if (!plan.runtimeId.trim()) return '需要目标运行连接（在「远程运维」建立后获得 ID）'
  if (plan.trigger === 'ALERT' && !plan.alertId.trim()) return '告警联动需要关联告警 ID'
  return '生成预览后会返回确认码，执行需人工提交'
})

async function prepareRun() {
  preparing.value = true
  planMessage.value = ''
  prepared.value = null
  try {
    const runtimeIds = plan.runtimeId.split(',').map(item => item.trim()).filter(Boolean)
    const variables = Object.fromEntries(Object.entries(plan.variables)
      .filter(([, value]) => value !== undefined && String(value).trim() !== ''))
    const result = await prepareScriptRun(plan.scriptId, {
      trigger: plan.trigger,
      runtimeIds,
      alertId: plan.alertId.trim() ? Number(plan.alertId.trim()) : null,
      variables
    })
    if (!result.ok) { planMessage.value = result.message; return }
    prepared.value = result.plan
    planMessage.value = result.plan.note
  } finally { preparing.value = false }
}

/* ── 定时计划 ──────────────────────────────────────────────────────── */

const schedule = reactive({ scriptId: null, cronExpr: '*/5 * * * *', runtimeId: '' })
const scheduling = ref(false)
const scheduleMessage = ref('')

const scheduleReady = computed(() => Boolean(schedule.scriptId)
  && schedule.cronExpr.trim().split(/\s+/).length === 5
  && schedule.runtimeId.trim().length > 0)

async function createSchedule() {
  scheduling.value = true
  scheduleMessage.value = ''
  try {
    const result = await addSchedule(schedule.scriptId, {
      cronExpr: schedule.cronExpr.trim(),
      runtimeId: schedule.runtimeId.trim()
    })
    scheduleMessage.value = result.ok ? '定时计划已保存；到点只生成待审批预览。' : result.message
    if (result.ok) await loadSentinel()
  } finally { scheduling.value = false }
}

async function removeSchedule(id) {
  const result = await deleteSchedule(id)
  scheduleMessage.value = result.ok ? '已删除定时计划。' : result.message
  if (result.ok) await loadSentinel()
}

/* ── 执行记录回放 ──────────────────────────────────────────────────── */

const replayed = ref(null)

const triggerLabel = id => TRIGGER_MODES.find(mode => mode.id === id)?.label ?? id ?? '—'
const scriptNameById = id => state.scripts.find(script => script.id === id)?.name ?? (id ? `#${id}` : '—')
const shorten = value => {
  if (!value) return '—'
  return value.length <= 28 ? value : `${value.slice(0, 12)}…${value.slice(-8)}`
}

async function replay(runId) {
  scheduleMessage.value = ''
  const result = await loadRunDetail(runId)
  if (!result.ok) { scheduleMessage.value = result.message; return }
  replayed.value = result.detail
}

/* ── 文件导入 ──────────────────────────────────────────────────────── */

const upload = reactive({ fileName: '', content: '', riskLevel: 'LOW', tags: '' })
const uploading = ref(false)
const uploadMessage = ref('')

/** 读文本文件到内存；不落盘、不解析，只把内容当成脚本正文。 */
async function pickFile(event) {
  const file = event.target.files?.[0]
  uploadMessage.value = ''
  if (!file) { upload.fileName = ''; upload.content = ''; return }
  if (file.size > 1024 * 1024) {
    upload.fileName = ''
    uploadMessage.value = '文件超过 1 MiB，请拆分或精简后再导入。'
    return
  }
  try {
    upload.content = await file.text()
    upload.fileName = file.name
    uploadMessage.value = `已读取 ${file.name}（${file.size} 字节）`
  } catch {
    upload.fileName = ''
    uploadMessage.value = '读取文件失败，请重试。'
  }
}

async function submitUpload() {
  uploading.value = true
  uploadMessage.value = ''
  try {
    const result = await uploadScript({
      fileName: upload.fileName, content: upload.content,
      riskLevel: upload.riskLevel, tags: upload.tags
    })
    uploadMessage.value = result.ok
      ? `已导入脚本「${result.script.name}」（${languageLabel(result.script.language)}，v${result.script.currentVersion}）`
      : result.message
    if (result.ok) { upload.fileName = ''; upload.content = ''; await loadSentinel() }
  } finally { uploading.value = false }
}

onMounted(loadSentinel)
</script>
