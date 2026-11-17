<template>
  <section class="ld-page">
    <header class="ld-head">
      <p class="ld-overline">LOG DIAGNOSIS</p>
      <h1>日志诊断</h1>
      <p class="ld-lead">
        粘贴或上传日志，由本地确定性规则引擎匹配常见运维故障指纹；不发起任何网络分析请求，结论仅来自规则命中。
      </p>
    </header>

    <!-- 诚实声明条 -->
    <div class="ld-banner" role="note">
      <span class="ld-banner-dot" aria-hidden="true"></span>
      <strong>确定性规则归因 · 无大模型参与 · 不编造结论</strong>
      <span class="ld-banner-sub">未命中已知指纹时会明确说明，而不是给出推测</span>
    </div>

    <!-- 输入区 -->
    <section class="ld-input-card">
      <div class="ld-input-toolbar">
        <span class="ld-toolbar-label">日志内容</span>
        <span class="ld-toolbar-meta">{{ inputMeta }}</span>
        <label class="ld-upload-btn">
          选择日志文件（.log / .txt，≤5MB）
          <input
            ref="fileInput"
            class="ld-file-input"
            type="file"
            accept=".log,.txt,text/plain"
            @change="onFileChange"
          />
        </label>
        <button
          v-if="logText"
          type="button"
          class="ld-btn ld-btn-ghost"
          @click="clearInput"
        >清空</button>
      </div>
      <textarea
        v-model="logText"
        class="ld-textarea"
        rows="10"
        placeholder="粘贴日志文本，例如应用 stdout、系统日志、容器日志……"
        spellcheck="false"
      ></textarea>
      <p v-if="fileError" class="ld-error" role="alert">{{ fileError }}</p>
      <div class="ld-input-actions">
        <button
          type="button"
          class="ld-btn ld-btn-primary"
          :disabled="!logText.trim()"
          @click="runDiagnosis"
        >开始诊断</button>
      </div>
    </section>

    <!-- 结果区 -->
    <template v-if="result">
      <!-- 统计条 -->
      <section class="ld-stats" aria-label="诊断统计">
        <div class="ld-stat">
          <span class="ld-stat-label">总行数</span>
          <span class="ld-stat-value">{{ result.stats.totalLines }}</span>
        </div>
        <div class="ld-stat">
          <span class="ld-stat-label">错误行数</span>
          <span class="ld-stat-value">{{ result.stats.errorLines }}</span>
        </div>
        <div class="ld-stat">
          <span class="ld-stat-label">级别分布</span>
          <span class="ld-stat-value ld-levels">
            <span class="ld-level ld-level-error">ERROR {{ result.stats.levelDist.ERROR }}</span>
            <span class="ld-level ld-level-warn">WARN {{ result.stats.levelDist.WARN }}</span>
            <span class="ld-level ld-level-info">INFO {{ result.stats.levelDist.INFO }}</span>
          </span>
        </div>
        <div class="ld-stat">
          <span class="ld-stat-label">命中指纹</span>
          <span class="ld-stat-value">{{ result.issues.length }} 条</span>
        </div>
      </section>

      <p v-if="result.stats.truncated" class="ld-truncate-note" role="note">
        日志超过 200KB，已截断：统计与结论仅基于前 200KB 内容。
      </p>

      <!-- 摘要 -->
      <div class="ld-summary" role="status">{{ result.summary }}</div>

      <!-- 问题卡列表 -->
      <section v-if="result.issues.length" class="ld-issues" aria-label="命中的故障指纹">
        <article
          v-for="issue in result.issues"
          :key="issue.ruleId"
          class="ld-issue"
          :class="`ld-issue-${issue.severity.toLowerCase()}`"
        >
          <header class="ld-issue-head">
            <h2 class="ld-issue-name">{{ issue.name }}</h2>
            <span class="ld-severity" :class="`ld-severity-${issue.severity.toLowerCase()}`">{{ issue.severity }}</span>
            <span class="ld-issue-category">{{ issue.category }}</span>
            <span class="ld-issue-count">命中 {{ issue.matchCount }} 行</span>
          </header>
          <p class="ld-issue-row"><span class="ld-issue-label">成因</span>{{ issue.reason }}</p>
          <p class="ld-issue-row"><span class="ld-issue-label">处置建议</span>{{ issue.recommendation }}</p>
          <p class="ld-issue-row">
            <span class="ld-issue-label">检索关键词</span>
            <span class="ld-keywords">
              <span v-for="kw in issue.keywords" :key="kw" class="ld-keyword">{{ kw }}</span>
            </span>
          </p>
          <!-- 命中行上下文折叠展示 -->
          <details class="ld-matches">
            <summary>命中行（已脱敏，前 {{ issue.matches.length }} 条样本，行号 {{ issue.lineNumbers.slice(0, 6).join(', ') }}{{ issue.lineNumbers.length > 6 ? '…' : '' }}）</summary>
            <pre class="ld-match-pre"><code>{{ issue.matches.join('\n') }}</code></pre>
          </details>
        </article>
      </section>

      <!-- 运维经验匹配：自学习闭环的回灌侧——沉淀/蒸馏的经验在这里反哺诊断 -->
      <section class="ld-exp" aria-label="运维经验匹配">
        <header class="ld-exp-head">
          <h2 class="ld-exp-title">运维经验匹配</h2>
          <span class="ld-exp-sub">按最高严重级指纹检索运维经验库</span>
        </header>
        <p v-if="expLoading" class="ld-exp-note" role="status">正在检索经验库…</p>
        <template v-else>
          <ul v-if="expMatches.length" class="ld-exp-list">
            <li v-for="(m, i) in expMatches" :key="i" class="ld-exp-item">
              <p class="ld-exp-action">{{ m.action }}</p>
              <p class="ld-exp-meta">
                <span class="ld-exp-source">{{ expSourceLabel(m.source) }}</span>
                <span class="ld-exp-conf">置信度 {{ Math.round((m.confidence || 0) * 100) }}%</span>
                <span v-if="m.sourceRefs" class="ld-exp-refs">来源 {{ m.sourceRefs }}</span>
              </p>
              <p v-if="m.verification" class="ld-exp-verify">{{ m.verification }}</p>
            </li>
          </ul>
          <p v-else-if="expError" class="ld-exp-note">经验库检索失败，已跳过（不影响诊断结论）。</p>
          <p v-else class="ld-exp-note">
            经验库暂无匹配的历史处理动作。经验由决策闭环与哨兵蒸馏自动沉淀——处理过同类工单后，下次诊断会在这里给出建议。
          </p>
        </template>
      </section>

      <!-- 未解释错误样本 -->
      <details v-if="result.unmatchedErrorSamples.length" class="ld-unmatched">
        <summary>未解释错误样本（{{ result.unmatchedErrorCount }} 行不符合任何指纹，仅展示前 {{ result.unmatchedErrorSamples.length }} 条）</summary>
        <pre class="ld-match-pre"><code>{{ result.unmatchedErrorSamples.join('\n') }}</code></pre>
      </details>

      <!-- 操作区 -->
      <section class="ld-actions">
        <button type="button" class="ld-btn ld-btn-ghost" @click="copyReport">复制诊断报告</button>
        <button
          type="button"
          class="ld-btn ld-btn-primary"
          :disabled="saving"
          @click="saveAsCandidate"
        >{{ saving ? '正在沉淀…' : '沉淀为知识候选' }}</button>
      </section>

      <p v-if="actionMessage" class="ld-action-message" :class="{ 'ld-action-error': actionIsError }" role="status">
        {{ actionMessage }}
      </p>
      <p v-if="savedCandidate" class="ld-saved-tip">
        已进入知识候选队列（待人工审核），请前往
        <RouterLink class="ld-link" to="/knowledge/review">知识审核页</RouterLink>
        完成审核后才会发布。
      </p>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { analyzeLog, toMarkdown } from '../../utils/logDiagnosisEngine.js'
