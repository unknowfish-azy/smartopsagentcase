/**
 * 流式分句：把 LLM 逐 token 吐出的文本切成可独立播报的句子。
 *
 * 目的：不再等整段回答合成完才出声，首句一到就送去 TTS，长句按软停顿提前切，
 * 避免"答完半天没声音"。纯逻辑、无副作用，可单测。
 *
 * 切分规则（针对中文讲解）：
 *  - 句末标点（。！？；… 换行）立即切；
 *  - 逗号/顿号只在已积累到 softChars 时才切，免得把"根据今天天气"这种半句念断；
 *  - 超过 maxChars 仍未遇到标点时强制切，防止一口气合成超长句把首句延迟拖大；
 *  - 不按英文句点切，避免把 3.5 / A-07 这类数字与编号拆开。
 */

const TERMINATORS = /[。！？!?；;…\n]/
const SOFT_BREAKS = /[，,、]/
// 至少要有一个可发音字符（字母/数字/汉字）才值得送 TTS；
// 流式 token 常把标点单独吐出来，纯标点不能变成一句"空气句子"
const SPEAKABLE = /[\p{L}\p{N}]/u

function pick(piece) {
  const text = piece.trim()
  return text && SPEAKABLE.test(text) ? text : ''
}

/**
 * @param {{ softChars?: number, maxChars?: number }} [options]
 * @returns {{ push: (delta?: string) => string[], flush: () => string[] }}
 */
export function createSentenceSplitter({ softChars = 26, maxChars = 60 } = {}) {
  let buffer = ''

  function push(delta) {
    buffer += String(delta ?? '')
    const out = []
    let start = 0
    for (let i = 0; i < buffer.length; i += 1) {
      const char = buffer[i]
      const length = i + 1 - start
      const hard = TERMINATORS.test(char) || length >= maxChars
      const soft = SOFT_BREAKS.test(char) && length >= softChars
      if (!hard && !soft) continue
      const piece = pick(buffer.slice(start, i + 1))
      if (piece) out.push(piece)
      start = i + 1
    }
    buffer = buffer.slice(start)
    return out
  }

  function flush() {
    const rest = pick(buffer)
    buffer = ''
    return rest ? [rest] : []
  }

  return { push, flush }
}

/** 非流式文本（如离线兜底整段稿）直接切成句子数组 */
export function splitSentences(text) {
  const splitter = createSentenceSplitter()
  return [...splitter.push(text), ...splitter.flush()]
}
