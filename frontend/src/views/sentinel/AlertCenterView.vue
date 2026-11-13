<template>
  <div ref="alertsShellRef" class="sentinel-shell" :data-theme="resolvedTheme">
    <CanvasAmbientField v-if="!isMobile" class="sentinel-ambient" :palette-root="alertsShellRef" :star-multiplier="1.8" connect-particles :connect-max-dist="130" />
    <div v-if="!isMobile" class="sentinel-aurora" aria-hidden="true"></div>
    <MeteorShower v-if="!isMobile" class="sentinel-meteors" />
    <div class="sentinel-mask" aria-hidden="true"></div>

  <section class="sentinel-surface" aria-labelledby="alerts-title">
    <header class="sentinel-page-header">
      <div>
        <p class="sentinel-eyebrow">SENTINEL / 告警中心</p>
        <h1 id="alerts-title">告警联动处置</h1>
      </div>
      <button type="button" :disabled="state.loading" @click="reload">刷新</button>
    </header>
    <p class="sentinel-lede">
      接收哨兵上报的异常，按规则选择通知渠道、给出 AI 研判与脚本推荐，并把处置结果回填工单形成闭环。
      <strong>处置不旁路审批</strong>：脚本仍经既有「预览 → 审批 → 执行 → 验证 → 审计」链路。
    </p>

    <SentinelNotice v-if="state.status === 'unavailable'" tone="warn" title="后端未接入" :detail="state.reason" />
    <SentinelNotice
      tone="info"
      title="为什么不做「告警直接执行」"
      detail="本项目定位是受控执行。因此实现为「建议 + 待审批」：P0/P1 与高危脚本一律停等人工确认，P2/P3 且脚本已发布且已授权时可由策略自动发起，但仍要经过预览与审批闸门。"
    />

    <dl class="sentinel-stats">
      <div class="sentinel-stat"><dt>待处理</dt><dd>{{ countBy('OPEN') }}</dd></div>
      <div class="sentinel-stat"><dt>待审批</dt><dd>{{ countBy('PENDING_APPROVAL') }}</dd></div>
      <div class="sentinel-stat"><dt>处置中</dt><dd>{{ countBy('REMEDIATING') }}</dd></div>
      <div class="sentinel-stat"><dt>已关闭</dt><dd>{{ countBy('CLOSED') }}</dd></div>
    </dl>

    <SentinelNotice
      tone="info"
      title="研判 / 通知 / 沉淀 / 团队审批 怎么用"
      detail="每条告警有四个操作：研判给出建议与证据（不改状态、不执行）；通知发给相关人（站内真实发出，邮件与 Webhook 会如实标记为待投递）；沉淀把已关闭告警整理成知识候选进入团队复核；走团队审批则生成预览并在团队侧创建待审批运行，仍由人批准后才执行。"
    />

    <SentinelEmpty
      v-if="state.loaded && state.alerts.length === 0"
      title="还没有告警"
      description="哨兵命中阈值并经过持续时间防抖后会产生告警。产生告警后，每行会提供「研判 / 通知 / 沉淀」三个操作。"
    >
      <p class="sentinel-empty__links">
        <RouterLink to="/sentinel">先配置哨兵与阈值模板 →</RouterLink>
      </p>
    </SentinelEmpty>

    <div v-else-if="state.alerts.length" class="alert-grid">
      <article v-for="alert in state.alerts" :key="alert.id" class="alert-card ops-card ops-card--interactive">
        <header class="alert-card__head">
          <span class="ui-tag ui-tag--sm" :class="`ui-tag--${severityTone(alert.severity)}`">{{ alert.severity || 'P3' }}</span>
          <h2 class="alert-card__title">{{ alert.title || '未命名告警' }}</h2>
          <span class="ui-pill" :class="`ui-pill--${statusTone(alert.status)}`">{{ statusLabel(alert.status) }}</span>
        </header>

        <div class="alert-card__meta">
          <span class="ui-tag ui-tag--sm ui-tag--mono">{{ alert.metric || '指标' }}</span>
          <span>观测 <b class="u-num">{{ alert.observedValue ?? '—' }}</b></span>
          <span>阈值 <b class="u-num">{{ alert.thresholdValue ?? '—' }}</b></span>
          <span>脚本：{{ scriptName(alert.recommendedScriptId) }}</span>
          <span>工单：{{ alert.ticketId || '—' }}</span>
          <time>{{ alert.firedAt || '—' }}</time>
        </div>

        <p class="alert-card__ai" :class="{ 'is-empty': !alert.aiSummary }">
          {{ alert.aiSummary || '尚未生成 AI 研判。点击「研判」获取建议与证据（仅建议，不改变状态、不执行脚本）。' }}
        </p>

        <!-- 处置闭环四步：采集 → 研判 → 审批 → 关闭（状态由告警真实字段推导） -->
        <ol class="ui-sop" aria-label="处置进度">
          <li
            v-for="step in sopSteps(alert)"
            :key="step.label"
            class="ui-sop__step"
            :class="{ 'ui-sop__step--done': step.done, 'ui-sop__step--active': step.active }"
          >{{ step.label }}</li>
        </ol>

        <footer class="alert-card__actions">
          <button type="button" :disabled="busyId === alert.id" @click="analyze(alert)">研判</button>
          <button type="button" :disabled="busyId === alert.id" @click="notify(alert)">通知</button>
          <!-- 只有已关闭的告警才能沉淀为经验；未关闭时后端会拒绝，这里提前禁用并说明原因。 -->
          <button type="button" :disabled="busyId === alert.id || alert.status !== 'CLOSED'" :title="alert.status === 'CLOSED' ? '沉淀为知识候选，等待团队复核' : '需先人工确认关闭后才能沉淀为知识'" @click="sediment(alert)">沉淀</button>
          <button type="button" :disabled="busyId === alert.id" title="交给团队 Agent 提出处置：生成预览并在团队侧创建待审批运行，不执行命令" @click="openProposal(alert)">走团队审批</button>
        </footer>
      </article>
      <p v-if="actionMessage" class="sentinel-hint sentinel-hint--table" role="status">{{ actionMessage }}</p>
    </div>

    <!-- 团队审批通道：明确说明它不执行命令，只是把处置交给团队走审批链。 -->
    <section v-if="proposalFor" class="sentinel-panel" aria-labelledby="proposal-title">
      <h2 id="proposal-title">交给团队 Agent 提出处置</h2>
      <p class="sentinel-hint">
        这里<strong>不会执行命令</strong>：服务端会生成既有多机执行的预览，并在团队侧创建一条
        <strong>待审批运行</strong>。之后仍需有审批权的成员预览并批准，再由申请人执行。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field"><span>团队 ID</span><input v-model.trim="proposal.teamId" placeholder="团队成员所在团队 ID" /></label>
        <label class="sentinel-field"><span>Agent ID</span><input v-model.trim="proposal.agentId" placeholder="团队 Agent 的 ID" /></label>
        <label class="sentinel-field"><span>已发布版本 ID</span><input v-model.trim="proposal.versionId" placeholder="Agent 当前已发布版本 ID" /></label>
        <label class="sentinel-field"><span>处置脚本</span>
          <select v-model="proposal.scriptId">
            <option :value="null" disabled>请选择脚本</option>
            <option v-for="script in state.scripts" :key="script.id" :value="script.id">{{ script.name }}</option>
          </select>
        </label>
        <label class="sentinel-field sentinel-field--wide"><span>目标运行连接 ID</span><input v-model.trim="proposal.runtimeId" placeholder="在「远程运维」建立连接后获得" /></label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="busyId !== null || !proposalReady" @click="submitProposal">生成预览并创建待审批运行</button>
        <button type="button" @click="proposalFor = null">取消</button>
        <span class="sentinel-muted">{{ proposalReady ? '提交后进入团队审批队列' : '请填写团队、Agent、版本、脚本与目标' }}</span>
      </div>
      <SentinelNotice v-if="proposalResult" tone="info"
        :title="`已创建待审批运行 #${proposalResult.teamRunId}`"
        :detail="`${proposalResult.nextStep}（预览 ${proposalResult.previewId}，风险 ${proposalResult.risk}，需确认 ${proposalResult.requiredApprovals} 次）`" />
    </section>

    <!-- 研判结果：明确标为「建议」，并展示证据与候选脚本，避免被当成既定结论。 -->
    <section v-if="advice" class="sentinel-panel sentinel-advice" aria-labelledby="advice-title">
      <h2 id="advice-title">
        AI 研判建议
        <span class="sentinel-tag">{{ advice.severity }}</span>
        <span v-if="advice.humanFirst" class="sentinel-tag sentinel-tag--p0">建议人工优先确认</span>
      </h2>
      <p class="sentinel-advice__summary">{{ advice.summary }}</p>
      <div class="sentinel-advice__grid">
        <div>
          <h3>证据</h3>
          <ul class="sentinel-list sentinel-list--plain">
            <li v-for="(item, index) in advice.evidence" :key="index"><span class="sentinel-muted">{{ item }}</span></li>
          </ul>
        </div>
        <div>
          <h3>候选脚本</h3>
          <ul v-if="advice.scripts.length" class="sentinel-list sentinel-list--plain">
            <li v-for="script in advice.scripts" :key="script.scriptId">
              <strong>{{ script.name }}</strong>
              <span class="sentinel-tag" :class="`sentinel-tag--${(script.riskLevel || 'low').toLowerCase()}`">{{ script.riskLevel }}</span>
              <span class="sentinel-muted">{{ script.reason }}</span>
            </li>
          </ul>
          <p v-else class="sentinel-muted">没有匹配到候选脚本，请人工选择或先沉淀脚本。</p>
        </div>
      </div>
      <p class="sentinel-hint">{{ advice.disclaimer }}</p>
      <button type="button" class="sentinel-advice__close" @click="advice = null">收起</button>
    </section>

    <section class="sentinel-panel" aria-labelledby="alerts-flow-title">
      <h2 id="alerts-flow-title">处置闭环</h2>
      <ol class="sentinel-flow">
        <li><strong>哨兵采集</strong><span>常驻轮询指标 / 监听日志</span></li>
        <li><strong>命中阈值</strong><span>含持续时间防抖，瞬时峰值不告警</span></li>
        <li><strong>产生告警</strong><span>P0..P3 分级</span></li>
        <li><strong>通知 + AI 研判</strong><span>站内 / 邮件 / Webhook，给出根因建议与脚本推荐</span></li>
        <li><strong>生成工单</strong><span>复用既有运行记录作为工单主体</span></li>
        <li><strong>预览 → 审批</strong><span>P0/P1 与高危脚本必须人工确认</span></li>
        <li><strong>执行 → 结果回填</strong><span>返回码、输出、耗时写回工单</span></li>
        <li><strong>人工确认关闭</strong><span>全程写入告警时间线与审计</span></li>
      </ol>
    </section>

    <section class="sentinel-panel" aria-labelledby="alerts-rule-create-title">
      <h2 id="alerts-rule-create-title">新建告警规则</h2>
      <p class="sentinel-hint">
        规则把<strong>哨兵监控项（阈值模板）</strong>与<strong>处置脚本</strong>绑起来。
        即使选了自动发起，真正执行仍要走<strong>预览 → 审批 → 执行</strong>；
        P0/P1 的自动发起会被服务端强制关闭。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field"><span>规则名称</span>
          <input v-model.trim="ruleForm.name" maxlength="128" placeholder="如 内存持续偏高" /></label>
        <label class="sentinel-field"><span>阈值模板</span>
          <select v-model="ruleForm.templateId">
            <option :value="null">不绑定模板</option>
            <option v-for="tpl in state.templates" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
          </select></label>
        <label class="sentinel-field"><span>告警级别</span>
          <select v-model="ruleForm.severity">
            <option v-for="item in ALERT_SEVERITIES" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select></label>
        <label class="sentinel-field"><span>处置脚本</span>
          <select v-model="ruleForm.scriptId">
            <option :value="null">不绑定脚本</option>
            <option v-for="script in state.scripts" :key="script.id" :value="script.id">{{ script.name }}</option>
          </select></label>
        <label class="sentinel-field"><span>Webhook 地址</span>
          <input v-model.trim="ruleForm.webhookUrl" placeholder="https://…（内网地址会被拒绝）" /></label>
        <label class="sentinel-field"><span>邮件收件人</span>
          <input v-model.trim="ruleForm.emailTo" placeholder="oncall@example.test，多个用逗号" /></label>
      </div>
      <fieldset class="sentinel-field sentinel-field--wide">
        <legend>通知渠道</legend>
        <label v-for="channel in NOTIFY_CHANNELS" :key="channel.id" class="sentinel-check">
          <input type="checkbox" :value="channel.id" v-model="ruleForm.channels" />
          <span>{{ channel.label }}</span>
          <span v-if="channel.cn" class="sentinel-muted sentinel-small">{{ channel.cn }}</span>
        </label>
      </fieldset>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="creating || !ruleReady" @click="submitRule">
          {{ creating ? '正在创建…' : '创建告警规则' }}</button>
        <span class="sentinel-muted">{{ ruleReady ? severityHint : '请填写规则名称' }}</span>
      </div>
      <p v-if="ruleMessage" class="sentinel-hint" role="status">{{ ruleMessage }}</p>
    </section>

    <section class="sentinel-panel" aria-labelledby="alerts-rules-title">
      <h2 id="alerts-rules-title">告警规则与分级</h2>
      <SentinelEmpty
        v-if="state.alertRules.length === 0"
        title="还没有告警规则"
        description="规则用于绑定哨兵监控项、触发条件、处置脚本与通知渠道。后端 /api/sentinel/alert-rules 接入后在此管理。"
      />
      <ul v-else class="sentinel-list">
        <li v-for="rule in state.alertRules" :key="rule.id">
          <strong>{{ rule.name }}</strong>
          <span class="sentinel-tag" :class="`sentinel-tag--${(rule.severity || 'p3').toLowerCase()}`">{{ rule.severity }}</span>
          <span class="sentinel-muted">{{ rule.notifyChannels }}</span>
          <!-- 收件人只在配了邮件渠道时显示，避免为空时留下无意义的"邮件：—" -->
          <span v-if="rule.emailTo" class="sentinel-muted">邮件收件人：{{ rule.emailTo }}</span>
          <span class="sentinel-muted">处置脚本：{{ scriptName(rule.scriptId) }}</span>
        </li>
      </ul>
      <ul class="sentinel-list">
        <li v-for="severity in ALERT_SEVERITIES" :key="severity.id">
          <strong>{{ severity.label }}</strong>
          <span class="sentinel-muted">{{ severity.cn }}</span>
          <span class="sentinel-tag">{{ requiresHumanBeforeRemediation(severity.id) ? '必须人工确认' : '可由策略发起，仍需审批' }}</span>
        </li>
      </ul>
    </section>

    <section class="sentinel-panel" aria-labelledby="alerts-channels-title">
      <h2 id="alerts-channels-title">通知渠道</h2>
      <ul class="sentinel-list">
        <li v-for="channel in NOTIFY_CHANNELS" :key="channel.id">
          <strong>{{ channel.label }}</strong><span class="sentinel-muted">{{ channel.cn || '按规则配置目标' }}</span>
        </li>
      </ul>
      <p class="sentinel-hint">
        投递结果会逐渠道区分：站内真实写入团队通知；Webhook 走真实 HTTP（内网地址默认被拒，
        需要部署方配置白名单）；<strong>邮件在未接入 SMTP 时显示"未配置"，不会谎称已发送</strong>。
      </p>
    </section>
  </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, defineAsyncComponent } from 'vue'
