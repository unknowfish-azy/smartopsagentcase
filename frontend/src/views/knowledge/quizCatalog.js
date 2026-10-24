// 题库：从既有知识条目中提取 QUESTION / WRONG_ANSWER 两类，归一化成可练习的题目。
// 复用 knowledgeCatalog 的 knowledgeEntries，不重造题目数据。

import { knowledgeEntries } from './knowledgeCatalog.js'

function normalizeQuizItem(entry) {
  const kind = entry.type === 'WRONG_ANSWER' ? 'wrong' : 'question'
  return {
    id: String(entry.id),
    kind,
    // 判断题 = 错题（错误认知）改造而来：给出一个说法，让用户判断对错
    typeLabel: kind === 'wrong' ? '判断题' : '问答题',
    prompt: kind === 'wrong' ? (entry.misconception || entry.title || '') : (entry.question || entry.title || ''),
    // 判断题的解析 = 正确纠正；问答题的解析 = 答案
    answer: kind === 'wrong' ? (entry.correction || '') : (entry.answer || ''),
    category: entry.category || entry.wrong_reason_type || '未分类',
    platform: entry.platform || entry.domain || '未分类',
    relatedIds: Array.isArray(entry.relatedIds) ? entry.relatedIds : []
  }
}

export const quizItems = knowledgeEntries
  .filter(entry => entry.type === 'QUESTION' || entry.type === 'WRONG_ANSWER')
  .map(normalizeQuizItem)

export const quizPlatforms = [...new Set(quizItems.map(item => item.platform))].sort()
export const quizTypes = [...new Set(quizItems.map(item => item.typeLabel))].sort()

// --- 错题本（localStorage，用户层轻量持久化；后续可升级为后端表） ----------
const WRONG_BOOK_KEY = 'smartops_quiz_wrong_book'

export function loadWrongBook() {
  try { return JSON.parse(localStorage.getItem(WRONG_BOOK_KEY)) || [] } catch { return [] }
}

export function saveWrongBook(items) {
  try { localStorage.setItem(WRONG_BOOK_KEY, JSON.stringify(items)) } catch { /* Storage optional */ }
}

export function addWrongItem(item) {
  const book = loadWrongBook()
  if (book.some(entry => entry.id === item.id)) return book
  const next = [{ id: item.id, kind: item.kind, typeLabel: item.typeLabel, prompt: item.prompt, answer: item.answer, platform: item.platform, savedAt: Date.now() }, ...book]
  saveWrongBook(next)
  return next
}

export function removeWrongItem(id) {
  const next = loadWrongBook().filter(entry => entry.id !== id)
  saveWrongBook(next)
  return next
}
