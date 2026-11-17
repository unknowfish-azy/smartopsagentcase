<template>
  <aside
    ref="host"
    class="persona-pet"
    :class="{ 'persona-pet--collapsed': store.collapsed, 'persona-pet--dragging': dragging }"
    :style="[positionStyle, petSizeStyle]"
    aria-label="小鱼桌宠"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @lostpointercapture="onPointerUp"
  >
    <template v-if="!store.collapsed">
      <header class="persona-pet__bar" aria-label="小鱼桌宠控制条">
        <span class="persona-pet__title">小鱼</span>
        <span class="persona-pet__bar-actions">
          <button
            type="button"
            class="persona-pet__mini"
            :aria-label="`缩放悬浮窗（当前：${sizeLabel}，点击切换档位）`"
            :title="`缩放悬浮窗（当前：${sizeLabel}，点击在 紧凑/标准/放大 间切换）`"
            @click.stop="store.cycleSize(currentViewport)"
          >⤢</button>
          <button
            type="button"
            class="persona-pet__mini persona-pet__mini--icon"
            :class="{ 'persona-pet__mini--muted': audioMuted }"
            :aria-pressed="!audioMuted"
            :aria-label="audioButtonLabel"
            :title="audioButtonLabel"
            @click.stop="toggleAudioMuted"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path class="spk-body" d="M4.2 9.4h3.3L12 5.4v13.2L7.5 14.6H4.2z" />
              <g v-if="!audioMuted" class="spk-wave">
                <path d="M15.1 9.1a4.4 4.4 0 0 1 0 5.8" />
                <path d="M17.7 6.6a8 8 0 0 1 0 10.8" />
              </g>
              <g v-else class="spk-mute">
                <path d="M15.4 9.6l5 4.8" />
                <path d="M20.4 9.6l-5 4.8" />
              </g>
            </svg>
          </button>
          <button
            type="button"
            class="persona-pet__mini"
            :disabled="!voiceSupported"
            :aria-label="voiceButtonLabel"
            :title="voiceButtonLabel"
            @click.stop="onVoiceCommand"
          >{{ voiceMode === 'listening' ? '停' : '听' }}</button>
          <button type="button" class="persona-pet__mini" :aria-label="'问助手打个招呼（播报中点击会先打断当前播报）'" title="问助手打个招呼（播报中点击会先打断）" @click.stop="speakGreeting">说</button>
          <button
            type="button"
            class="persona-pet__mini"
            :aria-pressed="store.speechFallback"
            :aria-label="store.speechFallback ? '浏览器音色兜底：开（神经语音不可用时改用浏览器音色）' : '浏览器音色兜底：关（神经语音不可用时保持无声，不换音色）'"
            :title="store.speechFallback ? '浏览器音色兜底：开（点击改为宁可无声，不换音色）' : '浏览器音色兜底：关（点击改为神经语音不可用时用浏览器音色念）'"
            @click.stop="store.setSpeechFallback(!store.speechFallback)"
          >兜</button>
          <button type="button" class="persona-pet__mini" aria-label="打开小鱼全页" title="全页模式" @click.stop="openFullPage">↗</button>
          <button type="button" class="persona-pet__mini" aria-label="收起小鱼" title="收起" @click.stop="store.setCollapsed(true, currentViewport)">—</button>
          <button type="button" class="persona-pet__mini" aria-label="关闭小鱼" title="关闭" @click.stop="store.disable()">×</button>
        </span>
      </header>
      <div
        class="persona-pet__stage"
        @click="onStageClick"
        @pointerdown="onStagePointerDown"
        @pointermove="onStagePointerMove"
        @pointerup="onStagePointerUp"
        @pointercancel="onStagePointerUp"
        @pointerleave="onStagePointerLeave"
      >
        <AgentPersona ref="personaRef" mode="vrm" :state="agentState" @ready="onReady" />
        <transition name="pet-bubble">
          <span v-if="reaction && !faultAlert" class="persona-pet__bubble" :key="reactionKey">{{ reaction }}</span>
        </transition>
        <transition name="pet-bubble">
          <button
            v-if="faultAlert"
            :key="faultAlert.id"
            type="button"
            class="persona-pet__bubble"
            :class="{ 'persona-pet__bubble--alert': faultAlert.critical }"
            :title="faultAlert.critical ? '高危异常，点击打开处置面板' : '点击打开处置面板'"
            @click.stop="openFaultAlert"
          >{{ faultAlert.text }} · 点我查看</button>
        </transition>
      </div>
      <p class="persona-pet__note" aria-live="polite">
        {{ noteLabel }}
        <span class="persona-pet__note-hint">{{ noteHint }}</span>
      </p>
      <button
        type="button"
        class="persona-pet__grip"
        :aria-label="`调整悬浮窗大小（当前：${sizeLabel}，点击切换档位，也可拖动缩放）`"
        :title="`点击切换大小（当前：${sizeLabel}），也可拖动右下角缩放`"
        @click.stop
        @pointerdown="onGripPointerDown"
        @pointermove="onGripPointerMove"
        @pointerup="onGripPointerUp"
        @pointercancel="onGripPointerUp"
        @lostpointercapture="onGripPointerUp"
      >
        <svg viewBox="0 0 12 12" aria-hidden="true" focusable="false">
          <path d="M4.2 10.4L10.4 4.2M7.2 4.2h3.2v3.2" />
        </svg>
      </button>
    </template>
    <button
      v-else
      type="button"
      class="persona-pet__orb"
      :class="{ 'persona-pet__orb--fault': faultAlert }"
      :aria-label="`展开小鱼，当前状态：${agentStateLabel}${faultAlert ? '，有待查看的异常' : ''}`"
      :title="`小鱼（${agentStateLabel}${faultAlert ? ' · 有待查看的异常' : ''}）· 点击展开`"
      @click.stop="store.setCollapsed(false, currentViewport)"
    />
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AgentPersona from './AgentPersona.vue'
import { createPetSpeech, isSpeechSynthesisAvailable } from './petSpeech.js'
import { createPetNeuralTts } from './petNeuralTts.js'
import { hasCoarseRun } from './useLipSync.js'
import { fetchTtsStatus, synthesizeSpeech, synthesizeSpeechWithTiming } from '../../api/tts.ts'
import { askAssistant, createVoiceInput, isVoiceInputAvailable } from './personaVoice.js'
import { resolveNavigationIntent, hazardBubble, isHazardRoute } from './voiceCommandRegistry.js'
import {
  HAZARD_LEVELS,
  actionBlockedBubble,
  actionConfirmBubble,
  actionExecuteBubble,
  resolveVoiceActionIntent,
  useVoiceActionBus,
} from './voiceActionRegistry.js'
import { createClickClassifier, createIdleScheduler, LONG_PRESS_MS } from './personaInteractions.js'
import { createFaultNotifier } from './personaFaultNotify.js'
import { gestureVoice } from './personaGestures.js'
import { PERSONA_PET_ASPECT, PERSONA_PET_INSET, resolvePetSize, usePersonaPetStore } from '../../stores/personaPet.js'
import { useCompanionStore } from '../../stores/companion.js'

