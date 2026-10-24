<template>
  <nav class="admin-pagination" aria-label="列表分页">
    <span>共 {{ total }} 条 · 第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</span>
    <label>每页<select aria-label="每页条数" :value="pageSize" :disabled="loading" @change="$emit('resize', Number($event.target.value))"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
    <button type="button" :disabled="loading || page <= 1" @click="$emit('page', page - 1)">上一页</button>
    <button type="button" :disabled="loading || page * pageSize >= total" @click="$emit('page', page + 1)">下一页</button>
  </nav>
</template>
<script setup>
defineProps({ total: { type: Number, default: 0 }, page: { type: Number, default: 1 }, pageSize: { type: Number, default: 20 }, loading: Boolean })
defineEmits(['page', 'resize'])
</script>
