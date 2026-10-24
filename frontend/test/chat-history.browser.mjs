import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'
import { blockLiveApi, mockAssistant } from './helpers/assistant.mjs'

let browser
before(async () => {
  browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
})
after(async () => { await browser?.close() })

async function openChat({ width = 1440, theme = 'light' } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
  const errors = []
  await blockLiveApi(page)
  await mockSession(page)
  const prompts = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(({ theme }) => {
    if (!sessionStorage.getItem('chat-test-initialized')) {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'history-test' }))
      localStorage.setItem('smartops_theme', theme)
      sessionStorage.setItem('chat-test-initialized', 'true')
    }
  }, { theme })
  await mockAssistant(page)
  await page.route('**/api/assistant/chat', route => {
    const payload = route.request().postDataJSON()
    prompts.push(payload)
    return route.fulfill({ json: { code: 200, data: { content: `已收到：${payload.message}`, providerKey: payload.providerKey, providerName: '智维 Mini', citations: [] } } })
  })
  await page.goto('http://127.0.0.1:5173/chat', { waitUntil: 'domcontentloaded' })
  await page.locator('.chat-page').waitFor()
  return { page, errors, prompts }
}

async function send(page, text) {
  await page.getByLabel('输入消息', { exact: true }).fill(text)
  await page.locator('.ai-chat-send').click()
  await page.locator('.ai-chat-message--assistant').filter({ hasText: `已收到：${text}` }).waitFor()
}

test('desktop history has visible borders, compact icons and clears the main navigation', async () => {
  const { page } = await openChat()
  try {
    const metrics = await page.evaluate(() => {
      const history = document.querySelector('.chat-page__sidebar').getBoundingClientRect()
      const navigation = document.querySelector('.sidebar').getBoundingClientRect()
      const icon = document.querySelector('.chat-history__new svg').getBoundingClientRect()
      return { historyLeft: history.left, navigationRight: navigation.right, iconWidth: icon.width, borderWidth: getComputedStyle(document.querySelector('.chat-page')).borderTopWidth }
    })
    assert.equal(metrics.borderWidth, '1px')
    assert.ok(metrics.iconWidth <= 20, `oversized icon: ${metrics.iconWidth}`)
    assert.ok(metrics.historyLeft >= metrics.navigationRight, 'main navigation must not cover chat history')
  } finally { await page.close() }
})

test('history creates, switches, searches, renames, deletes and survives reload', async () => {
  const { page, errors, prompts } = await openChat()
  try {
    await send(page, '检查 CPU')
    await page.getByRole('button', { name: '新建对话', exact: true }).click()
    await send(page, '检查内存')
    assert.equal(await page.locator('.chat-history__item').count(), 2)
    await page.getByRole('button', { name: '检查 CPU', exact: true }).click()
    await send(page, '下一步呢')
    assert.match(JSON.stringify(prompts.at(-1).history), /检查 CPU/)
    assert.doesNotMatch(JSON.stringify(prompts.at(-1).history), /检查内存/)
    assert.equal(prompts.at(-1).providerKey, 'mini')
    assert.equal(prompts.at(-1).message, '下一步呢')
    await page.getByLabel('搜索历史会话').fill('下一步')
    assert.equal(await page.locator('.chat-history__item').count(), 1)
    await page.getByLabel('搜索历史会话').fill('')
    await page.getByRole('button', { name: '管理会话：检查 CPU', exact: true }).click()
    await page.getByRole('menuitem', { name: '重命名', exact: true }).click()
    await page.locator('.el-message-box input').fill('CPU 排障记录')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByRole('heading', { name: 'CPU 排障记录', exact: true }).waitFor()
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { name: 'CPU 排障记录', exact: true }).waitFor()
    assert.equal(await page.locator('.ai-chat-message').count(), 4)
    await page.getByRole('button', { name: '管理会话：CPU 排障记录', exact: true }).click()
    await page.getByRole('menuitem', { name: '删除会话', exact: true }).click()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    assert.equal(await page.locator('.chat-history__item').count(), 2)
    await page.getByRole('button', { name: '管理会话：CPU 排障记录', exact: true }).click()
    await page.getByRole('menuitem', { name: '删除会话', exact: true }).click()
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.getByRole('heading', { name: '检查内存', exact: true }).waitFor()
    assert.equal(await page.locator('.chat-history__item').count(), 1)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { name: '检查内存', exact: true }).waitFor()
    assert.deepEqual(errors, [])
  } finally { await page.close() }
})

test('pending replies stay in their originating conversation and deleted history stays deleted', async () => {
  const { page } = await openChat()
  let pendingRoute
  await page.route('**/api/assistant/chat', route => { pendingRoute = route })
  try {
    await page.getByLabel('输入消息', { exact: true }).fill('慢请求')
    await page.locator('.ai-chat-send').click()
    await page.waitForFunction(() => document.querySelector('.ai-chat-pending'))
    while (!pendingRoute) await new Promise(resolve => setTimeout(resolve, 20))
    await page.getByRole('button', { name: '新建对话', exact: true }).click()
    await pendingRoute.fulfill({ json: { code: 200, data: { content: '慢请求的回复' } } })
    assert.equal(await page.locator('.ai-chat-message').count(), 0)
    await page.getByRole('button', { name: '慢请求', exact: true }).click()
    await page.getByText('慢请求的回复', { exact: true }).waitFor()
    pendingRoute = null
    await page.getByLabel('输入消息', { exact: true }).fill('即将删除')
    await page.locator('.ai-chat-send').click()
    while (!pendingRoute) await new Promise(resolve => setTimeout(resolve, 20))
    await page.getByRole('button', { name: '管理会话：慢请求', exact: true }).click()
    await page.getByRole('menuitem', { name: '删除会话', exact: true }).click()
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await pendingRoute.fulfill({ json: { code: 200, data: { content: '不得复活的回复' } } })
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.chat-page').waitFor()
    assert.equal(await page.getByRole('button', { name: '慢请求', exact: true }).count(), 0)
    assert.equal(await page.locator('.ai-chat-message').count(), 0)
  } finally { await page.close() }
})

