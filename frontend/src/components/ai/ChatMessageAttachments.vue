<template>
  <div v-if="attachments?.length || visionEvents?.length" class="message-attachments">
    <VisionEventCard v-for="event in visionEvents" :key="event.id" :event="event" />
    <button v-for="attachment in attachments" :key="attachment.id" type="button" :disabled="loading" @click="open(attachment)">{{ attachment.mediaType.startsWith('image/') ? '预览图片' : '下载文件' }} · {{ attachment.name }}</button>
    <p v-if="error" role="alert">{{ error }}</p>
    <el-dialog v-model="visible" :title="selected?.name || '附件预览'" append-to-body width="min(800px, 94vw)" class="chat-attachment-dialog" @closed="release">
      <img v-if="previewUrl" :src="previewUrl" :alt="selected?.name" />
      <button v-if="previewUrl" type="button" @click="save(previewUrl, selected.name)">下载此图片</button>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { chatAttachmentsApi } from '../../api/chatAttachments.ts'
import VisionEventCard from './VisionEventCard.vue'
const props = defineProps({ conversationId: String, attachments: Array, visionEvents: Array })
const previewUrl = ref(''), visible = ref(false), selected = ref(null), error = ref(''), loading = ref(false)
const controller = new AbortController()
let disposed = false
function release() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function save(url, name) { const link = document.createElement('a'); link.href = url; link.download = name; link.click() }
async function open(attachment) {
  loading.value = true; error.value = ''
  try {
    const blob = await chatAttachmentsApi.content(props.conversationId, attachment.id, controller.signal)
    if (disposed) return
    release()
    const url = URL.createObjectURL(blob)
    if (attachment.mediaType.startsWith('image/')) { previewUrl.value = url; selected.value = attachment; visible.value = true }
    else { save(url, attachment.name); setTimeout(() => URL.revokeObjectURL(url), 1000) }
  } catch (failure) { if (!disposed) error.value = failure.message || '附件读取失败' }
  finally { if (!disposed) loading.value = false }
}
onBeforeUnmount(() => { disposed = true; controller.abort(); release() })
</script>

<style scoped>
.message-attachments { display: grid; gap: 7px; margin-top: 10px; }.message-attachments button { text-align: left; overflow-wrap: anywhere; min-height: 34px; padding: 6px 9px; border: 1px solid var(--smart-border-strong); border-radius: 6px; color: var(--smart-text); background: var(--smart-surface); cursor: pointer; }.message-attachments p { color: var(--smart-danger); font-size: 12px; }.message-attachments button:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 2px; }
:global(.chat-attachment-dialog img) { display: block; max-width: 100%; max-height: 65vh; margin: auto; object-fit: contain; }
</style>
