<template>
  <div v-if="message" class="admin-error admin-error-state" role="alert">
    <p>{{ message }}</p>
    <button v-if="retryable" type="button" :disabled="busy" @click="$emit('retry')">{{ busy ? '重试中…' : '重试' }}</button>
  </div>
</template>

<script setup>
defineProps({
  message: { type: String, default: '' },
  busy: Boolean,
  retryable: { type: Boolean, default: true }
})
defineEmits(['retry'])
</script>

<style scoped>
.admin-error-state { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 16px; }
.admin-error-state p { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.admin-error-state button { flex: 0 0 auto; }
</style>
