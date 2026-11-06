<template>
  <section class="sentinel-surface" aria-labelledby="incident-detail-title">
    <header class="sentinel-page-header">
      <div>
        <p class="sentinel-eyebrow">INCIDENT CENTER / 工单详情</p>
        <h1 id="incident-detail-title">
          <span class="sentinel-tag" :class="`sentinel-tag--${(incident?.severity || 'p3').toLowerCase()}`">{{ incident?.severity || 'P3' }}</span>
          {{ incident?.title || (loading ? '加载中…' : '工单不存在') }}
        </h1>
      </div>
      <div class="sentinel-actions">
        <RouterLink to="/incidents">返回列表</RouterLink>
        <button type="button" :disabled="loading || !incident" @click="reload">刷新</button>
      </div>
    </header>

    <SentinelNotice v-if="status === 'unauthorized'" tone="warn" title="请先登录" detail="工单接口需要登录会话。" />
    <SentinelNotice v-else-if="status === 'unavailable'" tone="warn" title="加载失败" :detail="reason" />

    <template v-if="incident">
      <dl class="sentinel-stats">
        <div class="sentinel-stat"><dt>状态</dt><dd>{{ statusLabel(incident.status) }}</dd></div>
        <div class="sentinel-stat"><dt>来源</dt><dd>{{ sourceLabel(incident.source) }}</dd></div>
        <div class="sentinel-stat"><dt>负责人</dt><dd class="sentinel-mono">{{ incident.assigneeId ? `#${incident.assigneeId}` : '未指派' }}</dd></div>
        <div class="sentinel-stat"><dt>SLA</dt><dd>{{ slaText }}</dd></div>
      </dl>

      <section class="sentinel-panel" aria-labelledby="incident-info-title">
        <h2 id="incident-info-title">基本信息</h2>
        <p v-if="incident.description" class="sentinel-hint">{{ incident.description }}</p>
        <dl class="sentinel-flow">
          <li><strong>等级 / 优先级</strong><span>{{ severityLabel(incident.severity) }} / {{ severityLabel(incident.priority) }}</span></li>
          <li v-if="incident.category"><strong>分类</strong><span>{{ incident.category }}</span></li>
          <li v-if="incident.tags"><strong>标签</strong><span>{{ incident.tags }}</span></li>
          <li v-if="incident.relatedService"><strong>关联服务</strong><span>{{ incident.relatedService }}</span></li>
          <li v-if="incident.slaTargetMinutes"><strong>SLA 目标</strong><span>{{ incident.slaTargetMinutes }} 分钟（截止 {{ incident.slaDeadline || '—' }}）</span></li>
          <li><strong>创建 / 更新</strong><span class="sentinel-mono">{{ incident.createdAt || '—' }} / {{ incident.updatedAt || '—' }}</span></li>
          <li v-if="incident.rootCause"><strong>根因</strong><span>{{ incident.rootCause }}</span></li>
          <li v-if="incident.resolution"><strong>处置过程</strong><span>{{ incident.resolution }}</span></li>
          <li v-if="incident.postmortem"><strong>复盘结论</strong><span>{{ incident.postmortem }}</span></li>
        </dl>
        <p v-if="actionMessage" class="sentinel-hint" role="status">{{ actionMessage }}</p>
      </section>

      <section class="sentinel-panel" aria-labelledby="incident-actions-title">
        <h2 id="incident-actions-title">状态流转</h2>
        <p class="sentinel-hint">
          可流转目标：<span class="sentinel-mono">{{ transitions.join(' → ') || '无（状态未知）' }}</span>。
          最终以后端状态机校验为准，前端只做提前禁用。
        </p>
        <div class="sentinel-editor__actions">
          <button type="button" :disabled="busy || !canGo('ACK')" @click="transition('acknowledge')">接单（ACK）</button>
          <button type="button" :disabled="busy || !canGo('MITIGATING')" @click="transition('mitigate')">开始处置</button>
          <button type="button" :disabled="busy || !canGo('RESOLVED')" @click="resolveNow">标记已解决</button>
          <button type="button" :disabled="busy || !canGo('CLOSED')" @click="closeOpen = !closeOpen">关闭工单…</button>
          <button type="button" :disabled="busy || !canGo('OPEN')" @click="transition('reopen')">重开</button>
        </div>

        <label v-if="canGo('RESOLVED')" class="sentinel-field sentinel-field--wide">
          <span>解决说明（可选，随「标记已解决」提交）</span>
          <textarea v-model.trim="resolveText" rows="2" placeholder="已采取的缓解措施" />
        </label>

        <div v-if="closeOpen && canGo('CLOSED')" class="sentinel-editor">
          <p class="sentinel-hint">关闭必须填写根因、处置过程与复盘结论（后端强制校验）。</p>
          <label class="sentinel-field sentinel-field--wide"><span>根因（必填）</span>
            <textarea v-model.trim="closeForm.rootCause" rows="2" placeholder="导致故障的根本原因" /></label>
          <label class="sentinel-field sentinel-field--wide"><span>处置过程（必填）</span>
            <textarea v-model.trim="closeForm.resolution" rows="2" placeholder="实际执行的处置动作与结果" /></label>
          <label class="sentinel-field sentinel-field--wide"><span>复盘结论（必填）</span>
            <textarea v-model.trim="closeForm.postmortem" rows="2" placeholder="后续改进项与经验" /></label>
          <div class="sentinel-editor__actions">
            <button type="button" :disabled="busy || !closeRequestReady(closeForm)" @click="submitClose">确认关闭</button>
            <span class="sentinel-muted">{{ closeRequestReady(closeForm) ? '关闭后状态为 CLOSED，可重开' : '三项都必填' }}</span>
          </div>
        </div>
      </section>

      <section class="sentinel-panel" aria-labelledby="incident-assign-title">
        <h2 id="incident-assign-title">指派 / 转派</h2>
        <div class="sentinel-editor">
          <label class="sentinel-field"><span>负责人用户 ID</span>
            <input v-model.trim="assignForm.assigneeId" inputmode="numeric" placeholder="如 42" /></label>
          <div class="sentinel-editor__actions">
            <button type="button" :disabled="busy || !assignReady" @click="submitAssign">提交指派</button>
            <span class="sentinel-muted">{{ assigneeHint }}</span>
          </div>
        </div>
      </section>

      <section class="sentinel-panel" aria-labelledby="incident-comments-title">
        <h2 id="incident-comments-title">评论</h2>
        <div class="sentinel-editor">
          <label class="sentinel-field sentinel-field--wide"><span>新评论</span>
            <textarea v-model.trim="commentText" rows="2" placeholder="处理进展、外部沟通记录" /></label>
          <div class="sentinel-editor__actions">
            <button type="button" :disabled="busy || !commentText" @click="submitComment">添加评论</button>
          </div>
        </div>
      </section>

      <section class="sentinel-panel" aria-labelledby="incident-timeline-title">
        <h2 id="incident-timeline-title">时间线</h2>
        <table v-if="events.length">
          <caption class="sentinel-caption">事件时间线（含状态流转、评论、指派与 SLA 提醒）</caption>
          <thead>
            <tr><th scope="col">时间</th><th scope="col">类型</th><th scope="col">操作人</th><th scope="col">内容</th></tr>
          </thead>
          <tbody>
            <tr v-for="event in events" :key="event.id">
              <td class="sentinel-mono">{{ event.at || '—' }}</td>
              <td>{{ eventKindLabel(event.kind) }}</td>
              <td class="sentinel-mono">{{ event.actorId ? `#${event.actorId}` : '系统' }}</td>
              <td>{{ event.detail || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="sentinel-muted">还没有事件记录。</p>
      </section>

      <section class="sentinel-panel" aria-labelledby="incident-relations-title">
        <h2 id="incident-relations-title">关联（告警 / Agent 运行 / 知识 / 证据）</h2>
        <table v-if="relations.length">
          <caption class="sentinel-caption">关联对象</caption>
          <thead>
            <tr><th scope="col">类型</th><th scope="col">目标</th><th scope="col">说明</th><th scope="col">创建时间</th><th scope="col">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="relation in relations" :key="relation.id">
              <td>{{ relationTypeLabel(relation.relationType) }}</td>
              <td class="sentinel-mono">{{ relation.relationType }}#{{ relation.refId }}</td>
              <td>{{ relation.refType || '—' }}</td>
              <td class="sentinel-mono">{{ relation.createdAt || '—' }}</td>
              <td>
                <button type="button" :disabled="busy" @click="removeRelation(relation)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="sentinel-muted">还没有关联对象。</p>
        <div class="sentinel-editor">
          <label class="sentinel-field"><span>关联类型</span>
            <select v-model="relationForm.relationType">
              <option v-for="item in INCIDENT_RELATION_TYPES" :key="item.id" :value="item.id">{{ item.label }}</option>
            </select></label>
          <label class="sentinel-field"><span>目标 ID</span>
            <input v-model.trim="relationForm.refId" inputmode="numeric" placeholder="如 123" /></label>
          <label class="sentinel-field"><span>说明（可选）</span>
            <input v-model.trim="relationForm.refType" placeholder="如 sentinel-alert" /></label>
          <div class="sentinel-editor__actions">
            <button type="button" :disabled="busy || !relationReady" @click="submitRelation">添加关联</button>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SentinelNotice from '../sentinel/SentinelNotice.vue'
import {
  acknowledgeIncident,
  addIncidentComment,
  addIncidentRelation,
  assignIncident,
  closeIncident,
  getIncident,
  listIncidentEvents,
  listIncidentRelations,
  mitigateIncident,
  removeIncidentRelation,
  reopenIncident,
  resolveIncident
} from '../../api/incident'
import {
  INCIDENT_RELATION_TYPES,
  allowedTransitions,
  canTransitionTo,
  closeRequestReady,
  eventKindLabel,
  relationTypeLabel,
  severityLabel,
  slaRemainingMinutes,
  sourceLabel,
  statusLabel
} from './incidentModel'
import '../sentinel/sentinel.css'

const route = useRoute()

const incident = ref(null)
const events = ref([])
const relations = ref([])
const loading = ref(false)
const busy = ref(false)
const status = ref('unknown')
const reason = ref('')
const actionMessage = ref('')
const closeOpen = ref(false)
const resolveText = ref('')
const commentText = ref('')

const closeForm = reactive({ rootCause: '', resolution: '', postmortem: '' })
const assignForm = reactive({ assigneeId: '' })
const relationForm = reactive({ relationType: 'ALERT', refId: '', refType: '' })

const incidentId = computed(() => route.params.id)

const transitions = computed(() => (incident.value ? allowedTransitions(incident.value.status) : []))
const canGo = target => canTransitionTo(incident.value?.status, target)
const assignReady = computed(() => /^\d{1,19}$/.test(assignForm.assigneeId))
const assigneeHint = computed(() =>
  assignReady.value ? '指派会记录为时间线事件' : '请填写数字用户 ID')
const relationReady = computed(() => /^\d{1,19}$/.test(relationForm.refId))

const slaText = computed(() => {
  if (!incident.value) return '—'
  const remaining = slaRemainingMinutes(incident.value.slaDeadline, new Date())
  if (remaining === null) return '未设置'
  if (incident.value.status === 'CLOSED' || incident.value.status === 'RESOLVED') return '已结束'
  return remaining < 0 ? `已超时 ${-remaining} 分钟` : `剩 ${remaining} 分钟`
})

function failureMessage(error, fallback) {
  return error?.response?.data?.message || error?.message || fallback
}

async function reload() {
  const id = incidentId.value
  if (!id) return
  loading.value = true
  status.value = 'unknown'
  reason.value = ''
  try {
    const [detail, eventList, relationList] = await Promise.all([
      getIncident(id),
      listIncidentEvents(id).catch(() => ({ data: { data: [] } })),
      listIncidentRelations(id).catch(() => ({ data: { data: [] } }))
    ])
    incident.value = detail.data?.data ?? null
    events.value = Array.isArray(eventList.data?.data) ? eventList.data.data : []
    relations.value = Array.isArray(relationList.data?.data) ? relationList.data.data : []
    status.value = incident.value ? 'ready' : 'unavailable'
    if (!incident.value) reason.value = '工单不存在或已删除。'
  } catch (error) {
    const code = error?.response?.status
    if (code === 401) {
      status.value = 'unauthorized'
    } else {
      status.value = 'unavailable'
      reason.value = failureMessage(error, '工单详情加载失败')
    }
  } finally {
    loading.value = false
  }
}

/** 单按钮状态流转：acknowledge / mitigate / reopen。 */
async function transition(action) {
  busy.value = true
  actionMessage.value = ''
  try {
    const call = { acknowledge: acknowledgeIncident, mitigate: mitigateIncident, reopen: reopenIncident }[action]
    const response = await call(incidentId.value)
    incident.value = response.data?.data ?? incident.value
    actionMessage.value = `已流转到 ${statusLabel(incident.value.status)}。`
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '流转失败，请重试。')
  } finally {
    busy.value = false
  }
}

async function resolveNow() {
  busy.value = true
  actionMessage.value = ''
  try {
    const response = await resolveIncident(incidentId.value, resolveText.value)
    incident.value = response.data?.data ?? incident.value
    actionMessage.value = `已流转到 ${statusLabel(incident.value.status)}。`
    resolveText.value = ''
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '标记解决失败，请重试。')
  } finally {
    busy.value = false
  }
}

