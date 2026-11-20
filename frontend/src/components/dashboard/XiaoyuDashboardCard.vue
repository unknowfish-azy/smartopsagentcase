<template>
  <article class="ops-card xiaoyu-card" aria-label="小鱼 · 3D 化身面板">
    <header class="ops-card__head">
      <div class="ops-card__titles">
        <span class="u-overline">XIAOYU · 智能体化身</span>
        <h3 class="u-section">小鱼</h3>
      </div>
      <button type="button" class="xiaoyu-state-pill" :data-state="personaState" :title="`点击切换状态（演示） · 当前：${personaStateLabel}`" @click="cycleDemoState">{{ personaStateLabel }}</button>
    </header>

    <div class="xiaoyu-body">
      <!-- 3D 半身舞台：点击小鱼开口说话；情境气泡浮动在场景内（蒸馏 PetLive「角色住在空间里」） -->
      <button type="button" class="xiaoyu-stage" aria-label="小鱼 3D 形象 · 点击让小鱼说话" @click="speakGreeting">
        <AgentPersona
          v-if="personaLoaded"
          ref="personaRef"
          :state="personaState"
          mode="vrm"
          quality="auto"
        />
        <!-- #perf: 3D 未就绪时先用 CSS 静态封面占位，让首屏先出再升级 -->
        <div v-else class="xiaoyu-stage-placeholder" aria-hidden="true">
          <div class="xiaoyu-placeholder-silhouette"></div>
        </div>
        <p class="xiaoyu-bubble">{{ bubbleText }}</p>
      </button>

      <div class="xiaoyu-side">
        <!-- 就地对话流：不跳转 /chat，回答直接显示在这里 -->
        <div v-if="visibleMessages.length" ref="threadRef" class="xiaoyu-thread" aria-label="小鱼对话记录" role="log">
          <div v-for="msg in visibleMessages" :key="msg.id" class="xiaoyu-msg" :class="`xiaoyu-msg--${msg.role}`">
            <span class="xiaoyu-msg-role">{{ msg.role === 'user' ? '我' : '小鱼' }}</span>
            <div class="xiaoyu-msg-body">
              <div v-if="msg.images?.length" class="xiaoyu-msg-images">
                <img v-for="(src, idx) in msg.images" :key="idx" :src="src" :alt="`附图 ${idx + 1}`" />
              </div>
              <span v-if="msg.error" class="xiaoyu-msg-error">{{ msg.content }}</span>
              <!-- 助手回复统一按 Markdown 渲染（先转义再转换，v-html 无注入面）；流式进行中保留逐字纯文本 -->
              <div v-else-if="msg.role === 'assistant' && !msg.pending && !msg.streaming" class="xiaoyu-msg-text ai-chat-markdown" v-html="renderMarkdown(msg.content)"></div>
              <span v-else class="xiaoyu-msg-text">{{ msg.content || (msg.pending ? '思考中…' : '') }}</span>
            </div>
          </div>
        </div>

        <!-- 待发送图片 tray -->
        <div v-if="staged.length" class="xiaoyu-tray" aria-label="待发送图片">
          <div v-for="item in staged" :key="item.id" class="xiaoyu-tray-item">
            <img :src="item.preview" :alt="item.name" />
            <button type="button" :aria-label="`移除 ${item.name}`" @click="removeImage(item.id)">×</button>
          </div>
        </div>

        <!-- 快捷对话输入（支持文字 + 图片多模态） -->
        <form class="xiaoyu-input" @submit.prevent="onSend">
          <input ref="fileInput" class="xiaoyu-file" type="file" accept="image/png,image/jpeg" multiple @change="onPick" />
          <button type="button" class="xiaoyu-attach" title="添加图片（多模态）" aria-label="添加图片" :disabled="sending" @click="fileInput?.click()">＋图</button>
          <textarea
            v-model="input"
            rows="2"
            maxlength="2000"
            placeholder="跟小鱼说点什么…（可粘贴图片，回车发送）"
            @keydown.enter.exact.prevent="onSend"
            @paste="onPaste"
          ></textarea>
          <button type="submit" class="xiaoyu-send" :disabled="(!input.trim() && !staged.length) || sending">
            {{ sending ? '思考中…' : '发送 →' }}
          </button>
        </form>

        <!-- 3 个快捷按钮：就地填充问题，不再跳转 -->
        <div class="xiaoyu-quicks">
          <button v-for="q in QUICK_PROMPTS" :key="q.label" type="button" class="xiaoyu-quick" @click="fillQuick(q)">{{ q.label }}</button>
        </div>

        <!-- RAG + Agent 训练 双行指标：可点击跳转对应详情 -->
        <div class="xiaoyu-metrics">
          <button type="button" class="xiaoyu-metric" @click="router.push('/knowledge/space')">
            <span class="xiaoyu-metric-label">RAG</span>
            <strong>{{ ragTotal }}</strong>
            <span class="xiaoyu-metric-hint">知识条目 · 点击查看</span>
          </button>
          <button type="button" class="xiaoyu-metric" @click="router.push('/agent/module#loop')">
            <span class="xiaoyu-metric-label">训练</span>
            <strong>{{ agentStats.conversations }}</strong>
            <span class="xiaoyu-metric-hint">对话历史 · 点击查看</span>
          </button>
          <button type="button" class="xiaoyu-metric" @click="router.push('/model/strength')">
            <span class="xiaoyu-metric-label">技能</span>
            <strong>{{ agentStats.skills }}</strong>
            <span class="xiaoyu-metric-hint">可用 · 点击查看</span>
          </button>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