const GREETING = '正在检查集群节点健康状态，发现两个副本延迟偏高，准备滚动重启。'

const store = usePersonaPetStore()
const companion = useCompanionStore()
const router = useRouter()
const voiceActionBus = useVoiceActionBus()

// 按钮级意图的二次确认：第一次命中 high/medium 危险等级时，先播报确认提示，
// 把 actionId 暂存；第二次再说就真正 dispatch。critical 永远拦截，不进这里。
const pendingActionConfirm = ref(null)  // { actionId, label, hazard, expiresAt }

const host = ref(null)
const personaRef = ref(null)
const dragging = ref(false)
const speaking = ref(false)
const ready = ref(false)
const speechSupported = isSpeechSynthesisAvailable()
const voiceSupported = isVoiceInputAvailable()

/* 神经语音真实可用时的引擎名（后端 provider 的 display_name）；空串 = 正在用浏览器语音 */
const ttsEngine = ref('')

/* 语音闭环：listening（听）→ thinking（问 AI）→ speaking（答+播报）→ idle */
const voiceMode = ref('idle')
const heard = ref('')
const boundarySeen = ref(false)

/* 当前口型驱动来源，如实标注三档：
   phoneme=音素级（服务端给了真实韵母）/ timeline=词/字级时间戳 / text=按字数匀速近似 */
const lipAlign = ref('text')

const LISTEN_ERRORS = {
  unsupported: '当前浏览器不支持语音识别，请使用 Chrome 或 Edge',
  timeout: '没有听到说话，再试一次？',
  'no-speech': '没有听到说话，再试一次？',
  'not-allowed': '麦克风权限被拒绝，请在浏览器设置里允许',
  'service-not-allowed': '语音识别服务不可用',
  'no-result': '没能识别出内容，再试一次？',
  'network': '语音识别网络异常，请检查连接',
  aborted: '聆听被打断了',
  'aborted-by-user': '已停止聆听'
}

/* 聆听失败的肢体反馈：没听清→扶额；权限/服务不可用→无奈耸肩；主动停止不做动作 */
const LISTEN_ERROR_GESTURES = {
  unsupported: 'shrug',
  'not-allowed': 'shrug',
  'service-not-allowed': 'shrug',
  network: 'shrug',
  timeout: 'facepalm',
  'no-speech': 'facepalm',
  'no-result': 'facepalm',
  aborted: 'facepalm'
}

const voiceButtonLabel = computed(() => {
  if (voiceMode.value === 'listening') return '停止聆听'
  // 播报/思考中不再禁用，而是"随时可以插话"（豆包式 barge-in）
  if (voiceMode.value === 'thinking') return '正在询问平台助手，点一下可打断并重说'
  if (voiceMode.value === 'speaking' || speaking.value) return '正在播报，点一下可打断并说话'
  return voiceSupported ? '说一句话，我来回答（语音识别）' : '当前浏览器不支持语音识别'
})

const noteLabel = computed(() => {
  if (voiceMode.value === 'listening') return '聆听中，请说出你的问题…'
  if (voiceMode.value === 'thinking') return `已收到「${heard.value}」，正在询问平台助手…`
  if (voiceMode.value === 'speaking' || speaking.value) {
    return ttsEngine.value ? `语音播报中（${ttsEngine.value}）` : '语音播报中'
  }
  if (!speechSupported) return '当前浏览器不支持语音播报，仅文字近似口型'
  return ready.value ? '静默' : '加载中'
})

const noteHint = computed(() => {
  // 播报中给一句"可以打断"的提示：这是新交互的发现性入口
  if (speaking.value || voiceMode.value === 'speaking') {
    if (ttsEngine.value) {
      if (lipAlign.value === 'phoneme') {
        // 字母数字串在 piper-plus 里只能整串对齐：如实说明，不把它说成逐字音素
        return hasCoarseRun(neuralTts.lastTiming)
          ? '神经语音 · 按「听」或点我即可打断（口型按音素级对齐，字母数字为整串近似）'
          : '神经语音 · 按「听」或点我即可打断（口型按音素级时间戳对齐）'
      }
      if (lipAlign.value === 'timeline') {
        return '神经语音 · 按「听」或点我即可打断（口型按词级时间戳对齐）'
      }
      return '神经语音 · 按「听」或点我即可打断（口型为近似同步）'
    }
    if (boundarySeen.value) return '按「听」或点我即可打断 · 口型已按词边界校正'
    return '按「听」或点我即可打断（口型为近似同步）'
  }
  return '口型为近似同步，非音素级'
})

/* D1：点击反应气泡 */
const REACTIONS = [
  '在的～', '我看看…', '嗯？', '收到！', '让我想想…',
  '没问题', '稍等', '好的', '明白', '正在处理…'
]
const reaction = ref('')
const reactionKey = ref(0)
let reactionTimer = null

function showReaction(text, holdMs = 2200) {
  reaction.value = text
  reactionKey.value++
  if (reactionTimer) clearTimeout(reactionTimer)
  if (holdMs > 0) reactionTimer = setTimeout(() => { reaction.value = '' }, holdMs)
}

/* ------------------------------------------------------------
   告警主动通知（P1-3）：订阅 companion 的 FAULT_DETECTED 事件——
   视觉回传 / 哨兵 / 任意页面 ingestFault 都会走到这里。
   决策逻辑（去重/节流/分级/出声守卫）在 personaFaultNotify.js 纯逻辑层，
   本组件只负责把展示与语音注入进去；决策依据在测试里锁定。
   ------------------------------------------------------------ */
const faultAlert = ref(null)
let faultUnsubscribe = null

const faultNotifier = createFaultNotifier({
  showAlert: (alert) => { faultAlert.value = alert },
  clearAlert: () => { faultAlert.value = null },
  playGesture: (name) => personaRef.value?.playGesture?.(name),
  // 工厂已做"高危 + 空闲 + 非静音"守卫；speakNeuralOnly 的静音守卫是双保险
  speak: (text) => { speakNeuralOnly(text) }
}, {
  isBusy: () => speaking.value || voiceMode.value === 'speaking',
  isMuted: () => audioMuted.value
})

