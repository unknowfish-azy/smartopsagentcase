/**
 * 数字人对话的纯逻辑：聊天阶段 → 人格状态映射，流式增量 → 口型推进。
 *
 * 只放可单测的规则，不碰网络与 Vue：
 *  - personaStateForChat：把「连接中 / 流式输出 / 失败 / 渲染降级」映射到七态；
 *  - createSpeechPump：边收 token 边重建口型时间线，并跳到已播位置
 *    （useLipSync.speak 每次都会把时间线归零，直接逐 token 调用会让嘴反复重来）；
 *  - normalizeChatMessage：与 ai-service 的 2000 字符上限对齐的输入清洗。
 */

/** 聊天阶段 → 人格状态。说话阶段用 executing，失败用 error。 */
export function personaStateForChat(phase, { renderStatus = 'ready' } = {}) {
  if (renderStatus === 'error') return 'error'
  if (renderStatus === 'lost') return 'warning'
  if (phase === 'error') return 'error'
  if (phase === 'connecting') return 'thinking'
  if (phase === 'streaming') return 'executing'
  return 'idle'
}

export const CHAT_PHASE_LABELS = Object.freeze({
  idle: '待命',
  connecting: '连接 Agent 大脑',
  streaming: '正在回答',
  error: '回答失败'
})

const MAX_MESSAGE_CHARS = 2000
// 控制字符（保留换行/制表）会污染 prompt 与日志，输入侧先清掉。
const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g

/**
 * 清洗用户输入。
 * @returns {{ ok: boolean, text: string, reason?: 'empty' | 'too-long' }}
 */
export function normalizeChatMessage(value) {
  const text = String(value ?? '').replace(CONTROL_CHARS, '').trim()
  if (!text) return { ok: false, text: '', reason: 'empty' }
  if (text.length > MAX_MESSAGE_CHARS) return { ok: false, text, reason: 'too-long' }
  return { ok: true, text }
}

/**
 * 流式口型泵。
 *
 * push(累计文本) 时用完整文本重建时间线，再 seek 到上次已播位置，
 * 这样新 token 从「接下来该说的字」开始动嘴，而不是从头重播。
 *
 * @param {{ speakText?: Function, seekSpeech?: Function, stopSpeaking?: Function }} persona
 */
export function createSpeechPump(persona, { cps = 5 } = {}) {
  let spokenChars = 0

  return {
    push(fullText) {
      const spoken = String(fullText ?? '')
      if (!spoken.trim()) return
      persona?.speakText?.(spoken, { cps })
      if (spokenChars > 0) persona?.seekSpeech?.(spokenChars)
      spokenChars = spoken.length
    },
    stop() {
      spokenChars = 0
      persona?.stopSpeaking?.()
    }
  }
}