// #perf: 异步加载 3D 化身——避免 15MB VRM 模型在首屏同步阻塞主线程
const AgentPersona = defineAsyncComponent(() => import('../persona/AgentPersona.vue'))
import { useCompanionStore } from '../../stores/companion.js'
import { useAiChatStore } from '../../stores/aiChat.js'
import { renderMarkdown } from '../ai/markdown.js'
import '../ai/markdown.css'

const router = useRouter()
const companion = useCompanionStore()
const aiChat = useAiChatStore()

const personaRef = ref(null)
const personaLoaded = ref(false) // #perf: 空闲后才真正渲染 3D，避免首屏 VRM 解析长任务
const fileInput = ref(null)
const threadRef = ref(null)
const input = ref('')
const sending = computed(() => aiChat.sending)
const staged = ref([]) // [{ id, name, preview, dataUrl }]

// 最多 5 张、单张 10MB、合计 20MB，与 ai-service schema max_length=5 对齐。
const MAX_IMAGES = 5
const MAX_BYTES = 10 * 1024 * 1024
const TOTAL_BYTES = 20 * 1024 * 1024

const QUICK_PROMPTS = [
  { label: '一键体检', text: '帮我做一次系统健康体检，指出当前最需要关注的风险。' },
  { label: '读取知识库', text: '从知识库里总结与我当前问题最相关的三条运维经验。' },
  { label: '解释告警', text: '解释一下当前活跃告警的可能原因和处置建议。' }
]

/** 七状态映射：whale 状态 → personaStates profile key */
const personaState = computed(() => {
  const whale = companion.states.whale
  if (whale === 'DEGRADED') return 'warning'
  if (whale === 'CRITICAL') return 'error'
  if (whale === 'UNKNOWN') return 'idle'
  return 'idle'
})

const STATE_LABELS = {
  idle: '待机',
  thinking: '思考中',
  executing: '执行中',
  observing: '观察',
  warning: '告警',
  error: '故障',
  recovering: '恢复中'
}
const personaStateLabel = computed(() => STATE_LABELS[personaState.value] ?? '待机')

const bubbleText = computed(() => {
  const alerts = companion.contextSnapshot?.activeFault?.title
  switch (personaState.value) {
    case 'warning': return alerts ? `有活跃告警：${alerts.slice(0, 30)}` : '注意：需要你关注'
    case 'error': return '故障正在排查中'
    default: return '你好，今天想让我做什么？'
  }
})

// 就地展示当前会话最近 12 条消息（含进行中的流式回答），不跳转。
const visibleMessages = computed(() => aiChat.messages.slice(-12))

/** RAG 知识条目数 — 读 localStorage 缓存 + mock 兜底（真实接入后替换） */
const ragTotal = ref(0)

/** Agent 训练统计 — mock，真实接入后替换成 modelGovernance 接口 */
const agentStats = ref({ conversations: 156, skills: 8, lastFineTune: '3 天前' })

/** 演示模式：手动 cycle 状态（点击状态 pill 触发） */
const DEMO_STATE_ORDER = ['idle', 'thinking', 'observing', 'executing', 'warning', 'error', 'recovering']
const demoIdx = ref(0)
function cycleDemoState() {
  demoIdx.value = (demoIdx.value + 1) % DEMO_STATE_ORDER.length
  const next = DEMO_STATE_ORDER[demoIdx.value]
  personaRef.value?.setState?.(next, { fade: 350 })
  personaRef.value?.speakText?.(STATE_LABELS[next] ?? next)
}