/** 点气泡 → 打开处置抽屉（companion.openInvestigation 的正式入口） */
function openFaultAlert() {
  faultNotifier.dismiss()
  faultAlert.value = null
  companion.openInvestigation()
}

/* 声音开关（听筒图标）：关闭后神经语音与浏览器语音都不出声，
   气泡、动作与口型照常，避免"关了声音还在动嘴却没声音"的困惑 */
const AUDIO_MUTED_KEY = 'smartops.persona.audioMuted'
const audioMuted = ref(readAudioMuted())

function readAudioMuted() {
  try {
    return window.localStorage.getItem(AUDIO_MUTED_KEY) === '1'
  } catch {
    return false
  }
}

function toggleAudioMuted() {
  audioMuted.value = !audioMuted.value
  try {
    window.localStorage.setItem(AUDIO_MUTED_KEY, audioMuted.value ? '1' : '0')
  } catch {
    // 隐私模式下写不了本地存储：音量开关只在本次会话生效
  }
  if (!audioMuted.value) return
  // 关闭的瞬间就要真的安静下来：在途的神经音频与浏览器语音一起停
  neuralTts.stop()
  petSpeech.stop?.()
  if (speaking.value || voiceMode.value === 'speaking') stopSpeech()
}

const audioButtonLabel = computed(() => (
  audioMuted.value ? '声音已关闭，点击开启声音播报' : '声音已开启，点击关闭声音'
))

/* ============================================================
   厘米秀式互动（2026-11-16）：只蒸馏交互范式，不引入任何外部资产。
   单击=随机反应+挥手；双击=大笑；连击≥4（戳）=抗议摇头；长按=歪头疑惑；
   挂机 90s 伸懒腰 → 再 90s 打瞌睡循环，任意交互/语音唤醒并致意。
   点击分级与挂机时间轴是纯逻辑（personaInteractions.js），本组件只做播放接线。
   ============================================================ */

const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false

function canPlayIdle() {
  return ready.value && !store.collapsed && !document.hidden && !prefersReducedMotion
    && !speaking.value && voiceMode.value === 'idle'
}

/* 单击手势随机化（厘米秀式反应多样性）：挥手为主，其余覆盖问候、情绪、名片展示、战术手语，
   全部 34 个手势的台词都有机会被听到（此前 bow/deepBow/point/shy/lookAround/shake 无触发入口） */
const SINGLE_GESTURES = [
  'wave', 'wave', 'wave', 'cheer', 'applaud', 'salute', 'heart', 'thumbUp', 'sway', 'snap',
  'openArms', 'handOnHip', 'pointUp', 'armsCrossed',
  'bow', 'deepBow', 'point', 'shy', 'lookAround', 'shake'
]

/**
 * 统一发声入口：优先神经语音（后端 provider 自动挑选音源，音色统一），
 * 后端不可用/合成失败/自动播放被拦时回落浏览器 speechSynthesis。
 * 两条链路天然互斥：只有神经语音没能开始时才会走浏览器语音（此时没有神经音频在播），
 * 因此不需要额外 cancel，避免 speechSynthesis 的 onend 回调误伤刚起步的神经音频。
 * @param {string} text
 * @param {() => boolean} [isCurrent] 该次请求是否仍然有效；失效则不再重试（避免旧台词抢走新台词的播放）
 * @returns {Promise<boolean>} 是否有声音真的开始播放
 */
async function speakLine(text, isCurrent = () => true) {
  if (audioMuted.value) return false
  if (await neuralTts.speak(text)) return true
  if (!isCurrent()) return false
  // 偶发失败（合成超时、自动播放被拦）重试一次，避免同一句台词突然换成浏览器音色
  if (await neuralTts.speak(text)) return true
  // 兜底开关关闭（默认）时宁可无声，也不跳浏览器机械音
  return store.speechFallback && speechSupported && petSpeech.speak(text)
}

/* 手势口播代际：新的一句开始后，旧句的合成结果不得再重试、也不得再驱动口型，
   否则用户在合成等待期间再点一下，旧台词会抢在新台词之后播出来 */
let gestureToken = 0

/**
 * 手势口播：念出 PERSONA_GESTURE_VOICES 里对应的短句（不置 speaking）。
 * 不置 speaking 的原因：桌宠被点一下就被锁 2 秒交互体验很差；
 * 但正在播报 AI 回答时必须静默，防止盖掉用户真正要听的内容。
 */
async function sayGestureLine(name, { allowFallback = true } = {}) {
  if (audioMuted.value || speaking.value) return false
  const line = gestureVoice(name)
  if (!line) return false
  const token = ++gestureToken
  boundarySeen.value = false
  const isCurrent = () => token === gestureToken && !audioMuted.value && !speaking.value
  const started = allowFallback ? await speakLine(line, isCurrent) : await speakNeuralOnly(line, isCurrent)
  // 声音真正开始后才驱动口型，避免合成等待期间出现"无声动嘴"
  if (!started || !isCurrent()) return false
  driveLipSync(line)
  return true
}

/**
 * 只走神经语音（失败重试一次，绝不回落浏览器音色）。
 * 用于挂机氛围台词：换音色比没声音更违和，宁可不念也不跳音色。
 */
async function speakNeuralOnly(text, isCurrent = () => true) {
  if (audioMuted.value) return false
  if (await neuralTts.speak(text)) return true
  if (!isCurrent()) return false
  return neuralTts.speak(text)
}

/** 播手势 + 气泡 + 口播（口播不可用时自动退化为「动作 + 气泡」） */
function playGestureWithVoice(name, bubble, { allowFallback = true } = {}) {
  personaRef.value?.playGesture?.(name)
  if (bubble) showReaction(bubble)
  sayGestureLine(name, { allowFallback })
}

const clickClassifier = createClickClassifier({
  onSingle: () => {
    const gesture = SINGLE_GESTURES[Math.floor(Math.random() * SINGLE_GESTURES.length)]
    playGestureWithVoice(gesture, REACTIONS[Math.floor(Math.random() * REACTIONS.length)])
  },
  onDouble: () => {
    playGestureWithVoice('laugh', '哈哈～')
  },
  onPoke: () => {
    playGestureWithVoice('angry', '别戳啦！')
  }
})