import SentinelNotice from './SentinelNotice.vue'
import SentinelEmpty from './SentinelEmpty.vue'
import { resolvedTheme as _resolvedTheme } from '../../theme.js'
import {
  analyzeAlert,
  createAlertRule,
  createKnowledgeCandidate,
  loadSentinel,
  notifyAlert,
  proposeRemediation,
  sentinelState as state
} from './sentinelStore.js'
import { ALERT_SEVERITIES, ALERT_STATUSES, NOTIFY_CHANNELS, requiresHumanBeforeRemediation } from './sentinelModel.js'
import './sentinel.css'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))
const MeteorShower = defineAsyncComponent(() => import('../../components/common/MeteorShower.vue'))

const alertsShellRef = ref(null)
const resolvedTheme = computed(() => _resolvedTheme.value)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

const busyId = ref(null)
const actionMessage = ref('')
const advice = ref(null)

const countBy = status => state.alerts.filter(alert => alert.status === status).length
const statusLabel = id => ALERT_STATUSES.find(item => item.id === id)?.label ?? id ?? '—'
const scriptName = id => state.scripts.find(script => script.id === id)?.name ?? (id ? `#${id}` : '—')
const reload = () => loadSentinel()

/** 级别 → 语义标签色：P0/P1 危险，P2 警告，P3 中性。 */
const severityTone = severity => {
  const level = String(severity || '').toUpperCase()
  return level === 'P0' || level === 'P1' ? 'danger' : level === 'P2' ? 'warning' : 'neutral'
}