/** 点击 3D 舞台让小鱼开口说话 */
const GREETINGS = {
  idle: ['你好，今天想让我做什么？', '系统一切正常，随时待命。', '嗨，有什么可以帮你的？'],
  warning: ['有活跃告警，我来帮你看看。', '注意：需要你关注。', '我注意到了一些异常。'],
  error: ['故障正在排查中。', '我正在定位问题。', '需要协助吗？'],
  observing: ['正在观察系统运行。', '巡检进行中。', '一切看起来还好。'],
  thinking: ['嗯，让我想想。', '正在分析…', '稍等。'],
  executing: ['执行中，请稍等。', '正在处理。', '马上就好。'],
  recovering: ['恢复中…', '快好了。', '正在清理现场。']
}
function speakGreeting() {
  const pool = GREETINGS[personaState.value] ?? GREETINGS.idle
  const text = pool[Math.floor(Math.random() * pool.length)]
  personaRef.value?.speakText?.(text)
}

async function loadRag() {
  try {
    const raw = localStorage.getItem('smartops_rag_stats')
    if (raw) {
      const data = JSON.parse(raw)
      ragTotal.value = Number(data.total) || 0
      return
    }
  } catch {}
  ragTotal.value = 284 // mock fallback
}

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })
}

async function addFiles(files) {
  const list = Array.from(files || [])
  for (const file of list) {
    if (staged.value.length >= MAX_IMAGES) { aiChat.validationError = '一次最多附加 5 张图片。'; break }
    if (!/^image\/(png|jpe?g)$/i.test(file.type)) { aiChat.validationError = '仅支持 PNG / JPEG 图片。'; continue }
    if (!file.size || file.size > MAX_BYTES) { aiChat.validationError = '单张图片不能超过 10 MB。'; continue }
    if (staged.value.reduce((sum, item) => sum + item.size, file.size) > TOTAL_BYTES) { aiChat.validationError = '图片合计不能超过 20 MB。'; break }
    try {
      const dataUrl = await readAsDataUrl(file)
      staged.value.push({ id: crypto.randomUUID(), name: file.name, preview: URL.createObjectURL(file), dataUrl, size: file.size })
    } catch (error) {
      aiChat.validationError = error.message || '图片读取失败'
    }
  }
}

function onPick(event) {
  addFiles(event.target.files)
  event.target.value = ''
}
function onPaste(event) {
  const files = Array.from(event.clipboardData?.files || [])
  const images = files.filter(file => /^image\//i.test(file.type))
  if (images.length) { event.preventDefault(); addFiles(images) }
}
function removeImage(id) {
  const item = staged.value.find(value => value.id === id)
  if (item?.preview) URL.revokeObjectURL(item.preview)
  staged.value = staged.value.filter(value => value.id !== id)
}
function fillQuick(prompt) {
  input.value = prompt.text
  input.value && nextTick(() => threadRef.value?.scrollTo?.(0, threadRef.value.scrollHeight))
}
function clearStaged() {
  for (const item of staged.value) if (item.preview) URL.revokeObjectURL(item.preview)
  staged.value = []
}

// 发送后对话就地显示，不再 router.push('/chat')。
async function onSend() {
  const text = input.value.trim()
  const images = [...staged.value]
  if ((!text && !images.length) || sending.value) return
  input.value = ''
  clearStaged()
  try {
    // 带图走流式多模态链路（ai-service → 视觉模型）；纯文本也走同一链路便于就地流式显示。
    await aiChat.sendMessageStreaming(text, {
      images: images.map(item => item.name),
      imageData: images.map(item => item.dataUrl)
    })
    personaRef.value?.speakText?.('已收到，我来分析一下。')
    await nextTick()
    threadRef.value?.scrollTo?.(0, threadRef.value.scrollHeight)
  } catch {
    // store 内部已把错误写入消息，这里不重复提示。
  }
}

/** 让小鱼随状态切换姿态 */
watch(personaState, (state) => {
  personaRef.value?.setState?.(state, { fade: 350 })
})

onMounted(() => {
  loadRag()
  // #perf: 首屏出完再加载 3D 化身——用 requestIdleCallback 趁主线程空闲时懒加载，
  // 同时保证静态封面至少显示 500ms，确保它真的出现在 FCP/LCP 之前
  const MIN_PLACEHOLDER_MS = 500
  const mountedAt = performance.now()
  const trigger = () => {
    const remaining = MIN_PLACEHOLDER_MS - (performance.now() - mountedAt)
    if (remaining > 0) setTimeout(() => { personaLoaded.value = true }, remaining)
    else personaLoaded.value = true
  }
  if ('requestIdleCallback' in window) window.requestIdleCallback(trigger, { timeout: 3000 })
  else setTimeout(trigger, 1000)
})
onBeforeUnmount(() => {
  clearStaged()
  personaRef.value?.dispose?.()
})
</script>

<style scoped>
.xiaoyu-card {
  display: grid;
  gap: 12px;
}

.xiaoyu-body {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

/* 3D 半身舞台 */
.xiaoyu-stage {
  display: block;
  cursor: pointer;
  outline: none;
  aspect-ratio: 9 / 12;
  border-radius: var(--ds-radius-md);
  overflow: hidden;
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .18), transparent 62%),
    var(--ds-color-surface-base);
  position: relative;
  isolation: isolate;
  transition: box-shadow var(--ds-duration-micro) var(--ds-ease-out),
              transform var(--ds-duration-micro) var(--ds-ease-out);
}
.xiaoyu-stage:hover {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ds-color-primary) 40%, transparent);
}
.xiaoyu-stage:active { transform: scale(.98); }
.xiaoyu-stage :deep(.persona) {
  padding: 0;
  border: none;
  background: none;
  transform: translateY(-6%);
}
.xiaoyu-stage :deep(.webgl-host) { max-width: none; }