test('account changes isolate history within the same SPA and storage failures are visible', async () => {
  const { page } = await openChat()
  try {
    await send(page, '我的私有记录')
    const switchUser = username => page.evaluate(async username => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username }))
      const { currentSession } = await import('/src/security/session.js')
      currentSession.value = { id: username === 'history-test' ? 1 : 2, username, role: 'operator' }
      const { useAiChatStore } = await import('/src/stores/aiChat.js')
      useAiChatStore().syncAccount()
    }, username)
    await switchUser('second-user')
    assert.equal(await page.locator('.ai-chat-message').count(), 0)
    assert.equal(await page.locator('.chat-history__item').count(), 0)
    await send(page, '另一个账号的记录')
    await switchUser('history-test')
    await page.getByRole('heading', { name: '我的私有记录', exact: true }).waitFor()
    assert.equal(await page.getByText('另一个账号的记录', { exact: true }).count(), 0)
    await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException('full', 'QuotaExceededError') } })
    await page.getByRole('button', { name: '新建对话', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: '历史记录保存失败' }).waitFor()
  } finally { await page.close() }
})

test('failed replies remain readable after refresh and deleting the last conversation resets the panel', async () => {
  const { page } = await openChat()
  try {
    await page.route('**/api/assistant/chat', route => route.fulfill({ json: { code: 500, message: '测试：模型暂不可用' } }))
    await page.getByLabel('输入消息', { exact: true }).fill('请求失败测试')
    await page.locator('.ai-chat-send').click()
    await page.locator('.ai-chat-message__error').waitFor()
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.ai-chat-message__error').waitFor()
    assert.equal(await page.getByLabel('输入消息', { exact: true }).isEnabled(), true)
    await page.getByRole('button', { name: '管理会话：请求失败测试', exact: true }).click()
    await page.getByRole('menuitem', { name: '删除会话', exact: true }).click()
    await page.getByRole('button', { name: '删除', exact: true }).click()
    await page.locator('.ai-chat-empty').waitFor()
    assert.equal(await page.locator('.chat-history__item').count(), 0)
  } finally { await page.close() }
})

test('refresh marks a persisted pending reply interrupted and unlocks the composer', async () => {
  const { page } = await openChat()
  let pendingRoute
  try {
    await page.route('**/api/assistant/chat', route => { pendingRoute = route })
    await page.getByLabel('输入消息', { exact: true }).fill('刷新中断测试')
    await page.locator('.ai-chat-send').click()
    while (!pendingRoute) await new Promise(resolve => setTimeout(resolve, 20))
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.ai-chat-message__error').filter({ hasText: '上次回复已中断' }).waitFor()
    assert.equal(await page.getByLabel('输入消息', { exact: true }).isEnabled(), true)
    assert.equal(await page.locator('.ai-chat-pending').count(), 0)
  } finally {
    await pendingRoute?.abort().catch(() => {})
    await page.close()
  }
})

for (const theme of ['light', 'dark']) {
  test(`${theme} mobile drawer is usable, fits the viewport and hands off pet chat`, async () => {
    const { page, errors } = await openChat({ width: 375, theme })
    try {
      await page.getByLabel('打开历史会话').click()
      const drawer = page.getByRole('dialog', { name: '历史会话', exact: true })
      await drawer.waitFor()
      await drawer.getByRole('button', { name: '新建对话', exact: true }).click()
      await drawer.waitFor({ state: 'hidden' })
      await send(page, '手机记录')
      await page.getByLabel('打开历史会话').click()
      await page.screenshot({ path: `test-artifacts/mini/chat-history-${theme}-drawer.png`, fullPage: true })
      await drawer.getByRole('button', { name: '手机记录', exact: true }).click()
      await drawer.waitFor({ state: 'hidden' })
      await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
      await page.locator('.home-orbital').waitFor()
      assert.equal(await page.locator('.home-chat-section, .home-orbital .ai-chat-panel').count(), 0)
      await page.locator('.core-control').click()
      await page.getByRole('button', { name: 'AI 对话', exact: true }).click()
      await page.getByLabel('输入运维问题', { exact: true }).fill('桌宠追问')
      await page.locator('.pet-chat').getByLabel('发送消息', { exact: true }).click()
      await page.locator('.pet-chat__message--assistant').filter({ hasText: '已收到：桌宠追问' }).waitFor()
      await page.getByLabel('打开完整聊天', { exact: true }).click()
      await page.locator('.chat-page').waitFor()
      assert.equal(await page.locator('.ai-chat-message').count(), 4)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      await page.screenshot({ path: `test-artifacts/mini/chat-history-${theme}-mobile.png`, fullPage: true })
      await page.setViewportSize({ width: 1440, height: 1000 })
      await page.locator('.chat-page__sidebar').waitFor()
      await page.screenshot({ path: `test-artifacts/mini/chat-history-${theme}-desktop.png`, fullPage: true })
      await page.getByRole('button', { name: '管理会话：手机记录', exact: true }).click()
      await page.getByRole('menuitem', { name: '重命名', exact: true }).click()
      const background = await page.locator('.chat-history-dialog').evaluate(element => getComputedStyle(element).backgroundColor)
      assert.equal(background, theme === 'light' ? 'rgb(255, 255, 255)' : 'rgb(7, 16, 24)')
      await page.getByRole('button', { name: '取消', exact: true }).click()
      assert.deepEqual(errors, [])
    } finally { await page.close() }
  })
}