/** 处置状态 → 状态 pill 色。 */
function statusTone(status) {
  const value = String(status || '').toUpperCase()
  if (value === 'CLOSED') return 'success'
  if (value === 'REMEDIATING') return 'info'
  if (value === 'PENDING_APPROVAL' || value === 'OPEN') return 'warning'
  return 'neutral'
}

/**
 * 四步处置进度：采集 → 研判 → 审批 → 关闭。
 * 只用告警真实字段推导：有 aiSummary 视为已研判，进入处置/已关闭视为已审批，CLOSED 为已关闭。
 */
function sopSteps(alert) {
  const status = String(alert?.status || '').toUpperCase()
  const steps = [
    { label: '采集', done: true },
    { label: '研判', done: Boolean(alert?.aiSummary) },
    { label: '审批', done: status === 'REMEDIATING' || status === 'CLOSED' },
    { label: '关闭', done: status === 'CLOSED' }
  ]
  const activeIndex = steps.findIndex(step => !step.done)
  return steps.map((step, index) => ({ ...step, active: index === activeIndex }))
}

/** 研判：只产生建议，不改变告警状态、不执行脚本。 */
async function analyze(alert) {
  busyId.value = alert.id
  actionMessage.value = ''
  try {
    const result = await analyzeAlert(alert.id)
    if (!result.ok) { actionMessage.value = result.message; return }
    advice.value = result.advice
    actionMessage.value = '研判已完成，结果标记为「建议」；处置仍需人工确认与审批。'
    await loadSentinel()
  } finally { busyId.value = null }
}

