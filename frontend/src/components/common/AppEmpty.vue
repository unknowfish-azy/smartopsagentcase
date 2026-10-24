<template>
  <div class="empty">
    <KubernetesSpider class="icon" state="observing" :size="36" />
    <div class="text">{{ content }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import KubernetesSpider from './KubernetesSpider.vue'

const props = defineProps({ text: { type: String, default: '暂无数据' }, description: { type: String, default: '' } })
const content = computed(() => props.description || props.text)
</script>

<style scoped>
.empty { padding: 40px; text-align: center; color: var(--smart-muted); }
.icon { display: block; margin: 0 auto 10px; }
.text { font-size: 14px; }
</style>
