<template>
  <AdminDialog v-if="open" :title="title" :busy="busy" @close="cancel">
    <form class="admin-form" @submit.prevent="submit">
      <p v-if="description" class="admin-muted">{{ description }}</p>
      <label>管理员复核密码<input ref="passwordInput" v-model="password" type="password" autocomplete="off" :disabled="busy"></label>
      <small>输入你当前登录的管理员密码，仅用于本次身份复核。</small>
      <p v-if="error" class="admin-error" role="alert">{{ error }}</p>
      <footer>
        <button type="button" :disabled="busy" @click="cancel">取消</button>
        <button class="admin-primary" type="submit" :disabled="busy || !password">{{ busy ? '验证中…' : '确认' }}</button>
      </footer>
    </form>
  </AdminDialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import AdminDialog from './AdminDialog.vue'
const props = defineProps({ open: Boolean, title: String, description: String, busy: Boolean, error: String })
const emit = defineEmits(['confirm', 'cancel'])
const password = ref('')
const passwordInput = ref(null)
watch(() => props.open, async open => {
  password.value = ''
  if (open) { await nextTick(); passwordInput.value?.focus() }
}, { immediate: true })
function submit() { if (props.busy || !password.value) return; emit('confirm', password.value) }
function cancel() { if (props.busy) return; password.value = ''; emit('cancel') }
</script>