async function submitClose() {
  busy.value = true
  actionMessage.value = ''
  try {
    const response = await closeIncident(incidentId.value, { ...closeForm })
    incident.value = response.data?.data ?? incident.value
    actionMessage.value = '工单已关闭，复盘内容已归档。'
    closeOpen.value = false
    closeForm.rootCause = ''
    closeForm.resolution = ''
    closeForm.postmortem = ''
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '关闭失败，请检查三项必填内容。')
  } finally {
    busy.value = false
  }
}

async function submitAssign() {
  busy.value = true
  actionMessage.value = ''
  try {
    const response = await assignIncident(incidentId.value, { assigneeId: Number(assignForm.assigneeId) })
    incident.value = response.data?.data ?? incident.value
    actionMessage.value = `已指派给 #${incident.value.assigneeId}。`
    assignForm.assigneeId = ''
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '指派失败，请确认用户 ID。')
  } finally {
    busy.value = false
  }
}

async function submitComment() {
  busy.value = true
  actionMessage.value = ''
  try {
    await addIncidentComment(incidentId.value, { content: commentText.value })
    actionMessage.value = '评论已添加到时间线。'
    commentText.value = ''
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '评论失败，请重试。')
  } finally {
    busy.value = false
  }
}

async function submitRelation() {
  busy.value = true
  actionMessage.value = ''
  try {
    await addIncidentRelation(incidentId.value, {
      relationType: relationForm.relationType,
      refId: Number(relationForm.refId),
      refType: relationForm.refType || undefined
    })
    actionMessage.value = '关联已添加。'
    relationForm.refId = ''
    relationForm.refType = ''
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '添加关联失败，请确认目标 ID。')
  } finally {
    busy.value = false
  }
}

async function removeRelation(relation) {
  busy.value = true
  actionMessage.value = ''
  try {
    await removeIncidentRelation(incidentId.value, relation.id)
    actionMessage.value = '关联已移除。'
    await reload()
  } catch (error) {
    actionMessage.value = failureMessage(error, '移除关联失败。')
  } finally {
    busy.value = false
  }
}

watch(incidentId, reload)
onMounted(reload)
</script>
