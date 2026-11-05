<template>
  <form class="admin-filters" role="search" @submit.prevent="$emit('search')">
    <slot />
    <button type="submit" :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    <button v-if="resettable" type="button" :disabled="loading" @click="$emit('reset')">重置</button>
  </form>
</template>

<script setup>
defineProps({
  loading: Boolean,
  resettable: { type: Boolean, default: true }
})
defineEmits(['search', 'reset'])
</script>
