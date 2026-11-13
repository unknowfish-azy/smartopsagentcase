<template>
  <div ref="incidentsShellRef" class="sentinel-shell" :data-theme="resolvedTheme">
    <CanvasAmbientField v-if="!isMobile" class="sentinel-ambient" :palette-root="incidentsShellRef" :star-multiplier="1.8" connect-particles :connect-max-dist="130" />
    <div v-if="!isMobile" class="sentinel-aurora" aria-hidden="true"></div>
    <MeteorShower v-if="!isMobile" class="sentinel-meteors" />
    <div class="sentinel-mask" aria-hidden="true"></div>

  <section class="sentinel-surface" aria-labelledby="incidents-title">
    <header class="sentinel-page-header">
      <div>
        <p class="sentinel-eyebrow">INCIDENT CENTER / 工单中心</p>
        <h1 id="incidents-title">事件与工单</h1>
      </div>
      <button type="button" :disabled="state.loading" @click="reload">刷新</button>
    </header>
    <p class="sentinel-lede">
      把告警、AI 分析、审批、执行与复盘统一成一次故障处理。状态机
      <strong>OPEN → ACK → MITIGATING → RESOLVED → CLOSED</strong>；
      关闭必须填写根因、处置过程与复盘结论；误报可直接关闭，已关闭可重开。
    </p>

    <SentinelNotice v-if="state.status === 'unauthorized'" tone="warn" title="请先登录" detail="工单接口需要登录会话，未登录时无法读取数据。" />
    <SentinelNotice v-else-if="state.status === 'unavailable'" tone="warn" title="后端未接入" :detail="state.reason" />

    <dl class="sentinel-stats">
      <div v-for="item in INCIDENT_STATUSES" :key="item.id" class="sentinel-stat">
        <dt>{{ item.label }}</dt><dd>{{ countBy(item.id) }}</dd>
      </div>
    </dl>

    <div class="sentinel-editor" role="search">
      <label class="sentinel-field"><span>状态</span>
        <select v-model="filters.status">
          <option :value="''">全部</option>
          <option v-for="item in INCIDENT_STATUSES" :key="item.id" :value="item.id">{{ item.label }}</option>
        </select>
      </label>
      <label class="sentinel-field"><span>等级</span>
        <select v-model="filters.severity">
          <option :value="''">全部</option>
          <option v-for="item in INCIDENT_SEVERITIES" :key="item.id" :value="item.id">{{ item.label }}</option>
        </select>
      </label>
      <label class="sentinel-field"><span>负责人 ID</span>
        <input v-model.trim="filters.assigneeId" inputmode="numeric" placeholder="留空查看全部" />
      </label>
    </div>

    <SentinelEmpty
      v-if="state.status === 'ready' && visible.length === 0"
      title="没有符合条件的工单"
      description="列表为空可能是还没有事件，也可能是筛选条件太窄。清空筛选或刷新后再看。"
    />

    <div v-else-if="visible.length" class="sentinel-table-wrap">
      <table>
        <caption class="sentinel-caption">工单列表（按等级与创建时间排序）</caption>
        <thead>
          <tr>
            <th scope="col">等级</th>
            <th scope="col">标题</th>
            <th scope="col">状态</th>
            <th scope="col">来源</th>
            <th scope="col">负责人</th>
            <th scope="col">SLA</th>
            <th scope="col">创建时间</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="incident in visible" :key="incident.id">
            <td>
              <RouterLink :to="`/incidents/${incident.id}`" class="sentinel-tag" :class="`sentinel-tag--${(incident.severity || 'p3').toLowerCase()}`">
                {{ incident.severity || 'P3' }}
              </RouterLink>
            </td>
            <td><RouterLink :to="`/incidents/${incident.id}`">{{ incident.title }}</RouterLink></td>
            <td>{{ statusLabel(incident.status) }}</td>
            <td>{{ sourceLabel(incident.source) }}</td>
            <td class="sentinel-mono">{{ incident.assigneeId ? `#${incident.assigneeId}` : '未指派' }}</td>
            <td>
              <span v-if="slaText(incident) === null" class="sentinel-muted">—</span>
              <span v-else :class="{ 'sentinel-tag--p0': slaBreached(incident) }" class="sentinel-mono">{{ slaText(incident) }}</span>
            </td>
            <td class="sentinel-mono">{{ incident.createdAt || '—' }}</td>
            <td class="sentinel-actions">
              <RouterLink :to="`/incidents/${incident.id}`">详情</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="actionMessage" class="sentinel-hint sentinel-hint--table" role="status">{{ actionMessage }}</p>
    </div>

    <section class="sentinel-panel" aria-labelledby="incident-create-title">
      <h2 id="incident-create-title">新建工单</h2>
      <p class="sentinel-hint">
        手工创建适合用户报障与误报记录；告警产生的工单请在告警中心用「走团队审批」联动生成，避免重复建单。
      </p>
      <div class="sentinel-editor">
        <label class="sentinel-field sentinel-field--wide"><span>标题（必填）</span>
          <input v-model.trim="createForm.title" maxlength="128" placeholder="如 支付服务 5xx 升高" /></label>
        <label class="sentinel-field sentinel-field--wide"><span>描述</span>
          <textarea v-model.trim="createForm.description" rows="3" placeholder="现象、影响范围、初步观察" /></label>
        <label class="sentinel-field"><span>等级</span>
          <select v-model="createForm.severity">
            <option v-for="item in INCIDENT_SEVERITIES" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select></label>
        <label class="sentinel-field"><span>来源</span>
          <select v-model="createForm.source">
            <option v-for="item in INCIDENT_SOURCES" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select></label>
        <label class="sentinel-field"><span>SLA（分钟）</span>
          <input v-model.number="createForm.slaTargetMinutes" inputmode="numeric" placeholder="留空表示不设 SLA" /></label>
        <label class="sentinel-field"><span>关联服务</span>
          <input v-model.trim="createForm.relatedService" placeholder="如 payment-api" /></label>
      </div>
      <div class="sentinel-editor__actions">
        <button type="button" :disabled="creating || !createRequestReady(createForm)" @click="submitCreate">
          {{ creating ? '正在创建…' : '创建工单' }}</button>
        <span class="sentinel-muted">{{ createRequestReady(createForm) ? '创建后状态为 OPEN' : '请填写标题' }}</span>
      </div>
      <p v-if="createMessage" class="sentinel-hint" role="status">{{ createMessage }}</p>
    </section>
  </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, defineAsyncComponent } from 'vue'
