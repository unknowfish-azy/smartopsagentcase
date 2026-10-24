<template>
  <div class="attachment-composer">
    <div class="visual-actions" aria-label="视觉证据工具"><button type="button" :disabled="busy || store.sending || visualBusy" @click="capture('SCREENSHOT')">截取屏幕</button><button type="button" :disabled="busy || store.sending || visualBusy" @click="capture('CAMERA')">拍照</button></div>
    <input ref="input" class="attachment-input" type="file" multiple accept=".png,.jpg,.jpeg,.txt,.log,.md" aria-label="选择聊天附件" @change="choose" />
    <div v-if="queue.items.length" class="attachment-tray" aria-label="待发送附件">
      <article v-for="item in queue.items" :key="item.id" class="attachment-draft">
        <button v-if="item.preview" type="button" class="attachment-thumb" :aria-label="`预览 ${item.file.name}`" @click="preview = item"><img :src="item.preview" alt="待发送图片缩略图" /></button>
        <div class="attachment-description"><strong>{{ item.file.name }}</strong><small>{{ size(item.file.size) }} · {{ labels[item.status] }}</small><span v-if="item.error" role="alert">{{ item.error }}</span></div>
        <button type="button" :disabled="busy" :aria-label="`移除 ${item.file.name}`" @click="remove(item)">移除</button>
      </article>
    </div>
    <p v-if="store.activeConversation?.remote" class="attachment-notice">个人私有附件会话 · 仅保存证据，尚未接入 OCR / 看图分析。请先在本地遮盖密码、密钥等敏感信息；旧文本历史不会上传。未发送附件刷新后丢失。</p>
    <p v-else-if="queue.items.length" class="attachment-notice">图像证据随消息参与 AI 分析（当前仅发送文件名进行模拟解析，图片内容保留在本地不上传）。</p>
    <p v-if="queue.error || error" class="attachment-error" role="alert">{{ queue.error || error }}</p>
    <div v-if="error && !busy" class="attachment-recovery"><button type="button" @click="store.loadRemoteDetail(store.activeId)">核对服务端记录</button><button type="button" @click="discard">丢弃本地附件草稿</button></div>
    <button v-if="busy" type="button" class="attachment-cancel" @click="cancel">取消本次发送</button>
    <el-dialog v-model="previewOpen" title="发送前预览" width="min(800px, 94vw)" append-to-body class="chat-attachment-dialog" @closed="preview = null">
      <img v-if="preview" class="attachment-preview" :src="preview.preview" :alt="preview.file.name" />
      <p>此处只预览，未发送给服务器。需要裁剪或遮盖时，请先用本地图片工具处理后重新选择。</p>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAiChatStore } from '../../stores/aiChat.js'
import { createAttachmentQueue, attachmentFiles } from '../../domain/chat/attachments.ts'
import { captureCamera, captureScreen } from '../../domain/chat/visualCapture.ts'
import { chatAttachmentsApi } from '../../api/chatAttachments.ts'

const store = useAiChatStore()
const emit = defineEmits(['context-change'])
const input = ref(null)
const queue = reactive(createAttachmentQueue())
const busy = ref(false)
const error = ref('')
const preview = ref(null)
const previewOpen = computed({ get: () => Boolean(preview.value), set: value => { if (!value) preview.value = null } })
const labels = { staged: '待发送', uploading: '上传中', uploaded: '已上传，待保存消息', failed: '上传失败，发送可重试' }
const count = computed(() => queue.items.length)
const visualBusy = ref(false)
let controller = null
let submission = null
let generation = 0
let disposed = false

