<template>
  <div class="server-page">

    <!-- 页面标题 -->
    <div class="page-header">
      <div>
        <h1>服务器管理</h1>
        <p>管理接入智维Agent的云服务器与运维节点</p>
      </div>

      <el-button
          type="primary"
          size="large"
          :disabled="isDemo"
          @click="openCreateDialog"
      >
        <el-icon>
          <Plus />
        </el-icon>
        添加服务器
      </el-button>
    </div>


    <div class="server-source-switch" role="group" aria-label="服务器数据来源">
      <button type="button" :aria-pressed="!isDemo" @click="setSource('real')">真实服务器</button>
      <button type="button" :aria-pressed="isDemo" @click="setSource('demo')">演示案例（6 台）</button>
      <span>{{ isDemo ? '当前统计仅包含虚拟样例' : '当前统计仅包含真实服务器记录' }}</span>
    </div>
    <p v-if="isDemo" class="demo-banner" role="status">演示数据，非真实监控。不写入数据库，不参与真实统计，不提供连接、编辑或删除操作。</p>
    <p v-if="!isDemo && listError" class="list-error" role="alert">{{ listError }}；不会用演示数据替代真实结果，现有记录仅供参考。</p>

    <!-- 统计信息 -->
    <div class="stat-grid">

      <el-card shadow="never">
        <div class="stat-label">
          服务器总数
        </div>

        <div class="stat-value">
          {{ displayServers.length }}
        </div>
      </el-card>


      <el-card shadow="never">
        <div class="stat-label">
          在线
        </div>

        <div class="stat-value success">
          {{ onlineCount }}
        </div>
      </el-card>


      <el-card shadow="never">
        <div class="stat-label">
          告警
        </div>

        <div class="stat-value warning">
          {{ warningCount }}
        </div>
      </el-card>


      <el-card shadow="never">
        <div class="stat-label">
          离线/未知
        </div>

        <div class="stat-value danger">
          {{ offlineCount }}
        </div>
      </el-card>

    </div>


    <!-- 搜索区域 -->

    <el-card
        class="search-card"
        shadow="never"
    >

      <div class="search-row">

        <el-input
            v-model="keyword"
            placeholder="搜索服务器名称 / IP地址"
            clearable
            style="max-width: 360px"
            @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <Search />
            </el-icon>
          </template>
        </el-input>


        <el-select
            v-model="statusFilter"
            placeholder="服务器状态"
            aria-label="服务器状态筛选"
            clearable
            style="width: 160px"
        >
          <el-option
              label="在线"
              value="ONLINE"
          />

          <el-option
              label="告警"
              value="WARNING"
          />

          <el-option
              label="离线"
              value="OFFLINE"
          />

          <el-option
              label="未知"
              value="UNKNOWN"
          />
        </el-select>


        <el-button @click="handleSearch">
          查询
        </el-button>

        <el-button @click="resetSearch">
          重置
        </el-button>

      </div>

    </el-card>


    <!-- 服务器表格 -->
    <el-card
        class="table-card"
        shadow="never"
    >

      <template #header>

        <div class="table-header">
          <div>
            <span class="table-title">
              {{ isDemo ? '虚拟服务器演示列表' : '服务器列表' }}
            </span>

            <span class="table-count">
              共 {{ filteredServers.length }} 台
            </span>
          </div>

          <el-button
              link
              :loading="!isDemo && serverStore.loading"
              :disabled="isDemo"
              @click="refresh"
          >
            <el-icon>
              <Refresh />
            </el-icon>
            刷新
          </el-button>
        </div>

      </template>


      <el-table
          v-loading="!isDemo && serverStore.loading"
          :data="filteredServers"
          stripe
          border
          style="width: 100%"
          empty-text="暂无服务器"
      >

        <el-table-column
            prop="name"
            label="服务器名称"
            min-width="180"
            show-overflow-tooltip
        ><template #default="{ row }"><span>{{ row.name }}</span><span v-if="isDemoServer(row)" class="demo-row-label">演示</span></template></el-table-column>

        <el-table-column
            label="主机地址"
            min-width="180"
        >
          <template #default="{ row }">
            <span class="host">
              {{ row.host }}
            </span>
          </template>
        </el-table-column>


        <el-table-column
            prop="port"
            label="SSH端口"
            width="110"
        />


        <el-table-column
            prop="os"
            label="操作系统"
            min-width="150"
            show-overflow-tooltip
        />


        <el-table-column
            label="状态"
            width="120"
        >
          <template #default="{ row }">

            <small v-if="isDemoServer(row)" class="demo-row-label">模拟</small><ServerStatusTag
                :status="row.status"
            />

          </template>
        </el-table-column>


        <el-table-column
            prop="description"
            label="说明"
            min-width="220"
            show-overflow-tooltip
        />


        <el-table-column
            label="创建时间"
            width="180"
        >
          <template #default="{ row }">
            {{ isDemoServer(row) ? '固定演示样例' : formatDate(row.createdAt) }}
          </template>
        </el-table-column>


        <el-table-column
            label="操作"
            fixed="right"
            width="230"
        >

          <template #default="{ row }">

            <el-button
                type="primary"
                link
                @click="openDetail(row.id)"
            >
              {{ isDemoServer(row) ? '演示详情' : '详情' }}
            </el-button>


            <el-button
                v-if="!isDemoServer(row)"
                type="primary"
                link
                @click="openEditDialog(row)"
            >
              编辑
            </el-button>


            <el-popconfirm
                v-if="!isDemoServer(row)"
                title="确定删除这台服务器吗？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="handleDelete(row)"
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


      <!-- 没有数据 -->
      <AppEmpty
          v-if="
          (isDemo || !serverStore.loading) &&
          filteredServers.length === 0
        "
          text="暂无符合条件的服务器"
      />

    </el-card>


    <ServerDemoDetails :server="selectedDemo" @close="selectedDemo = null" />

    <!-- 添加/编辑服务器 -->
    <el-dialog
        v-model="dialogVisible"
        :title="isEdit ? '编辑服务器' : '添加服务器'"
        width="560px"
        destroy-on-close
    >

      <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="100px"
      >

        <el-form-item
            label="服务器名称"
            prop="name"
        >
          <el-input
              v-model="form.name"
              placeholder="例如：Server-01"
          />
        </el-form-item>


        <el-form-item
            label="主机地址"
            prop="host"
        >
          <el-input
              v-model="form.host"
              placeholder="例如：192.168.1.100"
          />
        </el-form-item>


        <el-form-item
            label="SSH端口"
            prop="port"
        >
          <el-input-number
              v-model="form.port"
              :min="1"
              :max="65535"
              controls-position="right"
              style="width: 100%"
          />
        </el-form-item>


        <el-form-item
            label="操作系统"
            prop="os"
        >
          <el-select
              v-model="form.os"
              placeholder="选择操作系统"
              style="width: 100%"
          >
            <el-option
                label="Ubuntu 24.04"
                value="Ubuntu 24.04"
            />

            <el-option
                label="Ubuntu 22.04"
                value="Ubuntu 22.04"
            />

            <el-option
                label="CentOS 7"
                value="CentOS 7"
            />

            <el-option
                label="Rocky Linux 9"
                value="Rocky Linux 9"
            />

            <el-option
                label="Windows Server"
                value="Windows Server"
            />

            <el-option
                label="其他"
                value="Other"
            />
          </el-select>
        </el-form-item>


        <el-form-item
            label="说明"
            prop="description"
        >
          <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              placeholder="填写服务器用途、环境等信息"
          />
        </el-form-item>

      </el-form>


      <template #footer>

        <el-button
            @click="dialogVisible = false"
        >
          取消
        </el-button>

        <el-button
            type="primary"
            :loading="submitLoading"
            @click="submitForm"
        >
          {{ isEdit ? '保存修改' : '创建服务器' }}
        </el-button>

      </template>

    </el-dialog>

  </div>