async function notify(alert) {
  busyId.value = alert.id
  actionMessage.value = ''
  try {
    const result = await notifyAlert(alert.id)
    actionMessage.value = result.ok ? describeDelivery(result.results) : result.message
  } finally { busyId.value = null }
}

/**
 * 把逐渠道结果翻译成人话。
 *
 * 关键是**不把没发出去说成已发送**：`not_configured` 与 `rejected` 都要看得见，
 * 否则运维会以为"已经通知到了"。
 */
function describeDelivery(results) {
  if (!results || typeof results !== 'object') return '通知已提交，但未收到逐渠道结果。'
  const labels = { inapp: '站内', email: '邮件', webhook: 'Webhook' }
  const statuses = {
    sent: '已发送', failed: '发送失败',
    not_configured: '未配置（未发送）', rejected: '被拒绝（未发送）'
  }
  return Object.entries(results)
    .map(([channel, status]) => `${labels[channel] ?? channel}：${statuses[status] ?? status}`)
    .join('；')
}

async function sediment(alert) {
  busyId.value = alert.id
  actionMessage.value = ''
  try {
    const result = await createKnowledgeCandidate(alert.id)
    actionMessage.value = result.ok
      ? `已沉淀为知识候选 #${result.candidateId}，等待团队复核后采纳。`
      : result.message
  } finally { busyId.value = null }
}

