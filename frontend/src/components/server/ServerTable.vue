<template>
  <div class="server-table">

    <!-- 表格顶部 -->
    <div class="table-toolbar">

      <div class="toolbar-left">

        <span class="table-title">
          服务器列表
        </span>

        <span class="table-count">
          共 {{ data.length }} 台
        </span>

      </div>


      <div class="toolbar-right">

        <el-button
            link
            :loading="loading"
            @click="$emit('refresh')"
        >
          <el-icon>
            <Refresh />
          </el-icon>

          刷新
        </el-button>

      </div>

    </div>


    <!-- 数据表格 -->
    <el-table
        v-loading="loading"
        :data="data"
        stripe
        border
        style="width: 100%"
        empty-text="暂无服务器"
        row-key="id"
    >

      <!-- 服务器名称 -->
      <el-table-column
          prop="name"
          label="服务器名称"
          min-width="180"
          show-overflow-tooltip
      />

      <!-- IP/主机 -->
      <el-table-column
          label="主机地址"
          min-width="180"
          show-overflow-tooltip
      >

        <template #default="{ row }">

          <span class="host-value">
            {{ row.host || '-' }}
          </span>

        </template>

      </el-table-column>


      <!-- SSH端口 -->
      <el-table-column
          prop="port"
          label="SSH端口"
          width="100"
          align="center"
      />


      <!-- 操作系统 -->
      <el-table-column
          prop="os"
          label="操作系统"
          min-width="150"
          show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.os || '-' }}
        </template>
      </el-table-column>


      <!-- 状态 -->
      <el-table-column
          label="状态"
          width="120"
          align="center"
      >

        <template #default="{ row }">

          <ServerStatusTag
              :status="row.status"
          />

        </template>

      </el-table-column>


      <!-- 描述 -->
      <el-table-column
          label="说明"
          min-width="220"
          show-overflow-tooltip
      >

        <template #default="{ row }">

          {{ row.description || '-' }}

        </template>

      </el-table-column>


      <!-- 创建时间 -->
      <el-table-column
          label="创建时间"
          width="180"
      >

        <template #default="{ row }">

          {{ formatDate(row.createdAt) }}

        </template>

      </el-table-column>


      <!-- 更新时间 -->
      <el-table-column
          label="更新时间"
          width="180"
      >

        <template #default="{ row }">

          {{ formatDate(row.updatedAt) }}

        </template>

      </el-table-column>


      <!-- 操作 -->
      <el-table-column
          label="操作"
          fixed="right"
          width="230"
          align="center"
      >

        <template #default="{ row }">

          <el-button
              type="primary"
              link
              @click="$emit('detail', row)"
          >
            详情
          </el-button>


          <el-button
              type="primary"
              link
              @click="$emit('edit', row)"
          >
            编辑
          </el-button>


          <el-popconfirm
              title="确定删除这台服务器吗？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              width="220"
              @confirm="$emit('delete', row)"
          >

            <template #reference>

              <el-button
                  type="danger"
                  link
              >
                删除
              </el-button>

            </template>

          </el-popconfirm>

        </template>

      </el-table-column>

    </el-table>


    <!-- 空状态 -->
    <div
        v-if="!loading && data.length === 0"
        class="empty-wrapper"
    >

      <div class="empty-icon">
        🖥️
      </div>

      <div class="empty-title">
        暂无服务器
      </div>

      <div class="empty-description">
        当前还没有接入任何服务器
      </div>

      <el-button
          type="primary"
          @click="$emit('create')"
      >
        添加第一台服务器
      </el-button>

    </div>

  </div>
</template>


<script setup>

import {
  Refresh
} from '@element-plus/icons-vue'

import ServerStatusTag
  from './ServerStatusTag.vue'


/**
 * =========================================================
 * Props
 * =========================================================
 */

defineProps({

  /**
   * 服务器数据
   */
  data: {
    type: Array,
    default: () => []
  },


  /**
   * 加载状态
   */
  loading: {
    type: Boolean,
    default: false
  }

})


/**
 * =========================================================
 * Events
 * =========================================================
 *
 * detail
 * edit
 * delete
 * create
 * refresh
 */

defineEmits([
  'detail',
  'edit',
  'delete',
  'create',
  'refresh'
])


/**
 * =========================================================
 * 日期格式化
 * =========================================================
 */

function formatDate(value) {

  if (!value) {
    return '-'
  }

  const date =
      new Date(value)

  if (
      Number.isNaN(
          date.getTime()
      )
  ) {
    return '-'
  }

  return date.toLocaleString(
      'zh-CN',
      {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }
  )
}

</script>


<style scoped>

.server-table {
  width: 100%;
}


/* =========================================================
   Toolbar
   ========================================================= */

.table-toolbar {
  display: flex;

  align-items: center;

  justify-content: space-between;

  margin-bottom: 14px;
}


.toolbar-left {
  display: flex;

  align-items: center;

  gap: 10px;
}


.table-title {
  font-size: 16px;

  font-weight: 600;
}


.table-count {
  color: var(--smart-muted);

  font-size: 13px;
}


.toolbar-right {
  display: flex;

  align-items: center;
}


/* =========================================================
   Host
   ========================================================= */

.host-value {
  font-family:
      "Consolas",
      "Courier New",
      monospace;

  font-size: 13px;
}


/* =========================================================
   Empty
   ========================================================= */

.empty-wrapper {
  display: flex;

  flex-direction: column;

  align-items: center;

  justify-content: center;

  min-height: 260px;

  padding: 40px 20px;

  text-align: center;

  border: 1px dashed
  var(--smart-border);

  border-top: none;
}


.empty-icon {
  margin-bottom: 12px;

  font-size: 42px;
}


.empty-title {
  margin-bottom: 8px;

  font-size: 16px;

  font-weight: 600;
}


.empty-description {
  margin-bottom: 18px;

  color: var(--smart-muted);

  font-size: 14px;
}


/* =========================================================
   Responsive
   ========================================================= */

@media (max-width: 900px) {

  .table-toolbar {
    align-items: flex-start;

    flex-direction: column;

    gap: 10px;
  }

}

</style>