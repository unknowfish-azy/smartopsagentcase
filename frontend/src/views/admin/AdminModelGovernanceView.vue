<template>
  <section aria-labelledby="model-governance-title">
    <header class="admin-page-header">
      <div>
        <p class="admin-eyebrow">AGENT GOVERNANCE / MODEL GATEWAY</p>
        <h1 id="model-governance-title">模型治理</h1>
        <p class="admin-muted">平台级只读清单：个人 owner 隔离保持不变，这里只汇总路由、用量、额度与错误元数据，不显示密钥哈希、明文或完整连接串。</p>
      </div>
      <button type="button" :disabled="loading || refreshing" @click="load({ preserve: true })">{{ refreshing ? '刷新中…' : '刷新' }}</button>
    </header>
    <p v-if="refreshing" class="admin-muted admin-refresh-hint" role="status">正在刷新模型治理清单…</p>
    <p v-else-if="updatedAt && data" class="admin-muted admin-refresh-hint">最近更新：{{ formatAdminTime(updatedAt) }} · 服务端生成：{{ formatAdminTime(data.generatedAt) }} · 统计窗口：近 {{ data.windowHours }} 小时（{{ data.timezone }}）</p>
    <AdminErrorState :message="error" :busy="loading || refreshing" @retry="load()" />
    <p v-if="loading" role="status">正在加载模型治理清单…</p>

    <template v-if="data">
      <section class="model-summary" aria-labelledby="model-summary-title">
        <h2 id="model-summary-title" class="admin-section-title">近 {{ data.windowHours }} 小时调用计量</h2>
        <div class="admin-stats">
          <dl class="admin-stat"><dt>调用总数</dt><dd>{{ summary.calls ?? 0 }}</dd></dl>
          <dl class="admin-stat"><dt>成功率</dt><dd>{{ summary.successRate == null ? '暂无结果数据' : summary.successRate.toFixed(1) + '%' }}</dd></dl>
          <dl class="admin-stat"><dt>失败调用</dt><dd>{{ summary.failures ?? 0 }}</dd></dl>
          <dl class="admin-stat"><dt>未知用量</dt><dd>{{ summary.unknownUsageCalls ?? 0 }}</dd></dl>
          <dl class="admin-stat"><dt>已记录 token</dt><dd>{{ summary.knownTokens == null ? '暂无记录' : summary.knownTokens }}</dd></dl>
          <dl class="admin-stat"><dt>无归属 key 调用</dt><dd>{{ unattributed.calls ?? 0 }}</dd></dl>
        </div>
        <p class="admin-muted">未知用量指成功调用但未记录 token 的部分，单独计数、不并入已记录 token；不显示金额，因为缺少币种、单价版本与计量依据。</p>
      </section>

      <AdminFilterBar :loading="loading || refreshing" :resettable="Boolean(keyword)" @search="noop" @reset="keyword = ''">
        <label>筛选账号或模型组<input v-model.trim="keyword" type="search" maxlength="80" placeholder="按账号或组名子串筛选"></label>
      </AdminFilterBar>
      <p class="admin-muted">筛选只作用于当前已加载清单，不是服务端全量检索。</p>

      <section class="model-section" aria-labelledby="model-owners-title">
        <h2 id="model-owners-title" class="admin-section-title">拥有者用量</h2>
        <div class="admin-table-wrap" tabindex="0" aria-label="模型拥有者用量列表">
          <table>
            <thead><tr><th scope="col">账号</th><th scope="col">调用</th><th scope="col">成功</th><th scope="col">失败</th><th scope="col">待完成</th><th scope="col">已记录 token</th><th scope="col">最近调用</th></tr></thead>
            <tbody>
              <tr v-for="owner in owners" :key="owner.ownerUserId">
                <td>{{ owner.username || '未知账号' }}<span class="admin-muted"> · ID {{ owner.ownerUserId }}</span></td>
                <td>{{ owner.calls }}</td><td>{{ owner.successes }}</td><td>{{ owner.failures }}</td><td>{{ owner.pendingCalls }}</td>
                <td>{{ owner.knownTokens == null ? '暂无记录' : owner.knownTokens }}</td>
                <td>{{ formatAdminTime(owner.lastCallAt) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!owners.length" class="admin-empty">当前窗口内没有可归属到个人 key 的调用。</p>
        </div>
      </section>

      <section class="model-section" aria-labelledby="model-groups-title">
        <h2 id="model-groups-title" class="admin-section-title">模型组与额度</h2>
        <div class="admin-table-wrap" tabindex="0" aria-label="模型组列表">
          <table>
            <thead><tr><th scope="col">模型组</th><th scope="col">拥有者</th><th scope="col">状态</th><th scope="col">请求额度 / 24h</th><th scope="col">token 额度 / 24h</th><th scope="col">实际调用</th><th scope="col">路由健康</th></tr></thead>
            <tbody>
              <tr v-for="group in groups" :key="group.slug">
                <td>{{ group.slug }}<span class="admin-muted"> · {{ group.name }}</span></td>
                <td>{{ group.username || '未知账号' }}<span class="admin-muted"> · ID {{ group.ownerUserId ?? '—' }}</span></td>
                <td><span class="admin-status" :class="group.enabled ? 'admin-status--success' : 'admin-status--muted'">{{ group.enabled ? '启用' : '停用' }}</span></td>
                <td>{{ quotaText(group.requestLimit24h) }}</td>
                <td>{{ quotaText(group.tokenLimit24h) }}</td>
                <td>{{ group.calls24h }}<span class="admin-muted"> · token {{ group.knownTokens24h == null ? '暂无' : group.knownTokens24h }}</span></td>
                <td>{{ group.healthyRouteCount }} / {{ group.routeCount }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!groups.length" class="admin-empty">尚未配置任何模型组。</p>
        </div>
      </section>

      <section class="model-section" aria-labelledby="model-routes-title">
        <h2 id="model-routes-title" class="admin-section-title">路由健康</h2>
        <div class="admin-table-wrap" tabindex="0" aria-label="模型路由列表">
          <table>
            <thead><tr><th scope="col">模型组</th><th scope="col">路由</th><th scope="col">连接</th><th scope="col">优先级 / 权重</th><th scope="col">状态</th><th scope="col">失败次数</th><th scope="col">最近错误</th><th scope="col">最近检查</th></tr></thead>
            <tbody>
              <tr v-for="route in routes" :key="route.id">
                <td>{{ route.groupSlug }}</td><td>#{{ route.id }}</td><td>{{ route.connectionId }}</td>
                <td>{{ route.priority }} / {{ route.weight }}</td>
                <td><span class="admin-status" :class="route.enabled ? (route.healthy ? 'admin-status--success' : 'admin-status--warning') : 'admin-status--muted'">{{ route.enabled ? (route.healthy ? '可用' : '隔离中') : '停用' }}</span></td>
                <td>{{ route.failureCount }}</td><td>{{ route.lastErrorCode || '—' }}</td><td>{{ formatAdminTime(route.lastCheckedAt) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!routes.length" class="admin-empty">尚未配置任何路由。</p>
        </div>
      </section>

      <section class="model-section" aria-labelledby="model-keys-title">
        <h2 id="model-keys-title" class="admin-section-title">密钥清单（脱敏）</h2>
        <div class="admin-table-wrap" tabindex="0" aria-label="模型密钥脱敏列表">
          <table>
            <thead><tr><th scope="col">名称</th><th scope="col">拥有者</th><th scope="col">前缀</th><th scope="col">范围</th><th scope="col">请求额度</th><th scope="col">token 额度</th><th scope="col">过期</th><th scope="col">状态</th></tr></thead>
            <tbody>
              <tr v-for="key in keys" :key="key.id">
                <td>{{ key.name }}</td>
                <td>{{ key.username || '未知账号' }}<span class="admin-muted"> · ID {{ key.ownerUserId }}</span></td>
                <td><code>{{ key.prefix }}…</code></td>
                <td>{{ key.scope }}</td>
                <td>{{ quotaText(key.requestLimit24h) }}</td>
                <td>{{ quotaText(key.tokenLimit24h) }}</td>
                <td>{{ key.expiresAt ? formatAdminTime(key.expiresAt) : '不限期' }}</td>
                <td><span class="admin-status" :class="key.revoked ? 'admin-status--muted' : 'admin-status--success'">{{ key.revoked ? '已撤销' : '有效' }}</span></td>
              </tr>
            </tbody>
          </table>
          <p v-if="!keys.length" class="admin-empty">尚未签发任何网关密钥。</p>
        </div>
        <p class="admin-notice">本页只读，不提供额度调整、路由发布或密钥签发；这些写操作仍由个人 owner 页面与既有管理接口执行，并记录审计。</p>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { adminApi } from '../../api/admin.ts'
import AdminErrorState from '../../components/admin/AdminErrorState.vue'
import AdminFilterBar from '../../components/admin/AdminFilterBar.vue'
import { useAdminResource, formatAdminTime } from '../../composables/useAdminResource.js'

const { data, loading, refreshing, error, updatedAt, load } = useAdminResource(() => adminApi.modelGovernance())
const keyword = ref('')
const matches = value => {
  const text = keyword.value.trim().toLowerCase()
  return !text || String(value || '').toLowerCase().includes(text)
}
const summary = computed(() => data.value?.summary || {})
const unattributed = computed(() => data.value?.unattributed || {})
const owners = computed(() => (data.value?.owners || []).filter(owner => matches(owner.username) || matches(owner.ownerUserId)))
const groups = computed(() => (data.value?.groups || []).filter(group => matches(group.slug) || matches(group.name) || matches(group.username)))
const routes = computed(() => {
  const visible = new Set(groups.value.map(group => group.slug))
  const list = data.value?.routes || []
  return keyword.value.trim() ? list.filter(route => visible.has(route.groupSlug)) : list
})
const keys = computed(() => (data.value?.keys || []).filter(key => matches(key.name) || matches(key.username) || matches(key.prefix)))
const quotaText = value => value == null || value < 0 ? '不限' : String(value)
const noop = () => {}
onMounted(() => load())
</script>

<style scoped>
.admin-refresh-hint { margin: 6px 0 12px; font-size: 13px; }
.model-summary { display: grid; gap: 10px; margin: 22px 0 18px; }
.model-summary .admin-stats { margin: 0; }
.model-section { display: grid; gap: 8px; margin-top: 26px; }
.model-summary .admin-section-title { padding-bottom: 12px; }
</style>