/* ── 团队审批通道（协作优化 4） ─────────────────────────────────────── */

const proposalFor = ref(null)
const proposalResult = ref(null)
const proposal = reactive({ teamId: '', agentId: '', versionId: '', scriptId: null, runtimeId: '' })

const proposalReady = computed(() => ['teamId', 'agentId', 'versionId', 'runtimeId']
  .every(key => String(proposal[key]).trim().length > 0) && Boolean(proposal.scriptId))

function openProposal(alert) {
  proposalFor.value = alert
  proposalResult.value = null
  actionMessage.value = ''
}

async function submitProposal() {
  busyId.value = proposalFor.value.id
  actionMessage.value = ''
  proposalResult.value = null
  try {
    const result = await proposeRemediation(proposalFor.value.id, {
      teamId: Number(proposal.teamId),
      agentId: Number(proposal.agentId),
      versionId: Number(proposal.versionId),
      scriptId: proposal.scriptId,
      runtimeId: proposal.runtimeId.trim()
    })
    if (!result.ok) { actionMessage.value = result.message; return }
    proposalResult.value = result.proposal
    await loadSentinel()
  } finally { busyId.value = null }
}

/* ── 新建告警规则 ─────────────────────────────────────────────────── */

const creating = ref(false)
const ruleMessage = ref('')
const ruleForm = reactive({
  name: '', templateId: null, severity: 'P2', scriptId: null,
  webhookUrl: '', emailTo: '', channels: ['inapp']
})

