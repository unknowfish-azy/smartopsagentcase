<template>
  <el-card class="info-card" shadow="never">
    <template #header>
      <div class="card-title">基本信息</div>
    </template>
    <el-descriptions :column="3" border>
      <el-descriptions-item label="服务器名称">
        {{ server?.name || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="主机地址">
        {{ server?.host || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="SSH端口">
        {{ server?.port || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="操作系统">
        {{ server?.os || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="服务器状态">
        <ServerStatusTag v-if="server" :status="server.status" />
        <span v-else>-</span>
      </el-descriptions-item>
      <el-descriptions-item label="创建时间">
        {{ formatDate(server?.createdAt) }}
      </el-descriptions-item>
      <el-descriptions-item label="更新时间">
        {{ formatDate(server?.updatedAt) }}
      </el-descriptions-item>
      <el-descriptions-item label="说明" :span="2">
        {{ server?.description || '-' }}
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup>
import ServerStatusTag from '../ServerStatusTag.vue'
import { formatDate } from './serverMetricFormat.js'

defineProps({
  server: {
    type: Object,
    default: null
  }
})
</script>

<style scoped>
.info-card {
  margin-bottom: 28px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}
</style>
