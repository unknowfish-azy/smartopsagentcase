<template>
  <section class="sentinel-surface" aria-labelledby="guardian-title">
    <header class="sentinel-page-header">
      <div>
        <h1 id="guardian-title">守护 Agent</h1>
      </div>
      <div class="guardian-actions">
        <button type="button" :disabled="busy" @click="learn">立即学习</button>
        <button type="button" :disabled="busy" @click="reload">刷新</button>
      </div>
    </header>
    <p class="sentinel-lede">
      告警一产生就自动补充证据（历史指标、同类告警、运维记忆），并持续从采集样本里学习指标基线。
      学习结果只产出**阈值建议**，必须人工确认后才写回阈值模板 —— 不会自动改生产阈值，也不会执行任何脚本。
    </p>

    <SentinelNotice v-if="error" tone="warn" title="守护 Agent 操作未完成" :detail="error" />

    <p class="sentinel-statusbar">
      <span>学习基线 <b>{{ stats.profiles ?? 0 }}</b></span>
      <span :class="{ 'is-bad': (stats.suggested ?? 0) > 0 }">待确认建议 <b>{{ stats.suggested ?? 0 }}</b></span>
      <span>已应用 <b>{{ stats.applied ?? 0 }}</b></span>
      <span>取证记录 <b>{{ stats.evidence ?? 0 }}</b></span>
    </p>

    <section class="sentinel-panel" aria-labelledby="guardian-profiles-title">
      <h2 id="guardian-profiles-title">阈值建议 / 基线学习</h2>
      <p class="sentinel-hint">
        基线窗口为每个指标最近 200 个数值样本；样本少于 20 个不做结论。建议值与原阈值偏差小于 10% 时标记为「稳定」，不打扰人。
      </p>

      <SentinelEmpty v-if="loaded && !profiles.length" title="还没有学习基线"
                     description="哨兵任务积累到 20 个数值样本后，守护 Agent 会自动学出 P95 基线并给出阈值建议。" />

      <div v-else-if="profiles.length" class="sentinel-table-wrap">
        <table>
          <caption class="sentinel-caption">指标基线学习结果</caption>
          <thead>
            <tr>
              <th scope="col">任务</th>
              <th scope="col">指标</th>
              <th scope="col">样本数</th>
              <th scope="col">均值</th>
              <th scope="col">P95</th>
              <th scope="col">当前阈值</th>
              <th scope="col">建议阈值</th>
              <th scope="col">状态</th>
              <th scope="col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="profile in profiles" :key="profile.id">
              <td>{{ profile.taskName || `#${profile.taskId}` }}</td>
              <td class="sentinel-mono">{{ profile.metric }}</td>
              <td>{{ profile.sampleCount }}</td>
              <td>{{ formatNumber(profile.avgValue) }}</td>
              <td>{{ formatNumber(profile.p95Value) }}</td>
              <td>{{ formatNumber(profile.currentThreshold) }}</td>
              <td>{{ formatNumber(profile.suggestedThreshold) }}</td>
              <td><span class="sentinel-tag" :class="statusClass(profile.status)">{{ statusLabel(profile.status) }}</span></td>
              <td>
                <button v-if="profile.status === 'SUGGESTED'" type="button" class="guardian-link" :disabled="busy"
                        @click="applyProfile(profile)">应用</button>
                <button v-if="profile.status === 'SUGGESTED'" type="button" class="guardian-link guardian-link--muted"
                        :disabled="busy" @click="dismissProfile(profile)">忽略</button>
                <span v-if="profile.status !== 'SUGGESTED'" class="sentinel-muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="sentinel-panel" aria-labelledby="guardian-evidence-title">
      <h2 id="guardian-evidence-title">自动取证记录</h2>
      <p class="sentinel-hint">
        告警产生后 30 秒内自动补齐证据；取证只读数据库，不执行脚本、不改变告警状态。
      </p>

      <SentinelEmpty v-if="loaded && !evidence.length" title="还没有取证记录"
                     description="哨兵命中阈值产生告警后，守护 Agent 会自动记录基线、同类告警与运维记忆。" />

      <div v-else-if="evidence.length" class="sentinel-table-wrap">
        <table>
          <caption class="sentinel-caption">最近告警取证明细</caption>
          <thead>
            <tr>
              <th scope="col">时间</th>
              <th scope="col">告警</th>
              <th scope="col">哨兵任务</th>
              <th scope="col">类型</th>
              <th scope="col">证据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in evidence" :key="item.id">
              <td>{{ formatTime(item.createdAt) }}</td>
              <td>{{ item.alertTitle || `#${item.alertId}` }}</td>
              <td>{{ item.taskName || '—' }}</td>
              <td><span class="sentinel-tag">{{ kindLabel(item.kind) }}</span></td>
              <td>
                <strong>{{ item.title }}</strong>
                <div v-if="item.detail" class="sentinel-muted">{{ item.detail }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import request from '../../utils/request.ts'
import SentinelNotice from './SentinelNotice.vue'
import SentinelEmpty from './SentinelEmpty.vue'
import './sentinel.css'

const profiles = ref([])
const evidence = ref([])
const stats = reactive({ profiles: 0, suggested: 0, applied: 0, evidence: 0 })
const loaded = ref(false)
const busy = ref(false)
const error = ref('')

const statusLabel = status => ({
  SUGGESTED: '待确认',
  APPLIED: '已应用',
  DISMISSED: '已忽略',
  STABLE: '稳定'
})[status] || status || '—'

const statusClass = status => `sentinel-tag--${{
  SUGGESTED: 'warn',
  APPLIED: 'ok',
  DISMISSED: 'muted',
  STABLE: 'ok'
}[status] || 'unknown'}`

const kindLabel = kind => ({
  BASELINE: '指标基线',
  RELATED_ALERT: '同类告警',
  MEMORY: '运维记忆'
})[kind] || kind || '—'

const formatNumber = value => (value === null || value === undefined ? '—' : Number(value).toFixed(2))
const formatTime = value => (value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—')

async function reload() {
  busy.value = true
  error.value = ''
  try {
    const [profileResponse, evidenceResponse, statsResponse] = await Promise.all([
      request.get('/api/sentinel/guardian/profiles'),
      request.get('/api/sentinel/guardian/evidence', { params: { limit: 50 } }),
      request.get('/api/sentinel/guardian/stats')
    ])
    profiles.value = profileResponse.data || []
    evidence.value = evidenceResponse.data || []
    Object.assign(stats, statsResponse.data || {})
    loaded.value = true
  } catch (failure) {
    error.value = failure?.response?.data?.message || failure.message || '守护 Agent 接口不可用'
  } finally {
    busy.value = false
  }
}

async function learn() {
  busy.value = true
  error.value = ''
  try {
    await request.post('/api/sentinel/guardian/learn')
    await reload()
  } catch (failure) {
    error.value = failure?.response?.data?.message || failure.message || '基线学习失败'
  } finally {
    busy.value = false
  }
}

async function applyProfile(profile) {
  const confirmed = window.confirm(
    `确认把 ${profile.metric} 的阈值从 ${formatNumber(profile.currentThreshold)} 调整为 ${formatNumber(profile.suggestedThreshold)}？\n这会写入任务绑定的阈值模板。`
  )
  if (!confirmed) return
  busy.value = true
  error.value = ''
  try {
    await request.post(`/api/sentinel/guardian/profiles/${profile.id}/apply`)
    await reload()
  } catch (failure) {
    error.value = failure?.response?.data?.message || failure.message || '应用建议失败'
  } finally {
    busy.value = false
  }
}

async function dismissProfile(profile) {
  busy.value = true
  error.value = ''
  try {
    await request.post(`/api/sentinel/guardian/profiles/${profile.id}/dismiss`)
    await reload()
  } catch (failure) {
    error.value = failure?.response?.data?.message || failure.message || '忽略建议失败'
  } finally {
    busy.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.guardian-actions{display:flex;gap:8px}
.guardian-link{background:none;border:none;padding:0 6px;color:var(--sentinel-accent,#3aa0ff);cursor:pointer;font:inherit}
.guardian-link:disabled{cursor:wait;opacity:.6}
.guardian-link--muted{color:var(--sentinel-muted,#8a94a6)}
</style>