const ruleReady = computed(() => ruleForm.name.length > 0 && ruleForm.channels.length > 0)

/** 按级别提示"会不会自动发起"，与后端强制规则一致（P0/P1 恒为人工）。 */
const severityHint = computed(() => {
  const item = ALERT_SEVERITIES.find(severity => severity.id === ruleForm.severity)
  return item?.needsHuman ? `${item.label}：必须人工确认，不会自动发起` : `${item.label}：仍需预览与审批后才执行`
})

async function submitRule() {
  creating.value = true
  ruleMessage.value = ''
  try {
    const result = await createAlertRule({
      name: ruleForm.name,
      templateId: ruleForm.templateId,
      severity: ruleForm.severity,
      scriptId: ruleForm.scriptId,
      notifyChannels: ruleForm.channels.join(','),
      webhookUrl: ruleForm.webhookUrl || null,
      emailTo: ruleForm.emailTo || null
    })
    ruleMessage.value = result.ok ? `已创建规则「${result.rule.name}」` : result.message
    if (result.ok) await loadSentinel()
  } finally { creating.value = false }
}

onMounted(() => { updateMobile(); window.addEventListener('resize', updateMobile); loadSentinel() })
onBeforeUnmount(() => window.removeEventListener('resize', updateMobile))
</script>

