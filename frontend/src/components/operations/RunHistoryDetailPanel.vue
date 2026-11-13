<template>
  <section class="detail-panel" aria-live="polite">
    <div v-if="detailError" class="state error detail-error" role="alert">
      <strong>运行详情暂时无法加载</strong>
      <p>{{ detailError }}</p>
      <button class="button" :disabled="selectedId == null" @click="$emit('retry')">重新加载详情</button>
    </div>
    <div v-else-if="detailLoading" class="state">正在加载证据详情…</div>
    <div v-else-if="!detail" class="state">
      <strong>选择一条运行记录</strong>
      <p>这里将展示完整命令输出和运行证据。</p>
    </div>
    <template v-else>
      <header class="panel-title detail-title">
        <div>
          <p class="eyebrow">TRACE DETAIL</p>
          <h2>{{ detail.run.toolId }}</h2>
        </div>
        <div class="detail-actions">
          <button v-if="!detail.run.isGuide" class="button candidate-button" type="button" :disabled="candidateLoading" @click="$emit('create-candidate')">
            {{ candidateLoading ? '正在生成…' : '沉淀为知识候选' }}
          </button>
          <i :class="runStatusClass(detail.run.status)">{{ runStatusLabel(detail.run.status) }}</i>
        </div>
      </header>
      <div v-if="detail.run.isGuide" class="guide-banner" role="note">
        <strong>虚拟运行记录</strong>
        <span>命令与输出均为示例，未连接真实主机或集群，不能由此生成正式知识候选。</span>
      </div>
      <div v-if="candidate || candidateError" class="candidate-feedback" :class="{ failed: candidateError }" role="status">
        <template v-if="candidate">
          <strong>已生成知识候选</strong>
          <span>状态：{{ candidateStatusLabel(candidate.status) }}</span>
          <span>候选标题：{{ candidate.title }}</span>
          <small>候选内容需经过人工审核后才能成为正式知识。</small>
        </template>
        <template v-else>
          <strong>知识候选生成失败</strong>
          <span>{{ candidateError }}</span>
        </template>
      </div>
      <dl class="facts">
        <div>
          <dt>Trace ID</dt>
          <dd>
            <DecodeText :value="detail.run.traceId" tag="code" />
            <button class="copy" @click="$emit('copy-trace', detail.run.traceId)">{{ copyFailed ? '复制失败，请重试' : copied ? '已复制' : '复制' }}</button>
          </dd>
        </div>
        <div>
          <dt>运行目标</dt>
          <dd>{{ detail.run.runtimeId }}</dd>
        </div>
        <div>
          <dt>会话 ID</dt>
          <dd>{{ detail.run.sessionId ?? '未关联' }}</dd>
        </div>
        <div>
          <dt>执行时间</dt>
          <dd>{{ formatRunTime(detail.run.startedAt) }}</dd>
        </div>
        <div>
          <dt>持续时间</dt>
          <dd>{{ formatDuration(detail.run.startedAt, detail.run.endedAt) }}</dd>
        </div>
      </dl>
      <section class="detail-section">
        <header>
          <h3>命令与输出</h3>
          <span>{{ detail.outputs.length }} 项</span>
        </header>
        <article v-for="output in detail.outputs" :key="output.id" class="command-card">
          <div class="command-head">
            <span>步骤 {{ output.sequenceNo }}</span>
            <b :class="`exit-${outputState(output.exitCode)}`">Exit {{ output.exitCode ?? '未知' }}</b>
          </div>
          <!-- axe scrollable-region-focusable：带 overflow:auto 的区域必须可键盘聚焦 -->
          <pre class="command" tabindex="0" role="region" :aria-label="`步骤 ${output.sequenceNo} 命令`"><code>{{ output.command }}</code></pre>
          <div class="outputs">
            <div>
              <h4>标准输出 stdout <em v-if="output.truncated" class="truncated">已截断</em></h4>
              <pre tabindex="0" role="region" :aria-label="`步骤 ${output.sequenceNo} 标准输出`" :class="{ empty: !visibleOutput(output.stdout) }">{{ visibleOutput(output.stdout) || '无标准输出' }}</pre>
            </div>
            <div>
              <h4>错误输出 stderr <em v-if="output.truncated" class="truncated">已截断</em></h4>
              <pre tabindex="0" role="region" :aria-label="`步骤 ${output.sequenceNo} 错误输出`" :class="{ empty: !visibleOutput(output.stderr) }">{{ visibleOutput(output.stderr) || '无错误输出' }}</pre>
            </div>
          </div>
        </article>
        <p v-if="!detail.outputs.length" class="empty">该运行记录没有命令输出。</p>
      </section>
      <section class="detail-section evidence">
        <header>
          <h3>运行证据</h3>
          <span>{{ detail.evidence.length }} 项</span>
        </header>
        <article v-for="item in detail.evidence" :key="item.id" class="evidence-row">
          <div>
            <b>{{ item.type }}</b>
            <code>{{ item.sourceRef || '无来源引用' }}</code>
          </div>
          <p>{{ item.content }}</p>
          <time>{{ formatRunTime(item.createdAt) }}</time>
        </article>
        <p v-if="!detail.evidence.length" class="empty">该运行记录没有附加证据。</p>
      </section>
    </template>
  </section>