import { post } from '../../utils/request'

/* ---------------- 输入状态 ---------------- */

const MAX_FILE_BYTES = 5 * 1024 * 1024 // 文件上限 5MB

const logText = ref('')
const fileError = ref('')
const fileInput = ref(null)
const result = ref(null)

const inputMeta = computed(() => {
  const chars = logText.value.length
  return chars === 0 ? '尚未输入' : `${chars} 字符`
})

/** 文件选择：仅接受 .log/.txt，≤5MB，FileReader 读取为文本 */
function onFileChange(event) {
  fileError.value = ''
  const file = event.target.files && event.target.files[0]
  if (!file) return
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.log') && !lower.endsWith('.txt')) {
    fileError.value = '仅支持 .log 或 .txt 文本日志文件。'
    event.target.value = ''
    return
  }
  if (file.size > MAX_FILE_BYTES) {
    fileError.value = `文件超过 5MB 上限（当前 ${Math.round(file.size / 1024 / 1024 * 10) / 10}MB），请先拆分或截取关键片段。`
    event.target.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    logText.value = String(reader.result || '')
  }
  reader.onerror = () => {
    fileError.value = '文件读取失败，请重试或直接粘贴日志内容。'
  }
  reader.readAsText(file)
}

function clearInput() {
  logText.value = ''
  fileError.value = ''
  result.value = null
  actionMessage.value = ''
  savedCandidate.value = null
  if (fileInput.value) fileInput.value.value = ''
}

