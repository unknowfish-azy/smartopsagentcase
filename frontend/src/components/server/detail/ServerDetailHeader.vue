<template>
  <div class="page-header">
    <div class="header-left">
      <el-button circle @click="emit('back')">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <div>
        <h1>{{ server?.name || '服务器详情' }}</h1>
        <p>{{ server?.host || '-' }} : {{ server?.port || '-' }}</p>
      </div>
    </div>
    <div class="header-right">
      <el-button :loading="loading" @click="emit('refresh')">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <ServerStatusTag v-if="server" :status="server.status" />
    </div>
  </div>
</template>

<script setup>
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import ServerStatusTag from '../ServerStatusTag.vue'

defineProps({
  server: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['back', 'refresh'])
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.header-left h1 {
  margin: 0 0 6px;
  font-size: 26px;
}

.header-left p {
  margin: 0;
  color: var(--smart-muted);
  font-family: "Consolas", "Courier New", monospace;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

@media (max-width: 700px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .header-right {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
