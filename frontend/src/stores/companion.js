import { computed, reactive, ref, onScopeDispose } from 'vue'
import { defineStore } from 'pinia'
import { createCompanionEvent, createCompanionEventBus, immutableSnapshot } from '../domain/companion/eventBus.js'
import { createCompanionContext, snapshotCompanionContext } from '../domain/companion/context.js'
import { resolveAttention, capabilityStatuses } from '../domain/companion/attention.js'
import { useInvestigationStore } from './investigation.js'

export const useCompanionStore = defineStore('companion', () => {
  const investigation = useInvestigationStore()
  const bus = createCompanionEventBus()
  const sessionId = `session-${crypto.randomUUID()}`
  const createdAt = new Date().toISOString()
  const mode = ref('NORMAL'), drawerOpen = ref(false), events = ref([]), page = ref(''), lastError = ref('')
  const capabilities = reactive({
    ai: { status: 'offline', detail: '尚未接入推理模型；使用本地问题规则' },
    knowledge: { status: 'available', detail: '本地关键词检索' },
    visual: { status: 'offline', detail: '尚未接入捕获 / OCR，仅接收证据事件' },
    telemetry: { status: 'offline', detail: '基础设施数据未接入' }
  })
  const states = computed(() => ({
    spider: investigation.activeContext ? (drawerOpen.value ? 'INVESTIGATING' : 'ANOMALY') : 'IDLE',
    jellyfish: !drawerOpen.value ? 'WAIT' : investigation.activeContext?.state === 'READY' ? 'RECOMMENDING' : 'QUESTIONING',
    whale: 'UNKNOWN', interaction: mode.value
  }))
  const attentionPolicy = computed(() => investigation.activeFault ? resolveAttention({ severity: investigation.activeFault.severity, userMode: mode.value }) : 'silent')
  const context = computed(() => {
    const source = investigation.activeContext
    return createCompanionContext({ ...source, id: source?.id || sessionId, sessionId,
      activePage: source?.page || page.value, investigationState: source?.state || 'IDLE',
      capabilityStatuses: Object.entries(capabilities).map(([name, value]) => ({ name, ...value })),
      mode: mode.value, attentionPolicy: attentionPolicy.value,
      createdAt: source?.createdAt || createdAt, updatedAt: source?.updatedAt || createdAt })
  })
  const contextSnapshot = computed(() => snapshotCompanionContext(context.value))
  function publish(type, payload = {}, source = 'companion') {
    const event = createCompanionEvent({ type, source, contextId: context.value.id, payload })
    events.value = [...events.value.slice(-199), event]
    bus.publish(event)
    return event
  }
  function ingestFault(input) {
    if (!input || !Array.isArray(input.evidence) || !input.evidence.some(item => typeof item?.content === 'string' && item.content.trim())) throw new TypeError('Fault Event 必须包含非空证据')
    const safe = immutableSnapshot(input)
    if (safe.id && investigation.faultEvents.some(item => item.id === safe.id)) return investigation.faultEvents.find(item => item.id === safe.id)
    const event = investigation.detect(safe)
    drawerOpen.value = false
    publish('FAULT_DETECTED', { faultEvent: event }, 'spider')
    lastError.value = ''
    return event
  }
  function publishQuestion() {
    const source = investigation.activeContext
    const question = source?.questions.find(item => !source.answers.some(answer => answer.questionId === item.id))
    if (question) publish('QUESTION_REQUIRED', { question }, 'smart-inquiry')
  }
  function openInvestigation() {
    if (!investigation.activeContext) return
    drawerOpen.value = true
    publish('USER_CLICKED_SPIDER')
    publish('INVESTIGATION_STARTED')
    publishQuestion()
  }
  function closeInvestigation() { drawerOpen.value = false }
  function recordAnswer(answer) {
    const safe = immutableSnapshot(answer), source = investigation.activeContext
    if (!source?.questions.some(question => question.id === safe.questionId)) throw new TypeError('Unknown inquiry question')
    investigation.addAnswer(safe)
    investigation.setState(source.questions.every(question => source.answers.some(item => item.questionId === question.id)) ? 'READY' : 'WAITING_USER')
    publish('ANSWER_RECORDED', { answer: safe }, 'smart-inquiry')
    publishQuestion()
    prepareRecommendations()
  }
  function prepareRecommendations() {
    const source = investigation.activeContext
    if (!source || source.state !== 'READY') return
    source.recommendations = source.knowledgeReferences.map(reference => ({
      id: `recommendation-${reference.documentId}`, kind: 'RECOMMENDATION',
      text: `建议先核对「${reference.title}」的 ${reference.section}：${reference.matchedText}`,
      documentId: reference.documentId, source: reference.source, section: reference.section,
      risk: reference.risk, executionAllowed: false
    }))
    if (source.recommendations.length) publish('RECOMMENDATION_READY', { recommendations: source.recommendations }, 'knowledge')
  }
  function addKnowledgeReference(reference) {
    if (!investigation.activeContext) return
    const safe = immutableSnapshot(reference)
    if (!safe.documentId || !safe.source || !safe.section || !safe.matchedText || !safe.risk) throw new TypeError('Knowledge reference requires source, section, evidence and risk')
    investigation.addKnowledgeReference(safe)
    publish('KNOWLEDGE_REFERENCED', { reference: safe }, 'knowledge')
    prepareRecommendations()
  }
  function setCapabilityStatus(name, status, detail = '') {
    if (!Object.hasOwn(capabilities, name) || !capabilityStatuses.includes(status)) throw new TypeError('Unsupported capability status')
    capabilities[name] = { status, detail: String(detail) }
    publish('CAPABILITY_CHANGED', { name, status, detail: String(detail) })
  }
  function setInteractionMode(value) {
    if (!['NORMAL', 'FOCUS', 'QUIET'].includes(value)) throw new TypeError('Unsupported interaction mode')
    mode.value = value
    publish('ATTENTION_CHANGED', { mode: value })
  }
  function connectLegacyEvents(target) {
    const detect = event => { try { ingestFault(event.detail) } catch (error) { lastError.value = error.message } }
    const open = () => openInvestigation()
    target.addEventListener('smartops:fault-detected', detect)
    target.addEventListener('smartops:open-investigation', open)
    return () => { target.removeEventListener('smartops:fault-detected', detect); target.removeEventListener('smartops:open-investigation', open) }
  }
  onScopeDispose(() => bus.clear())
  return { context, contextSnapshot, states, capabilities, attentionPolicy, drawerOpen, events, lastError,
    publish, ingestFault, recordAnswer, addKnowledgeReference, setCapabilityStatus, setInteractionMode,
    openInvestigation, closeInvestigation, connectLegacyEvents, setPage: value => { page.value = String(value) }, subscribe: bus.subscribe }
})