/* ---------------- 诊断执行 ---------------- */

function runDiagnosis() {
  actionMessage.value = ''
  savedCandidate.value = null
  result.value = analyzeLog(logText.value)
}

/* ---------------- 报告复制 ---------------- */

const actionMessage = ref('')
const actionIsError = ref(false)

/** 复制 Markdown 报告；clipboard 失败时降级为 execCommand */
async function copyReport() {
  if (!result.value) return
  const markdown = toMarkdown(result.value)
  try {
    await navigator.clipboard.writeText(markdown)
    notify('诊断报告已复制到剪贴板（Markdown 格式）。', false)
  } catch {
    const fallbackOk = fallbackCopy(markdown)
    notify(
      fallbackOk ? '诊断报告已复制到剪贴板（降级方式）。' : '复制失败：浏览器拒绝了剪贴板访问，请手动选择报告内容复制。',
      !fallbackOk
    )
  }
}

function fallbackCopy(text) {
  const helper = document.createElement('textarea')
  helper.value = text
  helper.setAttribute('readonly', '')
  helper.style.position = 'fixed'
  helper.style.opacity = '0'
  document.body.appendChild(helper)
  helper.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(helper)
  return ok
}

/* ---------------- 沉淀为知识候选 ---------------- */

const saving = ref(false)
const savedCandidate = ref(null)

/**
 * 一键沉淀：走现有知识候选闸门，POST /api/knowledge/candidates/from-log-diagnosis。
 * 未登录 / 失败时给出错误提示并降级为仅复制（诊断结果仍可手动带走）。
 */
async function saveAsCandidate() {
  if (!result.value || saving.value) return
  saving.value = true
  actionMessage.value = ''
  savedCandidate.value = null
  const title = `日志诊断 · ${new Date().toLocaleString('zh-CN', { hour12: false })} · ${result.value.issues.length} 条指纹命中`
  try {
    const response = await post('/api/knowledge/candidates/from-log-diagnosis', {
      title,
      contentMarkdown: toMarkdown(result.value)
    })
    savedCandidate.value = response.data || true
    notify('已沉淀为知识候选（待人工审核），请前往知识审核页完成审核。', false)
  } catch (error) {
    actionIsError.value = true
    notify(`沉淀失败：${error && error.message ? error.message : '请求失败'}。已降级为仅复制模式，可点击「复制诊断报告」带走结果。`, true)
    /* 失败后自动降级：直接执行一次复制，保证结果不丢 */
    try {
      await navigator.clipboard.writeText(toMarkdown(result.value))
    } catch { /* 降级复制失败时保留提示即可 */ }
  } finally {
    saving.value = false
  }
}