</template>

<script setup>
import DecodeText from '../common/DecodeText.vue'
import { candidateStatusLabel, formatDuration, formatRunTime, outputState, runStatusClass, runStatusLabel, visibleOutput } from './operationRunHistory.js'

defineProps({
  detail: { type: Object, default: null },
  detailLoading: { type: Boolean, default: false },
  detailError: { type: String, default: '' },
  selectedId: { type: [Number, String], default: null },
  candidate: { type: Object, default: null },
  candidateError: { type: String, default: '' },
  candidateLoading: { type: Boolean, default: false },
  copied: { type: Boolean, default: false },
  copyFailed: { type: Boolean, default: false }
})
defineEmits(['retry', 'create-candidate', 'copy-trace'])
</script>

<style scoped>
.detail-panel {
  min-width: 0;
  border: 1px solid var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
  min-height: 520px;
  overflow: hidden auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}
.state {
  padding: 60px 24px;
  text-align: center;
  color: var(--smart-muted);
  font-size: 12px;
}
.state strong {
  color: var(--smart-text);
  font-size: 14px;
}
.error {
  border: 1px solid var(--smart-border);
  border-left: 3px solid #e06b72;
  border-radius: 12px;
  background: var(--smart-surface);
}
.detail-error {
  margin: 16px;
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px;
  border-bottom: 1px solid var(--smart-border);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--smart-surface);
}
.eyebrow {
  margin: 0 0 9px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
h2,h3 {
  margin: 0;
  font-weight: 560;
}
.panel-title h2 {
  font-size: 18px;
}
.detail-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.button {
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  padding: 8px 15px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.candidate-button {
  min-height: 34px;
  padding: 6px 12px;
  border-color: color-mix(in srgb,var(--smart-primary-strong) 55%,var(--smart-border));
  color: var(--smart-primary-strong);
  background: color-mix(in srgb,var(--smart-primary-strong) 8%,var(--smart-surface));
  font-weight: 650;
}
.status {
  font-style: normal;
  font-size: 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 4px 8px;
}
.exit-unknown, .status-unknown {
  color: var(--smart-muted);
}
.status-success,.exit-success {
  color: #4fb58b;
}
.status-failed,.exit-failed {
  color: #e06b72;
}
.status-running {
  color: #d69a50;
}
.status-cancelled {
  color: var(--smart-muted);
}
.guide-banner {
  display: grid;
  gap: 5px;
  padding: 12px 20px;
  border-bottom: 1px solid color-mix(in srgb,#d69a50 45%,var(--smart-border));
  background: color-mix(in srgb,#d69a50 8%,var(--smart-surface));
  font-size: 11px;
}
.guide-banner strong {
  color: #d69a50;
}
.guide-banner span {
  color: var(--smart-muted);
  line-height: 1.5;
}
/* 浅色主题下原高饱和色对比度不足 4.5:1，改用深一档同色系（axe color-contrast 复核通过）。 */
[data-theme='light'] .status-success, [data-theme='light'] .exit-success { color: #0f7b52; }
[data-theme='light'] .status-failed, [data-theme='light'] .exit-failed { color: #b42318; }
[data-theme='light'] .status-running { color: #8a5a11; }
[data-theme='light'] .guide-banner strong { color: #8a5a11; }
.candidate-feedback {
  display: grid;
  grid-template-columns: auto auto minmax(180px,1fr);
  align-items: center;
  gap: 8px 18px;
  padding: 13px 20px;
  border-bottom: 1px solid var(--smart-border);
  border-left: 3px solid #4fb58b;
  background: color-mix(in srgb,#4fb58b 6%,var(--smart-surface));
  font-size: 11px;
}
.candidate-feedback strong {
  font-size: 12px;
}
.candidate-feedback small {
  grid-column: 1/-1;
  color: var(--smart-muted);
}
.candidate-feedback.failed {
  grid-template-columns: auto minmax(0,1fr);
  border-left-color: #e06b72;
  background: color-mix(in srgb,#e06b72 6%,var(--smart-surface));
}
.facts {
  display: grid;
  grid-template-columns: repeat(5,minmax(0,1fr));
  margin: 0;
  border-bottom: 1px solid var(--smart-border);
}
.facts div {
  min-width: 0;
  padding: 16px 18px;
  border-right: 1px solid var(--smart-border);
}
.facts dt {
  color: var(--smart-muted);
  font-size: 10px;
}
.facts dd {
  margin: 8px 0 0;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.facts code {
  font: 11px var(--font-mono);
}
.copy {
  min-height: 26px;
  margin-left: 8px;
  padding: 3px 8px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.detail-section {
  padding: 22px;
}
.detail-section>header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 15px;
}
.detail-section header span {
  color: var(--smart-muted);
  font-size: 11px;
}
.detail-section h3 {
  font-size: 15px;
}
.command-card {
  margin-top: 12px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  overflow: hidden;
}
.command-head {
  display: flex;
  justify-content: space-between;
  padding: 11px 14px;
  color: var(--smart-muted);
  font-size: 10px;
  background: var(--smart-bg);
}
.command {
  margin: 0;
  padding: 14px;
  overflow: auto;
  background: #090d12;
  color: #d8e4ec;
  font: 12px/1.7 var(--font-mono);
}
.outputs {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
.outputs>div {
  min-width: 0;
  padding: 14px;
}
.outputs>div+div {
  border-left: 1px solid var(--smart-border);
}
.outputs h4 {
  margin: 0 0 9px;
  color: var(--smart-muted);
  font-size: 10px;
}
.outputs h4 .truncated {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.16);
  color: #f59e0b;
  font-style: normal;
}
.outputs pre {
  min-height: 54px;
  max-height: 280px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: 11px/1.7 var(--font-mono);
}
.empty {
  color: var(--smart-muted);
  font-style: italic;
}
.evidence {
  border-top: 1px solid var(--smart-border);
}
.evidence-row {
  display: grid;
  grid-template-columns: minmax(150px,.65fr) minmax(0,1.5fr) auto;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--smart-border);
  font-size: 11px;
}
.evidence-row b,.evidence-row code {
  display: block;
}
.evidence-row code,.evidence-row time {
  margin-top: 6px;
  color: var(--smart-muted);
  font: 10px var(--font-mono);
}
.evidence-row p {
  margin: 0;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
button:disabled {
  opacity: .45;
  cursor: wait;
}
button:focus-visible {
  outline: 2px solid var(--smart-primary-strong);
  outline-offset: 3px;
}
@media(max-width:1180px) {
  .facts {
    grid-template-columns: repeat(2,minmax(0,1fr));
  }
}
@media(max-width:800px) {
  .detail-panel {
    overflow: visible;
  }
  .panel-title {
    position: static;
  }
  .outputs {
    grid-template-columns: 1fr;
  }
  .outputs>div+div {
    border-left: 0;
    border-top: 1px solid var(--smart-border);
  }
  .evidence-row {
    grid-template-columns: 1fr;
  }
}
@media(max-width:520px) {
  .facts {
    grid-template-columns: 1fr;
  }
  .detail-title {
    align-items: flex-start;
  }
  .detail-actions {
    align-items: flex-end;
    flex-direction: column;
  }
  .candidate-feedback {
    grid-template-columns: 1fr;
  }
  .candidate-feedback small {
    grid-column: auto;
  }
  .detail-section {
    padding: 17px 14px;
  }
}
</style>