import SentinelNotice from '../sentinel/SentinelNotice.vue'
import SentinelEmpty from '../sentinel/SentinelEmpty.vue'
import { resolvedTheme as _resolvedTheme } from '../../theme.js'
import { searchIncidents, createIncident } from '../../api/incident'
import {
  INCIDENT_SEVERITIES,
  INCIDENT_SOURCES,
  INCIDENT_STATUSES,
  createRequestReady,
  slaRemainingMinutes,
  sortIncidents,
  sourceLabel,
  statusLabel
} from './incidentModel'
import '../sentinel/sentinel.css'

const CanvasAmbientField = defineAsyncComponent(() => import('../../components/common/CanvasAmbientField.vue'))
const MeteorShower = defineAsyncComponent(() => import('../../components/common/MeteorShower.vue'))

const incidentsShellRef = ref(null)
const resolvedTheme = computed(() => _resolvedTheme.value)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)
function updateMobile() { isMobile.value = window.innerWidth < 1024 }

const state = reactive({
  loading: false,
  /** 'ready' | 'unauthorized' | 'unavailable'，与哨兵模块口径一致：不填充假数据 */
  status: 'unknown',
  reason: '',
  incidents: []
})

const filters = reactive({ status: '', severity: '', assigneeId: '' })
const creating = ref(false)
const createMessage = ref('')
const actionMessage = ref('')

const createForm = reactive({
  title: '',
  description: '',
  severity: 'P3',
  source: 'MANUAL',
  slaTargetMinutes: null,
  relatedService: ''
})

/** 本地过滤：后端 search 已支持 status/severity/assigneeId，前端再做一层兜底排序与过滤。 */
const visible = computed(() => sortIncidents(
  state.incidents.filter(item => {
    if (filters.status && item.status !== filters.status) return false
    if (filters.severity && item.severity !== filters.severity) return false
    if (filters.assigneeId && String(item.assigneeId ?? '') !== filters.assigneeId) return false
    return true
  })
))

const countBy = status => state.incidents.filter(item => item.status === status).length

function failureMessage(error, fallback) {
  const status = error?.response?.status
  if (status === 401) return 'unauthorized'
  return error?.response?.data?.message || error?.message || fallback
}