function notify(message, isError) {
  actionIsError.value = Boolean(isError)
  actionMessage.value = message
}
</script>

<style scoped>
/* 页面骨架：全部使用 --ds-* 设计令牌，深浅色随主题自适应 */
.ld-page {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-6);
  padding: var(--ds-space-6);
  max-width: 960px;
  margin: 0 auto;
  color: var(--ds-color-text);
}

.ld-head .ld-overline {
  margin: 0;
  font-size: var(--ds-type-overline-size);
  font-weight: var(--ds-type-overline-weight);
  letter-spacing: .12em;
  color: var(--ds-color-muted);
}

.ld-head h1 {
  margin: var(--ds-space-1) 0;
  font-size: var(--ds-type-h1-size);
  font-weight: var(--ds-type-h1-weight);
}

.ld-head .ld-lead {
  margin: 0;
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-muted);
}

/* 诚实声明条 */
.ld-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
  padding: var(--ds-space-3) var(--ds-space-4);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-pill-info-bg);
  font-size: var(--ds-type-body-caption-size);
}

.ld-banner-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--ds-radius-pill);
  background: var(--ds-semantic-info);
  flex: none;
}

.ld-banner-sub {
  color: var(--ds-color-muted);
}

/* 输入区 */
.ld-input-card {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3);
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-surface-raised);
  box-shadow: var(--ds-elevation-1);
}

.ld-input-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--ds-space-3);
}

.ld-toolbar-label {
  font-size: var(--ds-type-section-size);
  font-weight: var(--ds-type-section-weight);
}

.ld-toolbar-meta {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
  font-variant-numeric: var(--ds-type-num);
}

.ld-upload-btn {
  display: inline-flex;
  align-items: center;
  padding: 0 var(--ds-space-3);
  height: var(--ds-control-height);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  font-size: var(--ds-type-body-caption-size);
  cursor: pointer;
  transition: border-color var(--ds-duration-fast) var(--ds-ease-out), background var(--ds-duration-fast) var(--ds-ease-out);
}

.ld-upload-btn:hover {
  border-color: var(--ds-color-primary);
  background: var(--smart-primary-soft);
}

.ld-file-input {
  display: none;
}

.ld-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-surface-overlay);
  color: var(--ds-color-text);
  font-family: var(--ds-font-mono);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  resize: vertical;
  transition: border-color var(--ds-duration-fast) var(--ds-ease-out);
}

.ld-textarea:focus-visible {
  outline: none;
  border-color: var(--ds-focus-ring-color);
  box-shadow: 0 0 0 var(--ds-focus-ring-width) var(--ds-focus-ring-color);
}

.ld-error {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-semantic-danger);
}

.ld-input-actions {
  display: flex;
  gap: var(--ds-space-3);
}

/* 按钮 */
.ld-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--ds-control-height);
  padding: 0 var(--ds-space-6);
  border-radius: var(--ds-radius-md);
  border: 1px solid transparent;
  font-size: var(--ds-type-body-size);
  cursor: pointer;
  transition: opacity var(--ds-duration-fast) var(--ds-ease-out), border-color var(--ds-duration-fast) var(--ds-ease-out), background var(--ds-duration-fast) var(--ds-ease-out);
}

.ld-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.ld-btn-primary {
  background: var(--ds-color-primary);
  color: var(--smart-primary-foreground);
}

.ld-btn-primary:hover:not(:disabled) {
  opacity: .9;
}

.ld-btn-ghost {
  background: transparent;
  color: var(--ds-color-text);
  border-color: var(--ds-color-border-strong);
}

.ld-btn-ghost:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
}

/* 统计条 */
.ld-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--ds-space-3);
}

.ld-stat {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-1);
  padding: var(--ds-space-3) var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-surface-raised);
}

