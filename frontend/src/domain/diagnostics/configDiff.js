import { redactConfigText } from './redactConfig.js'

function linesOf(text) {
  if (new TextEncoder().encode(text).length > 256 * 1024) throw new Error('每侧文本不能超过 256 KiB')
  const lines = text === '' ? [] : text.replace(/\r\n?/g, '\n').split('\n')
  if (lines.length > 5000) throw new Error('每侧文本不能超过 5000 行')
  return lines
}

export function compareConfigTexts(left, right, { ignoreTrailingWhitespace = false } = {}) {
  const before = linesOf(left)
  const after = linesOf(right)
  const beforeMasked = redactConfigText(before.join('\n')).split('\n')
  const afterMasked = redactConfigText(after.join('\n')).split('\n')
  const normalized = value => ignoreTrailingWhitespace ? value.trimEnd() : value
  const beforeKeys = before.map(normalized)
  const afterKeys = after.map(normalized)
  let prefix = 0
  while (prefix < before.length && prefix < after.length && beforeKeys[prefix] === afterKeys[prefix]) prefix++
  let suffix = 0
  while (suffix < before.length - prefix && suffix < after.length - prefix && beforeKeys[before.length - suffix - 1] === afterKeys[after.length - suffix - 1]) suffix++
  const removedLength = before.length - prefix - suffix
  const addedLength = after.length - prefix - suffix
  if (removedLength * addedLength > 1_000_000) throw new Error('差异计算量超过上限，请拆分配置后比较')
  const stride = addedLength + 1
  const scores = new Uint16Array((removedLength + 1) * stride)
  for (let oldIndex = removedLength - 1; oldIndex >= 0; oldIndex--) {
    for (let newIndex = addedLength - 1; newIndex >= 0; newIndex--) {
      scores[oldIndex * stride + newIndex] = beforeKeys[prefix + oldIndex] === afterKeys[prefix + newIndex]
        ? 1 + scores[(oldIndex + 1) * stride + newIndex + 1]
        : Math.max(scores[(oldIndex + 1) * stride + newIndex], scores[oldIndex * stride + newIndex + 1])
    }
  }
  const rows = []
  let removed = 0
  let added = 0
  const equal = (oldIndex, newIndex) => rows.push({ type: 'equal', before: oldIndex + 1, after: newIndex + 1, text: afterMasked[newIndex] })
  for (let index = 0; index < prefix; index++) equal(index, index)
  let oldIndex = 0
  let newIndex = 0
  while (oldIndex < removedLength || newIndex < addedLength) {
    if (oldIndex < removedLength && newIndex < addedLength && beforeKeys[prefix + oldIndex] === afterKeys[prefix + newIndex]) {
      equal(prefix + oldIndex++, prefix + newIndex++)
    } else if (oldIndex < removedLength && (newIndex === addedLength || scores[(oldIndex + 1) * stride + newIndex] >= scores[oldIndex * stride + newIndex + 1])) {
      rows.push({ type: 'removed', before: prefix + oldIndex + 1, after: null, text: beforeMasked[prefix + oldIndex++] })
      removed++
    } else {
      rows.push({ type: 'added', before: null, after: prefix + newIndex + 1, text: afterMasked[prefix + newIndex++] })
      added++
    }
  }
  for (let index = suffix; index > 0; index--) equal(before.length - index, after.length - index)
  return { rows, removed, added }
}