/* #perf: 3D 加载前的 CSS 静态封面占位——避免首屏阻塞但不丢视觉存在感 */
.xiaoyu-stage-placeholder {
  width: 100%; height: 100%;
  display: grid; place-content: center;
  background:
    radial-gradient(120% 90% at 50% 85%, rgba(36, 150, 237, .22), transparent 64%),
    linear-gradient(180deg, rgba(36, 150, 237, .08), transparent 40%),
    var(--ds-color-surface-base);
}
.xiaoyu-placeholder-silhouette {
  width: 72%; aspect-ratio: 3 / 4;
  border-radius: 50% 50% 45% 45% / 55% 55% 45% 45%;
  background: linear-gradient(180deg, rgba(36, 150, 237, .38), rgba(36, 150, 237, .12));
  box-shadow: 0 20px 50px rgba(0, 0, 0, .35), inset 0 -20px 40px rgba(36, 150, 237, .22);
  animation: xiaoyu-pulse 2.8s ease-in-out infinite;
}
@keyframes xiaoyu-pulse {
  0%, 100% { transform: scale(1); opacity: .92; }
  50%      { transform: scale(1.04); opacity: 1; }
}

/* 状态气泡：浮动在 3D 场景内（脚下光环上方），玻璃质感 */
.xiaoyu-bubble {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  width: max-content;
  max-width: 92%;
  margin: 0;
  padding: 8px 14px;
  border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-color-surface-base) 72%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  color: var(--ds-color-text);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  border: 1px solid color-mix(in srgb, var(--ds-color-primary) 30%, transparent);
  box-shadow: 0 6px 18px rgba(0, 0, 0, .28);
  pointer-events: none;
}

