import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'
import { blockLiveApi, mockAssistant } from './helpers/assistant.mjs'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    const errors = []
    await blockLiveApi(page)
    await mockSession(page)
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', '{}'); localStorage.removeItem('smartops_ops_spider_position') })
    const assistant = await mockAssistant(page)
    await page.route('**/api/assistant/chat', route => {
      assistant.chats.push(route.request().postDataJSON())
      return route.fulfill({ json: { code: 200, data: { content: '先检查 CPU 使用率。', providerKey: 'mini', providerName: '智维 Mini', citations: [] } } })
    })
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
    await page.locator('.ops-spider-pet').waitFor()
    const pet = page.locator('.ops-spider-pet')
    await pet.waitFor()
    await pet.locator('.core-control').click()
    assert.equal(await pet.locator('.action-orbit button').count(), 8)
    const petBeforeDrag = await pet.boundingBox()
    const dragStart = { x: petBeforeDrag.x + petBeforeDrag.width / 2, y: petBeforeDrag.y + petBeforeDrag.height / 2 }
    const dragTarget = { x: width >= 768 ? 400 : 24, y: 250 }
    await page.mouse.move(dragStart.x, dragStart.y)
    await page.mouse.down()
    await page.mouse.move(dragTarget.x, dragTarget.y, { steps: 5 })
    const petDuringDrag = await pet.boundingBox()
    assert.ok(petDuringDrag && Number.isFinite(petDuringDrag.x), 'pet remains measurable during drag')
    const orbitBounds = await pet.locator('.action-orbit button').evaluateAll(buttons => buttons.map(button => {
      const { x, y, width: itemWidth, height } = button.getBoundingClientRect()
      return { x, y, right: x + itemWidth, bottom: y + height }
    }))
    assert.ok(orbitBounds.every(box => box.x >= 0 && box.y >= 0 && box.right <= width && box.bottom <= 900), `orbit stays in viewport while dragging: ${JSON.stringify(orbitBounds)}`)
    await page.mouse.up()
    const action = pet.getByRole('button', { name: 'AI 对话' })
    const box = await action.boundingBox()
    assert.ok(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= width && box.y + box.height <= 900, `AI action fits viewport: ${JSON.stringify(box)}`)
    await action.dispatchEvent('click')
    await pet.locator('input[aria-label="输入运维问题"]').fill('检查 CPU')
    await pet.locator('button[aria-label="发送消息"]').dispatchEvent('click')
    assert.equal(await page.locator('.home-chat-section').count(), 0)
    assert.equal(await pet.locator('.pet-chat__message--user').count(), 1)
    await pet.locator('.pet-chat__message--assistant').filter({ hasText: '先检查 CPU 使用率。' }).waitFor()
    assert.equal(assistant.chats[0].providerKey, 'mini')
    assert.ok(await pet.locator('.pet-chat').isVisible())
    await pet.getByLabel('打开完整聊天', { exact: true }).click()
    await page.locator('.chat-page').waitFor()
    assert.equal(await page.locator('.ai-chat-message--user').count(), 1)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    assert.deepEqual(errors, [])
    console.log(`PASS spider chat flow ${width}px`)
    await page.close()
  }
} finally {
  await browser.close()
}