</template>


<script setup>

import {
  computed,
  onMounted,
  reactive,
  ref,
  watch
} from 'vue'

import {
  useRouter,
  useRoute
} from 'vue-router'

import { ElMessage } from 'element-plus/es/components/message/index.mjs'

import {
  Plus,
  Search,
  Refresh
} from '@element-plus/icons-vue'

import {
  getServers,
  createServer,
  updateServer,
  deleteServer
} from '../../api/server'

import {
  useServerStore
} from '../../stores/server'

import ServerStatusTag
  from '../../components/server/ServerStatusTag.vue'

import AppEmpty
  from '../../components/common/AppEmpty.vue'
import ServerDemoDetails from '../../components/server/ServerDemoDetails.vue'
import { isDemoServer, findDemoServer, serverRowsForMode } from './serverDemo.js'


const router = useRouter()
const route = useRoute()
const isDemo = computed(() => route.query.view === 'demo')
const selectedDemo = ref(null)
const listError = ref('')

const serverStore =
    useServerStore()

const displayServers = computed(() => serverRowsForMode(isDemo.value ? 'demo' : 'real', serverStore.list))
function setSource(source) { router.replace({ query: { ...route.query, view: source === 'demo' ? 'demo' : undefined } }) }


/* ============================
   搜索
   ============================ */

