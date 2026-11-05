<template>
  <dialog ref="dialog" class="admin-dialog" :aria-labelledby="titleId" :aria-busy="busy" @cancel.prevent="close">
    <header class="admin-page-header"><h2 :id="titleId">{{ title }}</h2><button type="button" :disabled="busy" aria-label="关闭对话框" @click="close">关闭</button></header>
    <slot />
  </dialog>
</template>

<script>
// 同一页面可能同时存在多个对话框，标题 id 必须唯一，避免 aria-labelledby 指错。
let dialogSeq = 0
</script>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
const props = defineProps({ title: String, busy: Boolean })
const emit = defineEmits(['close'])
const dialog = ref(null)
const titleId = `admin-dialog-title-${++dialogSeq}`
// 打开时记住触发按钮，关闭后归还焦点；打开后把焦点放在第一个可编辑字段，
// 而不是对话框头部的“关闭”按钮，避免输入复核密码前还要多按一次 Tab。
let opener = null
function close() { if (!props.busy) emit('close') }
onMounted(async () => {
  opener = document.activeElement
  dialog.value.showModal()
  await nextTick()
  const field = dialog.value.querySelector('input:not([disabled]), select:not([disabled]), textarea:not([disabled])')
  field?.focus()
})
onUnmounted(() => { if (opener?.isConnected) opener.focus() })
</script>
