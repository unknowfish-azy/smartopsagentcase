/**
 * 解码文本纯逻辑（主题二配方 C，arwes 手法）。
 * 目标字符串先整体显示为随机字符，再逐字"落定"回原文，
 * 总时长 240–400ms——超过这个上限就从"仪器开机"变成"廉价炫技"
 * （见《三主题炫技UI-开源清单.md》配方 C 红线）。
 *
 * 只放纯函数：时序与 reduced-motion 降级在 DecodeText.vue，
 * 测试见 test/decode-text.test.mjs。
 */

/** arwes 风格字符池：大写字母 + 数字，等宽环境下宽度稳定、辨识度接近真实 ID。 */
export const SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

/** 分隔符在落定过程中保持原样，避免字符宽度剧烈跳动（ID 场景常见格式）。 */
const STABLE_CHARS = new Set([' ', '-', '_', ':', '.', '/'])

/** 取一个随机乱码字符；随机源可注入以便测试重现。 */
export function nextScrambleChar(random = Math.random) {
  const index = Math.floor(random() * SCRAMBLE_CHARS.length)
  return SCRAMBLE_CHARS[index] ?? SCRAMBLE_CHARS[0]
}

/**
 * 计算某一进度下应显示的文本。
 * @param {string|null|undefined} target 目标文本（真实值）
 * @param {number} progress 0–1；<1 时未落定部分显示乱码，>=1 时等于原文
 * @param {() => number} random 随机源（测试可注入固定值）
 * @returns {string} 该帧的显示文本；target 为空时返回 ''
 */
export function frameText(target, progress, random = Math.random) {
  if (target == null) return ''
  const text = String(target)
  if (!text) return ''
  // [...text] 按码点展开：emoji / 代理对不会被切成半个字符。
  const chars = [...text]
  const ratio = Number.isFinite(progress) ? progress : 0
  if (ratio >= 1) return text
  const settled = Math.max(0, Math.min(chars.length, Math.floor(ratio * chars.length)))
  let out = ''
  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index]
    out += index < settled || STABLE_CHARS.has(char) ? char : nextScrambleChar(random)
  }
  return out
}

/**
 * 解码时长随目标长度增长，但被夹在 240–400ms（配方 C 红线）。
 * @param {number} length 目标文本长度（按码点计）
 * @returns {number} 毫秒
 */
export function decodeDurationFor(length) {
  const size = Number.isFinite(length) ? Math.max(0, length) : 0
  return Math.min(400, Math.max(240, 160 + size * 12))
}
