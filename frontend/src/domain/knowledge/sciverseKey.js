/**
 * sciverseKey — SciVerse API Key 的前端校验与脱敏展示（纯函数，node:test 可测）
 *
 * 后端 PUT /api/knowledge/sciverse/key 是最终校验方；这里做第一道过滤，
 * 把今晚已验证过的坑提前拦住：sk- 系列密钥会被网关 UNAUTHORIZED 拒绝，
 * 官方控制台签发的密钥固定以 sci_ 开头。
 */

export const KEY_MIN_LENGTH = 16

/**
 * 校验并归一用户输入的密钥。
 * @returns {{ ok: boolean, value: string, reason: string|null }}
 *   ok=false 时 reason 为可直接展示的中文提示。
 */
export function validateSciverseKey(raw) {
  const value = String(raw ?? '').trim()
  if (!value) return { ok: false, value: '', reason: '密钥不能为空' }
  if (!value.startsWith('sci_')) {
    return { ok: false, value, reason: 'SciVerse 控制台签发的密钥以 sci_ 开头（sk- 开头的是其他平台凭证，网关会拒绝）' }
  }
  if (value.length < KEY_MIN_LENGTH) {
    return { ok: false, value, reason: `密钥长度异常（不足 ${KEY_MIN_LENGTH} 字符），请确认复制完整` }
  }
  if (/\s/.test(value)) {
    return { ok: false, value, reason: '密钥不应包含空白字符，请重新复制' }
  }
  return { ok: true, value, reason: null }
}

/** 展示用脱敏：保留前 6 后 4，中间以 … 代替。空值返回 null。 */
export function maskSciverseKey(value) {
  const key = String(value ?? '').trim()
  if (!key) return null
  if (key.length <= 10) return key.slice(0, 4) + '…'
  return key.slice(0, 6) + '…' + key.slice(-4)
}