const idleScheduler = createIdleScheduler({
  onStretch: () => {
    if (!canPlayIdle()) return
    // 挂机台词不接受浏览器音色：神经语音失败就只做动作+气泡，不跳音色
    playGestureWithVoice('stretch', '伸个懒腰～', { allowFallback: false })
  },
  onSleep: () => {
    if (!canPlayIdle()) return
    playGestureWithVoice('sleep', 'Zzz…', { allowFallback: false })
  }
})

/** 从瞌睡中醒来：清挂机计时，用「致意」代替常规点击动作（厘米秀式唤醒） */
function wakeIdle(greetWhenSleepy = false) {
  const wasSleepy = greetWhenSleepy && idleScheduler.stage >= 2
  idleScheduler.reset()
  return wasSleepy
}

/* 长按判定：stage 按下超过 LONG_PRESS_MS 且未移动 = 疑惑歪头 */
const press = { timer: null, fired: false, x: 0, y: 0 }

function cancelPress() {
  if (press.timer) {
    clearTimeout(press.timer)
    press.timer = null
  }
}

function onStagePointerDown(event) {
  // 点画面本身也是主动交互：先回正，再进入这次点击的手势/长按判定
  personaRef.value?.setLookPoint?.(null)
  if (speaking.value || voiceMode.value !== 'idle') return
  press.fired = false
  press.x = event.clientX
  press.y = event.clientY
  cancelPress()
  press.timer = setTimeout(() => {
    press.timer = null
    press.fired = true
    wakeIdle()
    playGestureWithVoice('tilt', '嗯？')
  }, LONG_PRESS_MS)
}

function onStagePointerMove(event) {
  if (press.timer && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 6) cancelPress()
  // 悬停朝向：把指针位置归一化成 [-1,1] 交给模型，头与上半身朝光标轻转
  const rect = event.currentTarget?.getBoundingClientRect?.()
  if (!rect || rect.width <= 0 || rect.height <= 0) return
  const nx = ((event.clientX - rect.left) / rect.width) * 2 - 1
  const ny = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
  personaRef.value?.setLookPoint?.(nx, ny)
}

/** 指针移出画面：回正，避免数字人一直侧着身子 */
function onStagePointerLeave() {
  personaRef.value?.setLookPoint?.(null)
}

function onStagePointerUp() {
  cancelPress()
}

function onStageClick() {
  // 播报中点击 = 打断播报（借用战术"压低手势"的语义），不再把点击吞掉
  if (speaking.value) {
    stopSpeech()
    playGestureWithVoice('signalCover', '先停一下')
    return
  }
  if (voiceMode.value !== 'idle') return
  // 长按刚触发完的抬手会带一次 click，吞掉防止重复反馈
  if (press.fired) {
    press.fired = false
    return
  }
  const wasSleepy = wakeIdle(true)
  if (wasSleepy) {
    playGestureWithVoice('greet', '哇！醒啦～')
    return
  }
  clickClassifier.feed()
}

/* 播报/语音结束回到空闲 → 重新计挂机；收起/页面隐藏 → 停表，展开/可见 → 重计 */
watch([voiceMode, speaking, () => store.collapsed], ([mode, speakingNow, collapsed]) => {
  if (collapsed) {
    idleScheduler.stop()
    clickClassifier.dispose()
    cancelPress()
    // 收起后画面不在了，指针朝向必须回正，否则再展开是侧着身子的
    personaRef.value?.setLookPoint?.(null)
    return
  }
  if (mode === 'idle' && !speakingNow) idleScheduler.reset()
})

function onVisibilityChange() {
  if (document.hidden) idleScheduler.stop()
  else if (!store.collapsed) idleScheduler.reset()
}

onMounted(() => {
  window.addEventListener('resize', updateViewport)
  document.addEventListener('visibilitychange', onVisibilityChange)
  idleScheduler.reset()
  // 订阅异常事件流：视觉回传/哨兵 ingestFault → FAULT_DETECTED → 小鱼示警
  faultUnsubscribe = companion.subscribe('FAULT_DETECTED', (event) => {
    faultNotifier.handleFault(event?.payload?.faultEvent)
  })
  // 探测后端神经语音：可用则记录引擎名（UI 如实展示），不可用则静默走浏览器语音
  neuralTts.probe().then((status) => {
    if (!status?.available || !status.provider) return
    const display = status.providers?.find((item) => item.name === status.provider)?.display_name
    ttsEngine.value = display || status.provider
  })
})

const viewport = reactive({ width: window.innerWidth, height: window.innerHeight })
const currentViewport = computed(() => ({ viewportWidth: viewport.width, viewportHeight: viewport.height }))
const drag = { pointerId: null, startX: 0, startY: 0, lastX: 0, lastY: 0, originX: 0, originY: 0, moved: false }
const positionStyle = computed(() => ({
  transform: `translate(${store.position.x}px, ${store.position.y}px)`
}))

/* 缩放档位（2026-11-16）：改真实布局尺寸，canvas 由 ResizeObserver 跟随，不用 CSS scale 防模糊。
   2026-11-16 追加：尺寸经 resolvePetSize 随视口自适应收敛——小屏不溢出、大屏保持设计基准 */
const SIZE_LABELS = { compact: '紧凑', regular: '标准', large: '放大' }
const currentSize = computed(() => resolvePetSize(store.sizeMode, currentViewport.value, store.customSize))
const sizeLabel = computed(() => (
  store.customSize
    ? `自定义 ${currentSize.value.width}×${currentSize.value.height}`
    : SIZE_LABELS[store.sizeMode] ?? '标准'
))
const petSizeStyle = computed(() => {
  if (store.collapsed) return {}
  const { width, height } = currentSize.value
  return {
    '--persona-pet-w': `${width}px`,
    '--persona-pet-h': `${height}px`
  }
})

/* 右下角缩放手柄（2026-11-17）：用户圈出的位置。
   单击 = 切换档位（标准 → 放大 → 紧凑），拖动 = 按像素自由缩放（高度驱动、2:3 比例）。
   指针捕获必须落在手柄自己身上——捕获到 aside 后手柄就收不到 pointermove 了。 */
const resize = { pointerId: null, startX: 0, startY: 0, startHeight: 0, moved: false }

function onGripPointerDown(event) {
  if (event.button !== 0) return
  event.stopPropagation()
  event.preventDefault()
  resize.pointerId = event.pointerId
  resize.startX = event.clientX
  resize.startY = event.clientY
  resize.startHeight = currentSize.value.height
  resize.moved = false
  event.currentTarget?.setPointerCapture?.(event.pointerId)
}