<style scoped>
/* T20：告警卡片化 —— 级别 / 状态 / 观测值 / AI 摘要 / 四步 SOP 同屏可读。 */
.alert-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: var(--ds-space-4); }
.alert-card { gap: 12px; }
.alert-card__head { display: flex; align-items: flex-start; gap: 10px; }
.alert-card__title { margin: 0; min-width: 0; color: var(--ds-color-text); font-size: var(--ds-type-h3-size); font-weight: 500; line-height: 1.35; }
.alert-card__head .ui-pill { margin-left: auto; flex: none; }
.alert-card__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; color: var(--ds-color-muted); font-size: var(--ds-type-caption-size); }
.alert-card__meta b { color: var(--ds-color-text); font-weight: 600; }
.alert-card__meta time { margin-left: auto; font-family: var(--ds-font-mono); white-space: nowrap; }
.alert-card__ai {
  margin: 0; padding: 10px 12px;
  border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-color-text) 3%, var(--ds-surface-base));
  color: var(--ds-color-text); font-size: var(--ds-type-body-caption-size); line-height: 1.6;
}
.alert-card__ai.is-empty { color: var(--ds-color-muted); }
.alert-card .ui-sop { flex-wrap: wrap; row-gap: 6px; }
.alert-card__actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: auto; padding-top: 12px; border-top: 1px solid var(--ds-hairline); }
.alert-card__actions button {
  min-height: 30px; padding: 4px 12px;
  border: 1px solid var(--ds-color-border); border-radius: var(--ds-radius-sm);
  background: transparent; color: var(--ds-color-text); font-size: var(--ds-type-caption-size);
  transition: border-color var(--ds-motion-duration) var(--ds-ease-out), color var(--ds-motion-duration) var(--ds-ease-out);
}
.alert-card__actions button:hover:not(:disabled) { border-color: var(--ds-color-primary); color: var(--ds-color-primary); }
.alert-card__actions button:disabled { opacity: .45; cursor: not-allowed; }
@media (max-width: 768px) {
  .alert-grid { grid-template-columns: 1fr; }
  .alert-card__meta time { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) { .alert-card__actions button { transition: none; } }

/* === 启佑风格背景层 === */
.sentinel-shell{position:relative;min-height:calc(100vh - 64px);overflow:hidden;background:radial-gradient(ellipse at 80% 10%,rgba(122,215,245,.10) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(63,185,80,.07) 0%,transparent 50%),#040B16}
.sentinel-shell[data-theme='light']{background:radial-gradient(ellipse at 80% 10%,rgba(26,110,154,.07) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(26,127,55,.04) 0%,transparent 50%),#EAF3FA}
.sentinel-ambient{position:absolute;inset:0;z-index:0;opacity:.48;pointer-events:none}
.sentinel-meteors{position:absolute;inset:0;z-index:0;opacity:.35;pointer-events:none}
.sentinel-aurora{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at 75% 15%,rgba(122,215,245,.22) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(63,185,80,.16) 0%,transparent 45%);filter:blur(24px);background-size:240% 240%;animation:sentinel-drift 22s ease-in-out infinite alternate}
.sentinel-aurora::after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(122,215,245,.35),transparent 70%);filter:blur(18px);animation:sentinel-sweep 32s ease-in-out infinite}
.sentinel-shell[data-theme='light'] .sentinel-aurora{background:radial-gradient(ellipse at 75% 15%,rgba(26,110,154,.14) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(26,127,55,.10) 0%,transparent 45%)}
.sentinel-shell[data-theme='light'] .sentinel-aurora::after{background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(26,110,154,.22),transparent 70%)}
@keyframes sentinel-drift{0%{background-position:0% 0%,100% 100%;transform:translate3d(0,0,0)}100%{background-position:30% 10%,70% 90%;transform:translate3d(-2%,2%,0)}}
@keyframes sentinel-sweep{0%,100%{opacity:.55;transform:translate3d(0,0,0)}50%{opacity:1;transform:translate3d(-8%,4%,0)}}
@media(prefers-reduced-motion:reduce){.sentinel-aurora,.sentinel-aurora::after{animation:none}}
.sentinel-mask{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(4,11,22,.42) 100%)}
.sentinel-shell[data-theme='light'] .sentinel-mask{background:radial-gradient(ellipse at center,transparent 40%,rgba(234,243,250,.42) 100%)}
.sentinel-shell>.sentinel-surface{position:relative;z-index:1}
</style>