async function reload() {
  state.loading = true
  try {
    const response = await searchIncidents()
    state.incidents = Array.isArray(response.data?.data) ? response.data.data : []
    state.status = 'ready'
    state.reason = ''
  } catch (error) {
    const message = failureMessage(error, '工单列表加载失败')
    if (message === 'unauthorized') {
      state.status = 'unauthorized'
      state.reason = ''
    } else {
      state.status = 'unavailable'
      state.reason = message
    }
  } finally {
    state.loading = false
  }
}

function slaRemaining(incident) {
  return slaRemainingMinutes(incident.slaDeadline, new Date())
}

function slaBreached(incident) {
  const remaining = slaRemaining(incident)
  return remaining !== null && remaining < 0 && incident.status !== 'CLOSED'
}

function slaText(incident) {
  const remaining = slaRemaining(incident)
  if (remaining === null) return null
  if (incident.status === 'CLOSED' || incident.status === 'RESOLVED') return '已结束'
  return remaining < 0 ? `超时 ${-remaining} 分钟` : `剩 ${remaining} 分钟`
}

async function submitCreate() {
  creating.value = true
  createMessage.value = ''
  try {
    const payload = {
      title: createForm.title,
      description: createForm.description || undefined,
      severity: createForm.severity,
      source: createForm.source,
      slaTargetMinutes: Number.isFinite(createForm.slaTargetMinutes) ? createForm.slaTargetMinutes : undefined,
      relatedService: createForm.relatedService || undefined
    }
    const response = await createIncident(payload)
    const created = response.data?.data
    createMessage.value = created?.id
      ? `已创建工单 #${created.id}（OPEN）。`
      : '创建已提交，但未返回工单编号。'
    createForm.title = ''
    createForm.description = ''
    createForm.slaTargetMinutes = null
    createForm.relatedService = ''
    await reload()
  } catch (error) {
    createMessage.value = failureMessage(error, '创建失败，请重试。')
  } finally {
    creating.value = false
  }
}

onMounted(() => { updateMobile(); window.addEventListener('resize', updateMobile); reload() })
onBeforeUnmount(() => window.removeEventListener('resize', updateMobile))
</script>

<style scoped>
/* === 启佑风格背景层 === */
.sentinel-shell{position:relative;min-height:calc(100vh - 64px);overflow:hidden;background:radial-gradient(ellipse at 80% 10%,rgba(122,215,245,.10) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(63,185,80,.07) 0%,transparent 50%),#040B16}
.sentinel-shell[data-theme='light']{background:radial-gradient(ellipse at 80% 10%,rgba(26,110,154,.07) 0%,transparent 50%),radial-gradient(ellipse at 20% 90%,rgba(26,127,55,.04) 0%,transparent 50%),#EAF3FA}
.sentinel-ambient{position:absolute;inset:0;z-index:0;opacity:.48;pointer-events:none}
.sentinel-meteors{position:absolute;inset:0;z-index:0;opacity:.35;pointer-events:none}
.sentinel-aurora{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at 75% 15%,rgba(122,215,245,.22) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(63,185,80,.16) 0%,transparent 45%);filter:blur(24px);background-size:240% 240%;animation:sentinel-drift 22s ease-in-out infinite alternate}
.sentinel-aurora::after{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(122,215,245,.35),transparent 70%);filter:blur(18px);animation:sentinel-sweep 32s ease-in-out infinite}
.sentinel-shell[data-theme='light'] .sentinel-aurora{background:radial-gradient(ellipse at 75% 15%,rgba(26,110,154,.14) 0%,transparent 45%),radial-gradient(ellipse at 30% 85%,rgba(26,127,55,.10) 0%,transparent 45%)}
.sentinel-shell[data-theme='light'] .sentinel-aurora::after{background:radial-gradient(ellipse 30% 20% at 15% 50%,rgba(26,110,154,.22),transparent 70%)}
@keyframes sentinel-drift{0%{background-position:0% 0%,100% 100%;transform:translate3d(0,0,0)}100%{background-position:30% 10%,70% 90%;transform:translate3d(-2%,2%,0)}}
@keyframes sentinel-sweep{0%,100%{opacity:.55;transform:translate3d(0,0,0)}50%{opacity:1;transform:translate3d(-8%,4%,0)}}
@media(prefers-reduced-motion:reduce){.sentinel-aurora,.sentinel-aurora::after{animation:none}}
.sentinel-mask{position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at center,transparent 40%,rgba(4,11,22,.42) 100%)}
.sentinel-shell[data-theme='light'] .sentinel-mask{background:radial-gradient(ellipse at center,transparent 40%,rgba(234,243,250,.42) 100%)}
.sentinel-shell>.sentinel-surface{position:relative;z-index:1}
</style>