function onGripPointerMove(event) {
  if (resize.pointerId !== event.pointerId) return
  const deltaX = event.clientX - resize.startX
  const deltaY = event.clientY - resize.startY
  if (!resize.moved && Math.hypot(deltaX, deltaY) < 4) return
  resize.moved = true
  // 横向拖 1px 等价于纵向 1.5px（2:3），斜着拖更跟手；宽度由 store 按比例回算
  const targetHeight = resize.startHeight + Math.max(deltaY, deltaX / PERSONA_PET_ASPECT)
  store.applyCustomSize({ height: targetHeight }, currentViewport.value)
}

function onGripPointerUp(event) {
  if (resize.pointerId !== event.pointerId) return
  const moved = resize.moved
  resize.pointerId = null
  resize.moved = false
  event.currentTarget?.releasePointerCapture?.(event.pointerId)
  if (moved) {
    store.setCustomSize(store.customSize, currentViewport.value)
    return
  }
  // 没拖动 = 单击：切换档位（这就是「点一下缩小 / 再点一下扩大」）
  store.cycleSize(currentViewport.value)
}

const agentState = computed(() => {
  // 复用 7 状态枚举：聆听→观察、提问→思考，播报回待机（口型层负责说话表现）
  if (voiceMode.value === 'listening') return 'observing'
  if (voiceMode.value === 'thinking') return 'thinking'
  return companion.states.whale === 'DEGRADED' ? 'warning' : 'idle'
})
const agentStateLabel = computed(() =>
  ({ idle: '待命', observing: '聆听', thinking: '思考', warning: '注意' })[agentState.value] ?? '待命'
)

/* 平台告警出现时"一惊"：进入 warning 态播一次后仰（语音/播报期间不抢动作） */
watch(agentState, (next, prev) => {
  if (next === 'warning' && prev !== 'warning' && canPlayIdle()) {
    playGestureWithVoice('leanBack', '注意，有异常！')
    return
  }
  // 告警解除回到待命：竖拇指确认（"干得漂亮"）
  if (prev === 'warning' && next === 'idle' && canPlayIdle()) {
    playGestureWithVoice('thumbUp', '已恢复正常')
  }
})

const petSpeech = createPetSpeech({
  onBoundary: (charIndex) => {
    boundarySeen.value = true
    personaRef.value?.seekSpeech?.(charIndex)
  },
  onEnd: () => stopSpeech(),
  onError: () => stopSpeech()
})

/* 神经语音：后端真实可用才用；任何失败由 speakLine/speakReply 回落浏览器语音 */
const neuralTts = createPetNeuralTts({
  fetchStatus: fetchTtsStatus,
  synthesize: synthesizeSpeech,
  // 优先取后端词级时间戳：Edge 有 WordBoundary，本地模型没有会回空数组
  synthesizeWithTiming: synthesizeSpeechWithTiming,
  onEnd: () => stopSpeech(),
  // 播放中途出错：如实收尾，不假装仍在播报
  onError: () => stopSpeech()
})

/**
 * 神经音频已响起时驱动口型：有真实时间戳走 timeline，否则按音频时长反推 cps。
 * 来源写进 lipAlign（phoneme/timeline/text），供 noteHint 如实展示。
 */
function driveLipSync(text) {
  const timing = neuralTts.lastTiming
  if (timing.length && personaRef.value?.speakTimeline?.(text, timing)) {
    // 带 viseme 说明服务端算出了真实韵母（piper-plus 音素级）；
    // 只有边界时间戳（Edge WordBoundary）就如实降一档标注为词级
    lipAlign.value = timing.some((item) => item.viseme) ? 'phoneme' : 'timeline'
    return
  }
  lipAlign.value = 'text'
  // 神经音频没有词边界事件时，用真实时长反推 cps，口型与音频同起同止
  const seconds = neuralTts.lastDurationMs / 1000
  const cps = seconds > 0.3 ? Math.max(2, Math.min(12, text.length / seconds)) : 5
  personaRef.value?.speakText(text, { cps })
}

/* 递增令牌：合成/发起期间的旧任务在停止后不得再驱动口型或状态 */
let speechToken = 0

/* 在途提问的取消句柄：插话打断时必须让旧回答彻底失效，
   否则"打断后旧回答又把它覆盖掉"，用户会看到刚说的话被无视 */
let askController = null

function abortAsk() {
  askController?.abort?.()
  askController = null
}

/**
 * 插话打断（豆包式 barge-in）：停播报 + 取消在途提问，回到可聆听状态。
 * 之前播报/思考期间按钮是 disabled（想说话只能干等），现在任何时刻都能抢话。
 */
function interruptPlayback() {
  abortAsk()
  stopSpeech()
}

const voiceInput = createVoiceInput()

function onPointerDown(event) {
  // 点按钮（含标题栏的「说」）属于主动交互：立刻回正朝向，不保留悬停时的侧头姿态
  personaRef.value?.setLookPoint?.(null)
  // 收起小球：整颗可拖；展开态：仅标题栏把手可拖，避免劫持画布区
  if (!store.collapsed && !event.target.closest('.persona-pet__bar')) return
  if (event.button !== 0) return
  drag.pointerId = event.pointerId
  drag.startX = event.clientX
  drag.startY = event.clientY
  drag.lastX = event.clientX
  drag.lastY = event.clientY
  drag.originX = store.position.x
  drag.originY = store.position.y
  drag.moved = false
  dragging.value = true
  // 注意：这里不能立刻 setPointerCapture——捕获会把后续 click 重定向到 aside，
  // 标题栏里的按钮（⤢/听/说/↗/—/×）就再也收不到 click 了。改为拖动确认后再捕获。
}

function onPointerMove(event) {
  if (drag.pointerId !== event.pointerId) return
  const deltaX = event.clientX - drag.startX
  const deltaY = event.clientY - drag.startY
  if (!drag.moved && Math.hypot(deltaX, deltaY) < 3) return
  if (!drag.moved) {
    drag.moved = true
    // 超过位移阈值、确认在拖动后才开始捕获，保证单纯点击仍落在原目标上
    host.value?.setPointerCapture?.(event.pointerId)
  }
  store.moveBy(event.clientX - (drag.lastX ?? drag.startX), event.clientY - (drag.lastY ?? drag.startY), {
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
    inset: PERSONA_PET_INSET
  })
  drag.lastX = event.clientX
  drag.lastY = event.clientY
}