.ld-stat-label {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.ld-stat-value {
  font-size: var(--ds-font-xl);
  font-weight: 300;
  font-variant-numeric: var(--ds-type-num);
}

.ld-levels {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
  font-size: var(--ds-type-caption-size);
}

.ld-level {
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
}

.ld-level-error {
  color: var(--ds-pill-danger-fg);
  background: var(--ds-pill-danger-bg);
}

.ld-level-warn {
  color: var(--ds-pill-warning-fg);
  background: var(--ds-pill-warning-bg);
}

.ld-level-info {
  color: var(--ds-pill-info-fg);
  background: var(--ds-pill-info-bg);
}

.ld-truncate-note {
  margin: 0;
  padding: var(--ds-space-2) var(--ds-space-3);
  border-radius: var(--ds-radius-md);
  background: var(--ds-pill-warning-bg);
  color: var(--ds-pill-warning-fg);
  font-size: var(--ds-type-caption-size);
}

.ld-summary {
  padding: var(--ds-space-3) var(--ds-space-4);
  border-left: 3px solid var(--ds-color-primary);
  border-radius: var(--ds-radius-sm);
  background: var(--ds-surface-raised);
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-height-base);
}

/* 问题卡 */
.ld-issues {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-4);
}

.ld-issue {
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-left-width: 3px;
  border-radius: var(--ds-radius-md);
  background: var(--ds-surface-raised);
}

.ld-issue-critical {
  border-left-color: var(--ds-semantic-danger);
}

.ld-issue-error {
  border-left-color: var(--ds-semantic-warning);
}

.ld-issue-warn {
  border-left-color: var(--ds-semantic-info);
}

.ld-issue-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
  margin-bottom: var(--ds-space-3);
}

.ld-issue-name {
  margin: 0;
  font-size: var(--ds-type-h3-size);
  font-weight: var(--ds-type-h3-weight);
}

.ld-severity {
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-type-caption-size);
  font-weight: 600;
  font-variant-numeric: var(--ds-type-num);
}

.ld-severity-critical {
  color: var(--ds-pill-danger-fg);
  background: var(--ds-pill-danger-bg);
}

.ld-severity-error {
  color: var(--ds-pill-warning-fg);
  background: var(--ds-pill-warning-bg);
}

.ld-severity-warn {
  color: var(--ds-pill-info-fg);
  background: var(--ds-pill-info-bg);
}

.ld-issue-category,
.ld-issue-count {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.ld-issue-row {
  display: flex;
  gap: var(--ds-space-2);
  margin: 0 0 var(--ds-space-2);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-base);
}

.ld-issue-label {
  flex: none;
  color: var(--ds-color-muted);
}

.ld-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-1);
}

.ld-keyword {
  padding: 1px var(--ds-space-2);
  border: 1px solid var(--ds-tag-border);
  border-radius: var(--ds-tag-radius);
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

/* 命中行折叠 */
.ld-matches,
.ld-unmatched {
  margin-top: var(--ds-space-2);
}

.ld-matches summary,
.ld-unmatched summary {
  cursor: pointer;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
  user-select: none;
}

.ld-match-pre {
  margin: var(--ds-space-2) 0 0;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-sm);
  background: var(--ds-surface-overlay);
  overflow: auto;
  max-height: 240px;
  font-family: var(--ds-font-mono);
  font-size: var(--ds-type-caption-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-text);
}

/* 操作区 */
.ld-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-3);
}

.ld-action-message {
  margin: 0;
  font-size: var(--ds-type-body-caption-size);
  color: var(--ds-color-text);
}

.ld-action-error {
  color: var(--ds-semantic-danger);
}

.ld-saved-tip {
  margin: 0;
  padding: var(--ds-space-3) var(--ds-space-4);
  border-radius: var(--ds-radius-md);
  background: var(--ds-pill-success-bg);
  color: var(--ds-pill-success-fg);
  font-size: var(--ds-type-body-caption-size);
}

.ld-link {
  color: var(--ds-color-primary);
  text-decoration: underline;
}

/* 动效降级：系统减少动态效果时全量关闭过渡 */
@media (prefers-reduced-motion: reduce) {
  .ld-page *,
  .ld-page *::before,
  .ld-page *::after {
    transition: none !important;
    animation: none !important;
  }
}
</style>