/* 就地对话流 */
.xiaoyu-thread {
  max-height: 240px;
  overflow-y: auto;
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
  padding: 10px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-md);
  background: color-mix(in srgb, var(--ds-color-text) 2%, transparent);
  scrollbar-width: thin;
}
.xiaoyu-msg { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 8px; align-items: start; }
.xiaoyu-msg-role {
  font: 9.5px/1.6 var(--ds-font-mono);
  letter-spacing: .06em;
  color: var(--ds-color-muted);
  text-transform: uppercase;
  padding-top: 2px;
}
.xiaoyu-msg--assistant .xiaoyu-msg-role { color: var(--ds-color-primary); }
.xiaoyu-msg-body { min-width: 0; }
.xiaoyu-msg-text {
  display: block;
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.xiaoyu-msg-error { display: block; font-size: 11px; color: var(--smart-danger); overflow-wrap: anywhere; }
.xiaoyu-msg-images { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.xiaoyu-msg-images img {
  width: 52px; height: 52px; object-fit: cover;
  border: 1px solid var(--ds-hairline); border-radius: var(--ds-radius-sm);
}

/* 待发送图片 tray */
.xiaoyu-tray { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.xiaoyu-tray-item { position: relative; width: 46px; height: 46px; }
.xiaoyu-tray-item img { width: 46px; height: 46px; object-fit: cover; border-radius: var(--ds-radius-sm); border: 1px solid var(--ds-color-primary); }
.xiaoyu-tray-item button {
  position: absolute; top: -5px; right: -5px; width: 18px; height: 18px; line-height: 16px;
  border-radius: 50%; border: 1px solid var(--ds-hairline); background: var(--ds-color-surface-raised);
  color: var(--ds-color-text); font-size: 12px; cursor: pointer; padding: 0;
}

/* 快捷对话 */
.xiaoyu-input {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 6px;
  margin-bottom: 10px;
}
.xiaoyu-file { display: none; }
.xiaoyu-attach {
  padding: 0 8px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-md);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11px;
  cursor: pointer;
}
.xiaoyu-attach:hover { border-color: var(--ds-color-primary); color: var(--ds-color-primary); }
.xiaoyu-input textarea {
  resize: none;
  padding: 8px 10px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-base);
  color: var(--ds-color-text);
  font-size: var(--ds-type-body-caption-size);
  line-height: var(--ds-line-height-base);
  font-family: inherit;
}
.xiaoyu-input textarea:focus {
  outline: none;
  border-color: var(--ds-color-primary);
}
.xiaoyu-send {
  padding: 0 14px;
  border: 1px solid var(--ds-color-primary);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-primary);
  color: var(--smart-primary-foreground);
  font-size: var(--ds-type-caption-size);
  font-weight: 500;
  cursor: pointer;
}
.xiaoyu-send:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* 3 个快捷按钮 */
.xiaoyu-quicks {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 12px;
}
.xiaoyu-quick {
  padding: 7px 10px;
  border: 1px solid var(--ds-hairline);
  border-radius: var(--ds-radius-sm);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              color var(--ds-duration-micro) var(--ds-ease-out),
              background var(--ds-duration-micro) var(--ds-ease-out);
}
.xiaoyu-quick:hover {
  border-color: var(--ds-color-primary);
  color: var(--ds-color-primary);
  background: color-mix(in srgb, var(--ds-color-primary) 6%, transparent);
}

/* 指标行 */
.xiaoyu-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--ds-hairline);
}
.xiaoyu-metric {
  display: grid;
  gap: 2px;
  padding: 6px 8px;
  border-radius: var(--ds-radius-sm);
  background: color-mix(in srgb, var(--ds-color-text) 3%, transparent);
  border: 1px solid transparent;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              background var(--ds-duration-micro) var(--ds-ease-out);
  font: inherit;
}
.xiaoyu-metric:hover {
  border-color: var(--ds-color-primary);
  background: color-mix(in srgb, var(--ds-color-primary) 8%, transparent);
}
.xiaoyu-metric-label {
  font: 9px/1 var(--ds-font-mono);
  color: var(--ds-color-muted);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.xiaoyu-metric strong {
  font-size: var(--ds-type-body-size);
  font-weight: 600;
  color: var(--ds-color-text);
}
.xiaoyu-metric-hint {
  font-size: 10.5px;
  color: var(--ds-color-muted);
}

.xiaoyu-state-pill {
  padding: 3px 10px;
  font: 9.5px var(--ds-font-mono);
  letter-spacing: .1em;
  text-transform: uppercase;
  border-radius: var(--ds-radius-pill);
  background: var(--ds-pill-info-bg);
  color: var(--ds-color-primary);
}
.xiaoyu-state-pill[data-state="warning"] { background: color-mix(in srgb, var(--smart-warning) 16%, transparent); color: var(--smart-warning); }
.xiaoyu-state-pill[data-state="error"]    { background: color-mix(in srgb, var(--smart-danger) 16%, transparent); color: var(--smart-danger); }
.xiaoyu-state-pill[data-state="recovering"] { background: color-mix(in srgb, var(--smart-success) 16%, transparent); color: var(--smart-success); }

@media (max-width: 1024px) {
  .xiaoyu-body { grid-template-columns: 140px minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .xiaoyu-body { grid-template-columns: 1fr; }
  .xiaoyu-stage { aspect-ratio: 9 / 16; max-width: 140px; margin: 0 auto; }
}
</style>