function onPointerUp(event) {
  if (drag.pointerId !== event.pointerId) return
  drag.pointerId = null
  drag.lastX = 0
  drag.lastY = 0
  dragging.value = false
  if (drag.moved) {
    store.setPosition(store.position, {
      viewportWidth: viewport.width,
      viewportHeight: viewport.height
    })
    // 被拖着走一圈、放下时"有点晕"（厘米秀式手感反馈），同时重置挂机计时
    idleScheduler.reset()
    playGestureWithVoice('shiver', '晕…晕了')
  }
}

function onReady() {
  ready.value = true
}

/**
 * 播报一段话：优先神经语音（口型按文本时间线近似推进），失败回落浏览器语音，
 * 两者都不可用时退化为纯文字口型；UI 的 noteHint 会如实标注当前引擎。
 */
function speakReply(text, gesture) {
  if (!personaRef.value || !text) return
  boundarySeen.value = false
  if (gesture) personaRef.value.playGesture?.(gesture)
  if (audioMuted.value) {
    // 静音态：只走口型时间线，不触碰任何语音引擎
    personaRef.value.speakText(text, { cps: 5 })
    if (voiceMode.value === 'speaking') voiceMode.value = 'idle'
    return
  }
  const token = ++speechToken
  speaking.value = true
  neuralTts.speak(text).then((started) => {
    if (token !== speechToken || !speaking.value) return
    if (started) {
      // 有后端词级时间戳就走 timeline；没有则按真实音频时长反推 cps，
      // 口型与音频同起同止（固定 5 字/秒在长句上会越播越不同步）
      driveLipSync(text)
      return
    }
    // 兜底开关关闭（默认）时不回落浏览器语音：直接退化为纯文字口型（无声）
    if (store.speechFallback && speechSupported && petSpeech.speak(text)) {
      lipAlign.value = 'text'
      personaRef.value?.speakText(text, { cps: 5 })
      return
    }
    // 没有任何可用语音：退化为纯文字时间线，UI 已如实标注
    lipAlign.value = 'text'
    personaRef.value?.speakText(text, { cps: 5 })
    speaking.value = false
    if (voiceMode.value === 'speaking') voiceMode.value = 'idle'
  })
}

/**
 * 「说」按钮（2026-11-16 真实对接）：向平台助手要一句真实问候并播报；
 * 助手不可用（如 run-token 未配置 / 网络离线）时退回本地固定问候，气泡如实标注。
 */
async function speakGreeting() {
  if (!personaRef.value) return
  // 播报中/思考中点「说」= 插话：先打断，再问候（不再要求先等它说完）
  if (speaking.value || voiceMode.value !== 'idle') interruptPlayback()
  voiceMode.value = 'thinking'
  heard.value = '打个招呼'
  // 托腮动作 + 台词：此前只做动作不发音，思考类手势的文案永远听不到
  playGestureWithVoice('think', '让我想一想…')
  const controller = new AbortController()
  askController = controller
  try {
    const { ok, text: reply } = await askAssistant(
      '请用一句话向用户问好，并简要说明你能帮助处理的事项，不超过 40 个字。',
      { signal: controller.signal }
    )
    if (controller.signal.aborted) return
    if (askController === controller) askController = null
    voiceMode.value = 'idle'
    if (ok && reply) {
      speakReply(reply, 'greet')
    } else {
      showReaction('助手暂时离线，先来句固定问候～')
      speakReply(GREETING, 'shrug')
    }
  } catch {
    if (controller.signal.aborted) return
    if (askController === controller) askController = null
    voiceMode.value = 'idle'
    showReaction('助手暂时离线，先来句固定问候～')
    speakReply(GREETING, 'shrug')
  }
}

/**
 * 语音闭环主入口：听 → 问 AI → 答（+口型/手势）。
 * listening 态再点一次「停」= 提前结束聆听。
 */
