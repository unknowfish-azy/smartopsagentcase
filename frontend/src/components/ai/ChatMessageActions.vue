<template>
  <div class="cma-bar" role="group" :aria-label="`消息操作 · ${message.id}`">
    <button type="button" class="cma-btn" @click="copy">复制</button>
    <button type="button" class="cma-btn" @click="$emit('followup', message.prompt || '')">追问</button>
    <button type="button" class="cma-btn" :disabled="saving" @click="save">收藏</button>
    <button type="button" class="cma-btn" @click="forward">转发</button>
    <button type="button" class="cma-btn" :disabled="Boolean(feedback)" @click="openFeedback">反馈</button>
    <span v-if="notice" class="cma-notice" role="status">{{ notice }}</span>
    <span v-if="feedback" class="cma-state" :class="`cma-state--${feedbackClass}`">
      {{ feedbackLabel }}
      <button v-if="feedback.status === 'REVIEW_FAILED'" type="button" class="cma-retry" @click="retry">重试复核</button>
    </span>
  </div>

  <div v-if="dialogOpen" class="cma-backdrop" @click.self="dialogOpen = false">
    <section class="cma-dialog" role="dialog" aria-modal="true" aria-labelledby="cma-dialog-title">
      <header><h2 id="cma-dialog-title">反馈这条回答</h2><button type="button" aria-label="关闭" @click="dialogOpen = false">×</button></header>
      <p class="cma-dialog-hint">反馈意味着原有知识可能有问题。提交后 Agent 会<b>暂时忽略原答案</b>，用真实知识库重新独立思考并核对引用；结论需要人工审核后才会对所有用户可见。</p>
      <label>问题类型
        <select v-model="issueType">
          <option value="事实错误">事实错误</option><option value="引用错误">引用错误</option>
          <option value="答案不完整">答案不完整</option><option value="信息过时">信息过时</option><option value="其他">其他</option>
        </select>
      </label>
      <label>问题描述（至少 10 字）
        <textarea v-model="description" rows="4" :aria-invalid="Boolean(error)" placeholder="请说明哪里不对、为什么不对"></textarea>
      </label>
      <label>期望修正（选填）<textarea v-model="expected" rows="2" placeholder="你希望正确的答案是什么"></textarea></label>
      <p v-if="error" class="cma-error" role="alert">{{ error }}</p>
      <footer>
        <button type="button" class="cma-btn" @click="dialogOpen = false">取消</button>
        <button type="button" class="cma-primary" :disabled="submitting" @click="submit">{{ submitting ? 'Agent 复核中…' : '提交反馈' }}</button>
      </footer>
    </section>
  </div>
</template>

<script setup>
/**
 * 消息级操作栏：复制 / 追问 / 收藏 / 转发 / 反馈。
 * 反馈链路：提交 → 后端 Agent 真独立复核（忽略原答案 + 真实检索）→ PENDING_REVIEW 候选；
 * 审核 promote 后才进全员共享库。本组件只展示结论，不伪造"已验证"。
 */
import { onMounted, ref } from 'vue'
import { submitChatFeedback, getChatFeedbackByMessage, retryChatFeedback } from '../../api/chatFeedback.ts'
import { listKnowledgeLibraries, createKnowledgeEntry } from '../../api/personalKnowledge.ts'

const props = defineProps({
  message: { type: Object, required: true },
  conversationId: { type: String, default: '' }
})
defineEmits(['followup'])

const notice = ref('')
const saving = ref(false)
const dialogOpen = ref(false)
const issueType = ref('事实错误')
const description = ref('')
const expected = ref('')
const error = ref('')
const submitting = ref(false)
const feedback = ref(null)

const statusMap = {
  REVIEWING: ['复核中', 'reviewing'],
  REVIEWED: ['已复核', 'done'],
  CONFIRMED: ['已确认有误 · 待审核', 'confirmed'],
  UNCONFIRMED: ['证据不足 · 无法确认', 'uncertain'],
  ORIGINAL_OK: ['复核认为原答案正确', 'ok'],
  REVIEW_FAILED: ['复核失败', 'failed']
}
const feedbackLabel = ref('')
const feedbackClass = ref('done')
function syncFeedback() {
  const state = feedback.value?.reviewConclusion || feedback.value?.status
  const [label, tone] = statusMap[state] || [state || '已提交', 'done']
  feedbackLabel.value = label
  feedbackClass.value = tone
}

