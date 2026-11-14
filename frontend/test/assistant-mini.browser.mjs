import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'
import { blockLiveApi, mockAssistant } from './helpers/assistant.mjs'

let browser
before(async () => { browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true }) })
after(async () => { await browser?.close() })

async function open({ width = 1440, theme = 'light', state = {} } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await blockLiveApi(page)
  await mockSession(page)
  await mockAssistant(page, state)
  await page.addInitScript(theme => {
    localStorage.setItem('smartops_theme', theme)
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 'mini-alice' }))
  }, theme)
  await page.goto('http://127.0.0.1:5173/chat', { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  return { page, state, errors }
}

async function send(page, message) {
  await page.getByLabel('输入消息', { exact: true }).fill(message)
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.locator('.ai-chat-message--assistant').filter({ hasText: '已收到：' + message }).waitFor()
}

test('new account with no external model chats with Mini and displays runtime status', async () => {
  const { page, state, errors } = await open()
  try {
    assert.equal(await page.getByLabel('助手模型', { exact: true }).inputValue(), 'mini')
    await page.getByText('运行时就绪', { exact: false }).waitFor()
    await send(page, '没有外部模型也能问')
    assert.deepEqual(state.chats, [{ providerKey: 'mini', message: '没有外部模型也能问', history: [] }])
    assert.deepEqual(errors, [])
  } finally { await page.close() }
})