async function onVoiceCommand() {
  if (voiceMode.value === 'listening') {
    // 主动停止：先复位，等到的听写结果直接作废（战术"停止手势"）
    voiceMode.value = 'idle'
    voiceInput.stop()
    playGestureWithVoice('signalStop', '已停止聆听')
    return
  }
  if (!voiceSupported) {
    showReaction('这个浏览器听不了语音，换 Chrome/Edge 试试')
    return
  }
  // 播报中/思考中按「听」= 插话：立刻停播报、取消在途提问，直接开始聆听。
  // 这就是「说话时不禁言」的核心——麦克风入口任何时候都可用。
  if (speaking.value || voiceMode.value !== 'idle') interruptPlayback()
  voiceMode.value = 'listening'
  // 聆听开始只做「凑近」动作、不念台词：此时麦克风已开，任何 TTS 都会被自己收进去
  personaRef.value?.playGesture?.('leanIn')
  const { text, reason } = await voiceInput.start()
  if (voiceMode.value !== 'listening') return
  if (!text) {
    voiceMode.value = 'idle'
    const errorGesture = LISTEN_ERROR_GESTURES[reason]
    if (errorGesture) {
      // 走统一发声入口：扶额/摊手等手势台词此前只做动作不发音
      playGestureWithVoice(errorGesture, LISTEN_ERRORS[reason] ?? '聆听失败，请重试')
    } else {
      showReaction(LISTEN_ERRORS[reason] ?? '聆听失败，请重试')
    }
    return
  }
  heard.value = text
  // 语音控屏：先检查导航意图——命中就直接路由或拦截，不调 AI。
  // 这能同时覆盖"高危拦截"和"快速跳转"两个场景，且避免 LLM 跑偏。
  const navIntent = resolveNavigationIntent(text)
  if (navIntent.matched) {
    voiceMode.value = 'thinking'
    if (navIntent.blocked) {
      // 高危拦截：播报"不能跳"，不执行路由
      showReaction(hazardBubble(navIntent), 3200)
      playGestureWithVoice('signalStop', hazardBubble(navIntent))
      voiceMode.value = 'idle'
      return
    }
    // 安全跳转：先播报确认，再路由
    const confirmPhrase = `好的，正在打开${navIntent.label}`
    playGestureWithVoice('radioCall', confirmPhrase)
    voiceMode.value = 'speaking'
    try {
      await router.push(navIntent.path)
    } catch (pushError) {
      showReaction(`页面跳转失败：${pushError?.message ?? '未知错误'}`, 3200)
    }
    voiceMode.value = 'idle'
    return
  }

  // ── 按钮级意图（当前页面上的操作） ──
  const currentRouteName = router.currentRoute.value?.name?.toString() ?? ''
  const actionIntent = resolveVoiceActionIntent(text, currentRouteName)

  if (pendingActionConfirm.value && _pendingStillFresh(pendingActionConfirm.value)) {
    // 上次播了"请再说一次确认"，用户这次又说了 —— 真正执行
    const pending = pendingActionConfirm.value
    if (actionIntent.matched && actionIntent.actionId === pending.actionId) {
      pendingActionConfirm.value = null
      voiceMode.value = 'thinking'
      const confirmPhrase = actionExecuteBubble(pending.label)
      playGestureWithVoice('radioCall', confirmPhrase)
      voiceMode.value = 'speaking'
      const fired = await voiceActionBus.dispatch(pending.actionId)
      voiceMode.value = 'idle'
      if (fired === 0) {
        showReaction(`抱歉，当前页面找不到"${pending.label}"的执行入口，请先导航到对应页面或手动操作`, 3200)
      }
      return
    }
    // 用户没说同一个 action → 废弃 pending，继续正常流程
    pendingActionConfirm.value = null
  }

  if (actionIntent.matched) {
    voiceMode.value = 'thinking'
    const level = HAZARD_LEVELS[actionIntent.hazard] ?? HAZARD_LEVELS.low

    if (level.blocks) {
      // critical：永远拦截
      const bubble = actionBlockedBubble(actionIntent.label, actionIntent.hazard)
      showReaction(bubble, 3200)
      playGestureWithVoice('signalStop', bubble)
      voiceMode.value = 'idle'
      return
    }

    if (level.requiresConfirm) {
      // high / medium：存 pending + 播报确认提示
      pendingActionConfirm.value = {
        actionId: actionIntent.actionId,
        label: actionIntent.label,
        hazard: actionIntent.hazard,
        expiresAt: Date.now() + 15_000,  // 15 秒内再说一次才算确认
      }
      const bubble = actionConfirmBubble(actionIntent.label, actionIntent.confirm)
      playGestureWithVoice('think', bubble)
      voiceMode.value = 'idle'
      return
    }

    // low：直接 dispatch
    const confirmPhrase = actionExecuteBubble(actionIntent.label)
    playGestureWithVoice('radioCall', confirmPhrase)
    voiceMode.value = 'speaking'
    const fired = await voiceActionBus.dispatch(actionIntent.actionId)
    voiceMode.value = 'idle'
    if (fired === 0) {
      showReaction(`当前页面暂未提供"${actionIntent.label}"的语音入口，请先导航到对应页面或手动操作`, 3200)
    }
    return
  }
  voiceMode.value = 'thinking'
  // 识别完成 = "收到呼叫"（无线电手势），随后进入思考与作答
  playGestureWithVoice('radioCall')
  const controller = new AbortController()
  askController = controller
  const { ok, text: reply } = await askAssistant(text, { signal: controller.signal })
  // 被新一轮插话打断：丢弃这次回答，不覆盖用户刚说的话
  if (controller.signal.aborted) return
  if (askController === controller) askController = null
  if (voiceMode.value !== 'thinking') return
  voiceMode.value = ok ? 'speaking' : 'idle'
  speakReply(reply, ok ? 'nod' : 'shrug')
  if (!ok) showReaction(reply, 3200)
}

// ── 按钮级意图二次确认的有效期检查 ──
function _pendingStillFresh(pending) {
  if (!pending?.expiresAt) return false
  if (Date.now() > pending.expiresAt) {
    pendingActionConfirm.value = null
    return false
  }
  return true
}

function stopSpeech() {
  speechToken += 1
  speaking.value = false
  lipAlign.value = 'text'
  neuralTts.stop()
  petSpeech.stop?.()
  personaRef.value?.stopSpeaking()
  if (voiceMode.value === 'speaking') voiceMode.value = 'idle'
}

function openFullPage() {
  stopSpeech()
  router.push('/agent/persona')
}

function updateViewport() {
  viewport.width = window.innerWidth
  viewport.height = window.innerHeight
  store.setPosition(store.position, {
    viewportWidth: viewport.width,
    viewportHeight: viewport.height
  })
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  idleScheduler.stop()
  clickClassifier.dispose()
  cancelPress()
  voiceInput.stop()
  petSpeech.dispose()
  neuralTts.dispose()
  personaRef.value?.stopSpeaking?.()
  personaRef.value?.stopGesture?.()
  if (reactionTimer) clearTimeout(reactionTimer)
  faultUnsubscribe?.()
  faultNotifier.dismiss() // 取消退醒定时并清气泡，幂等安全
})
</script>

<style scoped>
.persona-pet {
  position: fixed;
  left: 0;
  top: 0;
  z-index: 60;
  width: var(--persona-pet-w, 232px);
  height: var(--persona-pet-h, auto);
  display: grid;
  gap: var(--ds-space-2);
  padding: var(--ds-space-2);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: radial-gradient(120% 90% at 50% 0%, rgba(36, 150, 237, .14), transparent 62%), var(--ds-color-surface-raised);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .35);
  touch-action: none;
  user-select: none;
}

.persona-pet--dragging {
  cursor: grabbing;
}

.persona-pet__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
  cursor: grab;
}

.persona-pet--dragging .persona-pet__bar {
  cursor: grabbing;
}

.persona-pet__title {
  font-size: var(--ds-type-caption-size);
  letter-spacing: .12em;
  color: var(--ds-color-muted);
}

.persona-pet__bar-actions {
  display: inline-flex;
  gap: 4px;
}