const keyword = ref('')

const statusFilter = ref('')


const handleSearch = () => {
  // 使用computed自动过滤
}


const resetSearch = () => {
  keyword.value = ''
  statusFilter.value = ''
}


/* ============================
   统计
   ============================ */

const onlineCount = computed(() =>
    displayServers.value.filter(
        item => item.status === 'ONLINE'
    ).length
)


const warningCount = computed(() =>
    displayServers.value.filter(
        item => item.status === 'WARNING'
    ).length
)


const offlineCount = computed(() =>
    displayServers.value.filter(
        item =>
            item.status === 'OFFLINE' ||
            item.status === 'UNKNOWN'
    ).length
)


/* ============================
   过滤
   ============================ */

const filteredServers = computed(() => {

  const search =
      keyword.value
          .trim()
          .toLowerCase()

  return displayServers.value.filter(
      server => {

        const matchKeyword =
            !search ||
            server.name
                ?.toLowerCase()
                .includes(search) ||
            server.host
                ?.toLowerCase()
                .includes(search)

        const matchStatus =
            !statusFilter.value ||
            server.status === statusFilter.value

        return (
            matchKeyword &&
            matchStatus
        )
      }
  )
})


/* ============================
   表单
   ============================ */

const dialogVisible = ref(false)

const isEdit = ref(false)

const submitLoading = ref(false)

const formRef = ref(null)


const createEmptyForm = () => ({
  id: null,
  name: '',
  host: '',
  port: 22,
  os: '',
  description: ''
})


const form = reactive(
    createEmptyForm()
)


const rules = {

  name: [
    {
      required: true,
      message: '请输入服务器名称',
      trigger: 'blur'
    }
  ],

  host: [
    {
      required: true,
      message: '请输入主机地址',
      trigger: 'blur'
    }
  ],

  port: [
    {
      required: true,
      message: '请输入SSH端口',
      trigger: 'change'
    }
  ]

}


/* ============================
   打开新增
   ============================ */

function openCreateDialog() {
  if (isDemo.value) return

  Object.assign(
      form,
      createEmptyForm()
  )

  isEdit.value = false

  dialogVisible.value = true
}


/* ============================
   打开编辑
   ============================ */

function openEditDialog(row) {
  if (isDemo.value || isDemoServer(row)) return

  Object.assign(
      form,
      {
        id: row.id,
        name: row.name || '',
        host: row.host || '',
        port: row.port || 22,
        os: row.os || '',
        description: row.description || ''
      }
  )

  isEdit.value = true

  dialogVisible.value = true
}


/* ============================
   提交
   ============================ */

