<template>
  <dialog ref="dialog" class="admin-dialog" aria-labelledby="admin-dialog-title" :aria-busy="busy" @cancel.prevent="close">
    <header class="admin-page-header"><h2 id="admin-dialog-title">{{ title }}</h2><button type="button" :disabled="busy" aria-label="关闭对话框" @click="close">关闭</button></header>
    <slot />
  </dialog>
</template>

<script setup>
import { onMounted, ref } from 'vue'
const props = defineProps({ title: String, busy: Boolean })
const emit = defineEmits(['close'])
const dialog = ref(null)
function close() { if (!props.busy) emit('close') }
onMounted(() => dialog.value.showModal())
</script>