function flash(text) {
  notice.value = text
  window.setTimeout(() => { if (notice.value === text) notice.value = '' }, 2200)
}
async function copy() {
  try { await navigator.clipboard.writeText(props.message.content || ''); flash('已复制') }
  catch { flash('复制失败') }
}
async function save() {
  saving.value = true
  try {
    const unwrap = response => response?.data ?? response
    const list = unwrap(await listKnowledgeLibraries())
    const libraries = Array.isArray(list) ? list : (list?.items || [])
    if (!libraries.length) { flash('请先创建一个个人知识库'); return }
    await createKnowledgeEntry(libraries[0].id, {
      title: String(props.message.prompt || 'AI 回答').slice(0, 40),
      contentMarkdown: props.message.content || '',
      sourceType: 'CHAT_SAVED',
      sourceRef: props.message.id
    })
    flash('已收藏到个人知识库')
  } catch { flash('收藏失败') }
  finally { saving.value = false }
}
function forward() {
  const text = `来自 SmartOps Agent 的回答：\n\n问题：${props.message.prompt || '—'}\n\n${props.message.content || ''}`
  navigator.clipboard.writeText(text).then(() => flash('已复制可转发文本')).catch(() => flash('复制失败'))
}
function openFeedback() {
  issueType.value = '事实错误'; description.value = ''; expected.value = ''; error.value = ''
  dialogOpen.value = true
}
async function submit() {
  if (description.value.trim().length < 10) { error.value = '问题描述至少需要 10 个字'; return }
  error.value = ''
  submitting.value = true
  try {
    const unwrap = response => response?.data ?? response
    feedback.value = unwrap(await submitChatFeedback({
      conversationId: props.conversationId,
      messageId: props.message.id,
      prompt: props.message.prompt || '',
      originalAnswer: props.message.content || '',
      issueType: issueType.value,
      description: description.value.trim(),
      expected: expected.value.trim() || undefined
    }))
    syncFeedback()
    dialogOpen.value = false
    flash('已提交，Agent 已完成独立复核')
  } catch (cause) {
    error.value = cause?.response?.data?.message || cause?.message || '提交失败'
  } finally { submitting.value = false }
}
async function retry() {
  if (!feedback.value?.id) return
  submitting.value = true
  try {
    const unwrap = response => response?.data ?? response
    feedback.value = unwrap(await retryChatFeedback(feedback.value.id))
    syncFeedback()
  } catch (cause) { flash(cause?.message || '重试失败') }
  finally { submitting.value = false }
}
onMounted(async () => {
  try {
    const unwrap = response => response?.data ?? response
    const result = unwrap(await getChatFeedbackByMessage(props.message.id))
    if (result && result.id) { feedback.value = result; syncFeedback() }
  } catch { /* 没有反馈记录属正常 */ }
})
</script>

<style scoped>
.cma-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--ds-hairline, var(--smart-border)); }
.cma-btn, .cma-primary { min-height: 26px; padding: 3px 9px; border: 1px solid var(--smart-border); border-radius: 6px; background: transparent; color: var(--smart-muted); font: 11px var(--font-cn); cursor: pointer; }
.cma-btn:hover:not(:disabled) { color: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }
.cma-btn:disabled { opacity: .5; cursor: default; }
.cma-primary { color: var(--smart-bg); background: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }
.cma-notice { color: var(--smart-primary-strong); font-size: 11px; }
.cma-state { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--smart-border); font-size: 10px; color: var(--smart-muted); }
.cma-state--confirmed { color: var(--ds-semantic-danger); border-color: color-mix(in srgb, var(--ds-semantic-danger) 50%, transparent); }
.cma-state--ok { color: var(--ds-color-success); border-color: color-mix(in srgb, var(--ds-color-success) 50%, transparent); }
.cma-state--uncertain { color: var(--ds-semantic-warning); border-color: color-mix(in srgb, var(--ds-semantic-warning) 50%, transparent); }
.cma-retry { border: 0; background: transparent; color: inherit; text-decoration: underline; cursor: pointer; font-size: 10px; }
.cma-backdrop { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; background: rgba(0,0,0,.52); }
.cma-dialog { width: min(460px, calc(100vw - 32px)); max-height: 88dvh; overflow-y: auto; display: grid; gap: 12px; padding: 20px; border: 1px solid var(--smart-border-strong); border-radius: 12px; background: var(--smart-surface); color: var(--smart-text); }
.cma-dialog header { display: flex; justify-content: space-between; align-items: center; }
.cma-dialog h2 { margin: 0; font-size: 16px; font-weight: 500; }
.cma-dialog header button { border: 0; background: transparent; color: var(--smart-muted); font-size: 20px; cursor: pointer; }
.cma-dialog-hint { margin: 0; color: var(--smart-muted); font-size: 12px; line-height: 1.7; }
.cma-dialog label { display: grid; gap: 6px; font-size: 12px; }
.cma-dialog select, .cma-dialog textarea { width: 100%; padding: 8px; border: 1px solid var(--smart-border); border-radius: 6px; background: var(--smart-bg); color: var(--smart-text); font: inherit; }
.cma-dialog footer { display: flex; justify-content: flex-end; gap: 8px; }
.cma-error { margin: 0; color: var(--ds-semantic-danger); font-size: 12px; }
@media (prefers-reduced-motion: reduce) { .cma-btn, .cma-primary { transition: none; } }
</style>