.persona-pet__mini {
  min-width: 22px;
  min-height: 22px;
  padding: 0 4px;
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.persona-pet__mini:hover:not(:disabled) {
  color: var(--ds-color-text);
}

.persona-pet__mini:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* 兜底开关：开启态高亮（允许回落浏览器音色），默认关闭态为普通灰 */
.persona-pet__mini[aria-pressed='true'] {
  color: var(--smart-primary-strong, #2496ed);
  border-color: var(--smart-primary-strong, #2496ed);
}

/* 听筒开关：图标按钮，开启态高亮，关闭态回到默认灰 */
.persona-pet__mini--icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.persona-pet__mini--icon svg {
  display: block;
  width: 13px;
  height: 13px;
}

.persona-pet__mini--icon .spk-body {
  fill: currentColor;
}

.persona-pet__mini--icon .spk-wave path,
.persona-pet__mini--icon .spk-mute path {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
}

.persona-pet__mini--icon:not(.persona-pet__mini--muted) {
  color: var(--smart-primary-strong, #2496ed);
  border-color: var(--smart-primary-strong, #2496ed);
}

/* 聆听中：按钮呼吸提醒正在收音 */
.persona-pet__mini[data-listening='true'],
.persona-pet__mini[aria-label='停止聆听'] {
  color: var(--smart-primary-strong, #2496ed);
  border-color: var(--smart-primary-strong, #2496ed);
  animation: mic-listen 1.2s ease-in-out infinite;
}

@keyframes mic-listen {
  0%, 100% { opacity: .75 }
  50% { opacity: 1; box-shadow: 0 0 6px rgba(36, 150, 237, .45) }
}

.persona-pet__stage {
  position: relative;
  min-width: 0;
  isolation: isolate;
}

/* 生物发光氛围层：canvas 四周柔光晕 + 底部微弱青蓝渐变 */
.persona-pet__stage::before,
.persona-pet__stage::after {
  content: '';
  position: absolute;
  inset: -6% -4%;
  pointer-events: none;
  z-index: 0;
  border-radius: inherit;
}

.persona-pet__stage::before {
  background:
    radial-gradient(120% 90% at 50% 100%, rgba(36, 150, 237, .22), transparent 62%),
    radial-gradient(90% 70% at 50% 30%, rgba(122, 215, 245, .12), transparent 60%);
  filter: blur(1.2px);
}

.persona-pet__stage::after {
  box-shadow: 0 0 24px rgba(36, 150, 237, .12), inset 0 0 18px rgba(36, 150, 237, .06);
  animation: ocean-breath 4.8s ease-in-out infinite;
}

@keyframes ocean-breath {
  0%, 100% { opacity: .7; transform: scale(1) }
  50% { opacity: 1; transform: scale(1.02) }
}

.persona-pet__stage :deep(.persona) {
  position: relative;
  z-index: 1;
  padding: var(--ds-space-2);
  border: none;
  background: none;
}

.persona-pet__stage :deep(.webgl-host) {
  max-width: none;
}

.persona-pet__note {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-pet__note-hint {
  margin-left: var(--ds-space-1);
  color: var(--ds-color-text);
}

/* 右下角缩放手柄：骑在边框上，默认低调，悬停/拖动时点亮 */
.persona-pet__grip {
  position: absolute;
  right: -7px;
  bottom: -7px;
  width: 16px;
  height: 16px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ds-color-border-strong);
  border-radius: 50%;
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-muted);
  cursor: nwse-resize;
  touch-action: none;
  opacity: .65;
  transition: opacity var(--ds-duration-fast) ease, border-color var(--ds-duration-fast) ease,
    color var(--ds-duration-fast) ease;
}

.persona-pet__grip svg {
  display: block;
  width: 10px;
  height: 10px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
}

.persona-pet__grip:hover,
.persona-pet__grip:focus-visible {
  opacity: 1;
  color: var(--smart-primary-strong, #2496ed);
  border-color: var(--smart-primary-strong, #2496ed);
}

/* D1：点击反应气泡 */
.persona-pet__bubble {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  padding: 5px 12px;
  border-radius: 14px;
  background: var(--ds-color-surface-raised);
  border: 1px solid var(--ds-accent, #7ad7f5);
  color: var(--ds-color-text);
  font: 12px/1.4 var(--ds-font-cn);
  white-space: nowrap;
  box-shadow: 0 4px 14px rgba(36, 150, 237, .25);
  pointer-events: none;
}
.pet-bubble-enter-active,
.pet-bubble-leave-active {
  transition: opacity .2s ease, transform .2s ease;
}
.pet-bubble-enter-from,
.pet-bubble-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

/* 异常示警气泡：可点击打开处置面板；高危红描边 + 呼吸提醒 */
.persona-pet__bubble--alert {
  pointer-events: auto;
  cursor: pointer;
  border-color: #ef4444;
  color: #b91c1c;
  box-shadow: 0 4px 14px rgba(220, 38, 38, .3);
  animation: pet-alert-pulse 1.6s ease-in-out infinite;
}

@keyframes pet-alert-pulse {
  0%, 100% { box-shadow: 0 4px 14px rgba(220, 38, 38, .3); }
  50% { box-shadow: 0 4px 18px rgba(220, 38, 38, .55); }
}

@media (prefers-reduced-motion: reduce) {
  .persona-pet__bubble--alert {
    animation: none;
  }
}

/* 收起态小球：有待查看异常时亮红点，展开即随气泡消失 */
.persona-pet__orb--fault::after {
  content: '';
  position: absolute;
  top: 6px;
  right: 6px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 0 2px rgba(239, 68, 68, .25);
}

.persona-pet--collapsed {
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid rgba(122, 215, 245, .4);
  background:
    radial-gradient(circle at 50% 45%, rgba(180, 235, 255, .7), rgba(122, 215, 245, .35) 38%, rgba(36, 150, 237, .18) 62%, transparent 78%),
    var(--ds-color-surface-raised);
  box-shadow:
    0 0 0 1px rgba(36, 150, 237, .08),
    0 0 14px rgba(36, 150, 237, .28),
    0 0 36px rgba(36, 150, 237, .12),
    0 6px 18px rgba(0, 0, 0, .3);
  cursor: pointer;
  animation: orb-pulse 3.2s ease-in-out infinite;
}

@keyframes orb-pulse {
  0%, 100% { box-shadow: 0 0 0 1px rgba(36, 150, 237, .08), 0 0 14px rgba(36, 150, 237, .28), 0 0 36px rgba(36, 150, 237, .12), 0 6px 18px rgba(0, 0, 0, .3) }
  50% { box-shadow: 0 0 0 1px rgba(122, 215, 245, .14), 0 0 22px rgba(122, 215, 245, .42), 0 0 52px rgba(36, 150, 237, .22), 0 6px 18px rgba(0, 0, 0, .3) }
}

.persona-pet__orb {
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
  position: relative;
}

/* 内部核心光点 */
.persona-pet__orb::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: color-mix(in srgb, var(--smart-primary-strong) 92%, var(--smart-text));
  box-shadow: 0 0 8px 2px color-mix(in srgb, var(--smart-primary-strong) 70%, transparent), 0 0 16px 4px color-mix(in srgb, var(--smart-primary-strong) 40%, transparent);
  animation: orb-core 3.2s ease-in-out infinite;
}

@keyframes orb-core {
  0%, 100% { opacity: .6; transform: translate(-50%, -50%) scale(.9) }
  50% { opacity: 1; transform: translate(-50%, -50%) scale(1.1) }
}

@media (prefers-reduced-motion: reduce) {
  .persona-pet {
    background: var(--ds-color-surface-raised);
  }

  .persona-pet__mini[aria-label='停止聆听'] {
    animation: none;
  }
}
</style>