function size(bytes) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` }
function pick() { if (!busy.value && !store.sending) input.value?.click() }
const isImageFile = file => /\.(png|jpe?g)$/i.test(file?.name || '')
function add(files, source = 'FILE') {
  if (busy.value || store.sending || !files.length) return
  if (!store.activeConversation?.remote) {
    // 普通文本会话：图像作为证据本地暂存、随消息参与 AI 分析（仅文件名）；
    // 一旦混入文本/日志附件，整组转为私有附件会话保存，不参与模型分析。
    const images = files.filter(isImageFile)
    const rest = files.filter(file => !isImageFile(file))
    if (images.length && !rest.length) { queue.add(images, source); return }
    const previousId = store.activeId
    queue.add(files, source)
    const accepted = queue.items.map(item => item.file)
    const validationError = queue.error
    if (!accepted.length) return
    const conversation = store.prepareAttachmentConversation()
    emit('context-change', { previousId, nextId: conversation.id })
    queue.add(accepted, source)
    queue.error = validationError
    return
  }
  queue.add(files, source)
}
function choose(event) { add(Array.from(event.target.files || []), 'FILE'); event.target.value = '' }
async function capture(kind) {
  if (visualBusy.value) return
  visualBusy.value = true; error.value = ''
  try { add([await (kind === 'SCREENSHOT' ? captureScreen() : captureCamera())], kind) }
  catch (cause) { error.value = cause.message === 'VISUAL_PERMISSION_DENIED' ? '视觉权限被拒绝，可继续使用文件上传、粘贴或拖拽。' : (cause.message || '无法获取视觉证据') }
  finally { visualBusy.value = false }
}
function paste(event) {
  const files = attachmentFiles(event.clipboardData)
  if (files.length) { event.preventDefault(); add(files, 'CLIPBOARD') }
}
function drop(event) { event.preventDefault(); add(attachmentFiles(event.dataTransfer), 'DRAG_DROP') }
async function remove(item) {
  if (busy.value) return
  const epoch = generation
  const conversationId = store.activeId
  if (item.stored) {
    try { await chatAttachmentsApi.remove(conversationId, item.stored.id) }
    catch (failure) { if (epoch === generation) error.value = `移除失败：${failure.message}`; return }
  }
  if (epoch !== generation) return
  queue.remove(item.id); submission = null; error.value = ''
}
function reset() {
  generation++; controller?.abort(); controller = null
  queue.clear(); busy.value = false; error.value = ''; preview.value = null; submission = null
}
function cancel() { controller?.abort() }
function discard() { if (window.confirm('只丢弃本地草稿，已发送的消息不会删除；未发送的服务端暂存附件会过期清理。确定继续？')) reset() }
function confirmLeave() {
  return (!queue.items.length && !busy.value) || window.confirm('切换会清除未发送的附件并取消请求。已上传但未发送的暂存文件将过期清理，确定继续？')
}
function beforeUnload(event) { if (queue.items.length || busy.value) { event.preventDefault(); event.returnValue = '' } }

async function submit(text) {
  if (busy.value || store.remoteLoading || (!text.trim() && !queue.items.length)) return false
  const conversation = store.activeConversation
  if (!conversation?.remote) return false
  store.invalidateRemoteReads()
  const epoch = generation
  const account = store.accountEpoch
  const stillCurrent = () => !disposed && epoch === generation && account === store.accountEpoch && store.activeId === conversation.id
  const fingerprint = JSON.stringify([text.trim(), queue.items.map(item => item.id)])
  if (!submission || submission.fingerprint !== fingerprint) submission = { fingerprint, requestId: crypto.randomUUID() }
  controller = new AbortController()
  const signal = controller.signal
  busy.value = true; error.value = ''
  try {
    if (!conversation.backed) {
      await chatAttachmentsApi.create(conversation)
      if (!stillCurrent() || signal.aborted) throw new Error('发送已取消')
      conversation.backed = true
    }
    const attachments = await queue.upload((file, requestId, sourceType) => {
      if (!stillCurrent() || signal.aborted) throw new Error('发送已取消')
      return chatAttachmentsApi.upload(conversation.id, file, requestId, signal, sourceType)
    })
    if (!stillCurrent() || signal.aborted) throw new Error('发送已取消')
    const detail = await chatAttachmentsApi.append(conversation.id, { requestId: submission.requestId, text: text.trim(), attachmentIds: attachments.map(item => item.id) }, signal)
    if (!stillCurrent()) return false
    store.invalidateRemoteReads()
    Object.assign(conversation, detail, { remote: true, backed: true })
    queue.clear(); submission = null
    return true
  } catch (failure) {
    if (stillCurrent()) error.value = signal.aborted ? '请求已取消；服务端可能已收到消息，原样重试不会重复保存。' : (failure.message || '发送失败，请重试')
    return false
  } finally { if (stillCurrent()) { busy.value = false; controller = null } }
}

function stagedImageNames() {
  if (store.activeConversation?.remote) return []
  return queue.items.filter(item => !item.stored && isImageFile(item.file)).map(item => item.file.name)
}
function clearStaged() { if (!busy.value) queue.clear() }

watch(() => [store.activeId, store.accountEpoch], reset, { flush: 'sync' })
onBeforeRouteLeave(() => confirmLeave())
onMounted(() => { store.setAttachmentLeaveGuard(confirmLeave); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => { disposed = true; reset(); store.setAttachmentLeaveGuard(null); window.removeEventListener('beforeunload', beforeUnload) })
defineExpose({ pick, paste, drop, submit, capture, count, busy, stagedImageNames, clearStaged })
</script>

<style scoped>
.attachment-input { display: none; }
.visual-actions { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 12px 0; }.visual-actions button { min-height: 32px; padding: 6px 10px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; }.visual-actions button:disabled { opacity: .5; cursor: not-allowed; }
.attachment-tray { display: grid; gap: 8px; padding: 12px 12px 0; max-height: 220px; overflow: auto; }
.attachment-draft { display: flex; gap: 10px; align-items: center; padding: 8px; border: 1px solid var(--smart-border-strong); border-radius: 8px; background: var(--smart-surface); color: var(--smart-text); }
.attachment-draft button, .attachment-cancel { border: 1px solid var(--smart-border-strong); border-radius: 6px; min-height: 32px; color: var(--smart-text); background: var(--smart-surface); cursor: pointer; }
.attachment-draft button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
.attachment-thumb { padding: 0; flex: 0 0 48px; overflow: hidden; }.attachment-thumb img { display: block; width: 48px; height: 48px; object-fit: cover; }
.attachment-description { display: grid; gap: 4px; flex: 1; min-width: 0; }.attachment-description strong { font-size: 12px; overflow-wrap: anywhere; }.attachment-description small { color: var(--smart-muted); font-size: 11px; }
.attachment-notice, .attachment-error { margin: 8px 12px; font-size: 11px; line-height: 1.6; color: var(--smart-muted); }.attachment-error, .attachment-description span { color: var(--smart-danger); }
.attachment-cancel { margin: 0 12px 10px; }.attachment-preview { display: block; max-width: 100%; max-height: 65vh; margin: auto; object-fit: contain; }
.attachment-recovery { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 12px 10px; }.attachment-recovery button { padding: 6px 8px; border: 1px solid var(--smart-border-strong); border-radius: 6px; background: var(--smart-surface); color: var(--smart-text); cursor: pointer; }
:global(.chat-attachment-dialog) { --el-dialog-bg-color: var(--smart-surface); --el-text-color-primary: var(--smart-text); --el-text-color-regular: var(--smart-text); color: var(--smart-text); }
</style>
