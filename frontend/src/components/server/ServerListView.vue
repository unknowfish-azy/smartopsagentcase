<template>
  <div>

    <div class="page-header">

      <div>
        <h1>服务器管理</h1>
        <p>管理接入智维Agent的服务器</p>
      </div>

      <el-button
          type="primary"
          @click="showCreateDialog = true"
      >
        添加服务器
      </el-button>

    </div>

    <el-card shadow="never">

      <el-table
          v-loading="serverStore.loading"
          :data="serverStore.list"
          stripe
      >

        <el-table-column
            prop="name"
            label="名称"
            min-width="160"
        />

        <el-table-column
            prop="host"
            label="主机地址"
            min-width="160"
        />

        <el-table-column
            prop="port"
            label="端口"
            width="100"
        />

        <el-table-column
            prop="os"
            label="操作系统"
            min-width="140"
        />

        <el-table-column
            label="状态"
            width="120"
        >
          <template #default="{ row }">
            <ServerStatusTag
                :status="row.status"
            />
          </template>
        </el-table-column>

        <el-table-column
            label="操作"
            width="140"
        >
          <template #default="{ row }">

            <el-button
                type="primary"
                link
                @click="openDetail(row.id)"
            >
              详情
            </el-button>

          </template>
        </el-table-column>

      </el-table>

      <AppEmpty
          v-if="
          !serverStore.loading &&
          serverStore.list.length === 0
        "
          text="暂无服务器"
      />

    </el-card>

  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useServerStore }
  from '../../stores/server'

import ServerStatusTag
  from '../../components/server/ServerStatusTag.vue'

import AppEmpty
  from '../../components/common/AppEmpty.vue'

const router = useRouter()
const serverStore = useServerStore()

const showCreateDialog = ref(false)

function openDetail(id) {
  router.push(`/servers/${id}`)
}

onMounted(() => {
  serverStore.fetchList()
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 6px;
}

.page-header p {
  margin: 0;
  color: var(--smart-muted);
}
</style>