async function submitForm() {
  if (isDemo.value || isDemoServer(form)) return

  if (!formRef.value) {
    return
  }

  const valid =
      await formRef.value.validate()

  if (!valid) {
    return
  }

  submitLoading.value = true

  try {

    const payload = {
      name: form.name,
      host: form.host,
      port: form.port,
      os: form.os,
      description: form.description
    }

    if (isEdit.value) {

      await updateServer(
          form.id,
          payload
      )

      ElMessage.success(
          '服务器修改成功'
      )

    } else {

      await createServer(
          payload
      )

      ElMessage.success(
          '服务器创建成功'
      )
    }

    dialogVisible.value = false

    await refresh()

  } catch (error) {

    ElMessage.error(
        error.message ||
        '操作失败'
    )

  } finally {

    submitLoading.value = false
  }
}


/* ============================
   删除
   ============================ */

async function handleDelete(row) {
  if (isDemo.value || isDemoServer(row)) return

  try {

    await deleteServer(
        row.id
    )

    ElMessage.success(
        '服务器已删除'
    )

    await refresh()

  } catch (error) {

    ElMessage.error(
        error.message ||
        '删除失败'
    )
  }
}


/* ============================
   跳转详情
   ============================ */

function openDetail(id) {
  if (isDemoServer({ id })) {
    selectedDemo.value = findDemoServer(id)
    return
  }

  router.push(
      `/servers/${id}`
  )
}


/* ============================
   加载
   ============================ */

async function refresh() {
  if (isDemo.value) return
  listError.value = ''

  try {

    await serverStore.fetchList()

  } catch (error) {

    ElMessage.error(
        error.message ||
        '服务器列表加载失败'
    )
    listError.value = '真实服务器列表加载失败，请检查连接并重试'
  }
}


/* ============================
   日期
   ============================ */

function formatDate(value) {

  if (!value) {
    return '-'
  }

  return new Date(value)
      .toLocaleString('zh-CN')
}


onMounted(() => {
  refresh()
})
watch(isDemo, demo => {
  resetSearch()
  selectedDemo.value = null
  dialogVisible.value = false
  if (!demo) refresh()
})

</script>


<style scoped>
.server-source-switch{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 16px}.server-source-switch button{min-height:44px;padding:9px 14px;border:1px solid var(--smart-border-strong);border-radius:6px;background:var(--smart-surface);color:var(--smart-text)}.server-source-switch button[aria-pressed=true]{border-color:var(--smart-primary-strong);background:var(--smart-primary-soft);color:var(--smart-primary-strong)}.server-source-switch span{color:var(--smart-muted);font-size:13px}.demo-banner,.list-error{padding:14px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);line-height:1.7}.demo-row-label{display:inline-block;margin:0 6px;padding:1px 5px;border:1px solid var(--smart-border);color:var(--smart-primary-strong);font-size:11px;white-space:nowrap}

.server-page {
  width: 100%;
}


.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
}

.page-header p {
  margin: 0;
  color: var(--smart-muted);
}

.stat-grid {
  display: grid;
  grid-template-columns:
    repeat(4, minmax(0, 1fr));

  gap: 16px;

  margin-bottom: 20px;
}

.stat-label {
  color: var(--smart-muted);
  font-size: 14px;
}

.stat-value {
  margin-top: 8px;
  font-size: 30px;
  font-weight: 700;
}

.success {
  color: var(--smart-success);
}

.warning {
  color: var(--smart-warning);
}

.danger {
  color: var(--smart-danger);
}

.search-card {
  margin-bottom: 20px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.table-card {
  margin-bottom: 20px;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
}

.table-count {
  margin-left: 10px;
  color: var(--smart-muted);
  font-size: 13px;
}

.host {
  font-family:
      "Consolas",
      "Courier New",
      monospace;
}

@media (max-width: 1000px) {

  .stat-grid {
    grid-template-columns:
      repeat(2, 1fr);
  }

  .search-row {
    flex-wrap: wrap;
  }
}

@media (max-width: 650px) {

  .page-header {
    align-items: flex-start;
    gap: 15px;
    flex-direction: column;
  }

  .stat-grid {
    grid-template-columns: 1fr;
  }

}

</style>
