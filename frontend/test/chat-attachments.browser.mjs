import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const base = 'http://127.0.0.1:5298'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5298, strictPort: true }, logLevel: 'error' })
await server.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const errors = [], calls = []
const conversations = new Map(), attachments = new Map(), uploads = new Map()
let failUpload = true
const user = { id: 991, username: 'attachment-browser-test', role: 'operator', portal: 'user', mustChangePassword: false }
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF6kAAAAASUVORK5CYII=', 'base64')
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  await context.addInitScript(() => { localStorage.setItem('smartops_visual_mode', 'reduced-motion'); if (!localStorage.getItem('smartops_theme')) localStorage.setItem('smartops_theme', 'light') })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method()
    if (url.origin !== base) return route.abort()
    if (!path.startsWith('/api/')) return route.continue()
    calls.push({ path, method })
    const reply = (data, code = 200, message = 'OK') => route.fulfill({ status: code, json: { code, message, data } })
    if (method !== 'GET') assert.equal(request.headers()['x-csrf-token'], 'attachment-csrf')
    if (path === '/api/auth/session') return reply({ user, csrfToken: 'attachment-csrf' })
    if (path === '/api/assistant/options') return reply({ selectedKey: 'mini', options: [{ key: 'mini', name: '智维 Mini', available: true, enabled: true, kind: 'builtin' }] })
    if (path === '/api/assistant/chat') return reply({ content: '普通文本回复', providerKey: 'mini' })
    if (path === '/api/assistant/conversations') {
      if (method === 'GET') return reply([...conversations.values()].map(({ messages, ...conversation }) => conversation))
      const input = request.postDataJSON()
      if (!conversations.has(input.id)) conversations.set(input.id, { ...input, createdAt: Date.now(), updatedAt: Date.now(), teamId: null, messages: [] })
      return reply(conversations.get(input.id))
    }
    const match = path.match(/^\/api\/assistant\/conversations\/([^/]+)(.*)$/)
    if (match) {
      const conversation = conversations.get(match[1]), suffix = match[2]
      if (!conversation) return reply(null, 404, '会话不存在')
      if (!suffix) {
        if (method === 'DELETE') { conversations.delete(match[1]); return reply(null) }
        if (method === 'PUT') conversation.title = request.postDataJSON().title
        return reply(conversation)
      }
      if (suffix === '/attachments') {
        assert.match(request.headers()['content-type'], /multipart\/form-data; boundary=/)
        const body = request.postDataBuffer().toString('utf8')
        const name = body.match(/filename="([^"]+)"/)?.[1]
        const requestId = body.match(/name="requestId"\r\n\r\n([^\r]+)/)?.[1]
        assert.ok(name); assert.ok(requestId)
        if (failUpload) { failUpload = false; return reply(null, 503, '模拟上传断线') }
        const file = uploads.get(requestId) || { id: crypto.randomUUID(), name, mediaType: name.endsWith('.png') ? 'image/png' : 'text/plain', size: 50 }
        uploads.set(requestId, file); attachments.set(file.id, file)
        return reply(file)
      }
      if (suffix === '/messages') {
        const input = request.postDataJSON()
        if (!conversation.messages.some(message => message.requestId === input.requestId)) conversation.messages.push(
          { id: crypto.randomUUID(), requestId: input.requestId, role: 'user', content: input.text, attachments: input.attachmentIds.map(id => attachments.get(id)) },
          { id: crypto.randomUUID(), role: 'assistant', content: '附件已保存，尚未接入 OCR 或图片理解。', providerKey: 'attachment-receipt' })
        return reply(conversation)
      }
      if (suffix.endsWith('/content')) return route.fulfill({ contentType: 'image/png', body: png })
      if (method === 'DELETE') return reply(null)
    }
    return reply([])
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${base}/chat`)
  await page.getByLabel('输入消息', { exact: true }).fill('原有本地对话')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.getByText('普通文本回复', { exact: true }).waitFor()
  await page.getByLabel('选择聊天附件', { exact: true }).setInputFiles({ name: 'error.log', mimeType: 'text/plain', buffer: Buffer.from('ERROR: permission denied') })
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.getByText('模拟上传断线', { exact: true }).first().waitFor()
  assert.equal(conversations.size, 1)
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.getByText('附件已保存，尚未接入 OCR 或图片理解。', { exact: true }).waitFor()
  assert.equal([...conversations.values()][0].messages.length, 2)
  assert.equal(calls.filter(call => call.path === '/api/assistant/chat').length, 1)
  assert.ok(!JSON.stringify([...conversations.values()]).includes('原有本地对话'))
  assert.ok(!(await page.evaluate(() => JSON.stringify(localStorage))).includes('error.log'))

  await page.getByLabel('输入消息', { exact: true }).evaluate((element, data) => {
    const transfer = new DataTransfer()
    transfer.items.add(new File([new Uint8Array(data)], 'paste.png', { type: 'image/png' }))
    element.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: transfer }))
  }, [...png])
  await page.locator('.attachment-draft').waitFor()
  assert.equal(await page.locator('.attachment-draft').count(), 1)
  await page.getByRole('button', { name: '预览 paste.png', exact: true }).click()
  await page.getByRole('dialog', { name: '发送前预览' }).waitFor()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await page.getByRole('button', { name: '预览图片 · paste.png', exact: true }).waitFor()
  await page.getByRole('button', { name: '预览图片 · paste.png', exact: true }).click()
  await page.getByRole('dialog', { name: 'paste.png', exact: true }).waitFor()
  await page.keyboard.press('Escape')
  await page.locator('.ai-chat-composer').evaluate(element => {
    const transfer = new DataTransfer()
    transfer.items.add(new File(['drop evidence'], 'drop.txt', { type: 'text/plain' }))
    const event = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer })
    element.dispatchEvent(event)
    if (!event.defaultPrevented) throw new Error('Drop navigation was not prevented')
  })
  await page.getByRole('button', { name: '移除 drop.txt', exact: true }).waitFor()
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  assert.equal(await page.locator('.attachment-draft').count(), 1)
  await page.getByRole('button', { name: '移除 drop.txt', exact: true }).click()
  assert.equal(await page.locator('.attachment-draft').count(), 0)
  await page.reload()
  await page.getByRole('button', { name: '个人附件会话', exact: true }).click()
  await page.getByRole('button', { name: '预览图片 · paste.png', exact: true }).waitFor()
  await mkdir('../test-artifacts/chat-attachments', { recursive: true })
  for (const theme of ['light', 'dark']) {
    await page.evaluate(theme => { localStorage.setItem('smartops_theme', theme) }, theme)
    await page.reload()
    assert.equal(await page.locator('html').getAttribute('data-theme'), theme)
    await page.getByRole('button', { name: '个人附件会话', exact: true }).click()
    await page.getByRole('button', { name: '预览图片 · paste.png', exact: true }).waitFor()
    await page.screenshot({ path: `../test-artifacts/chat-attachments/${theme}-desktop.png` })
    await page.setViewportSize({ width: 375, height: 900 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
    await page.screenshot({ path: `../test-artifacts/chat-attachments/${theme}-mobile.png`, fullPage: true })
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
  assert.deepEqual(errors, [])
  console.log('PASS: file-only send, retry, multipart, paste image, preview, drag/drop, private server restore, no model transfer, light/dark/mobile; all API requests mocked')
} finally { await browser.close(); await server.close() }
