import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { chromium } from 'playwright'
import { mockSession } from './helpers/session.mjs'
import { mockAssistant } from './helpers/assistant.mjs'

let browser
before(async () => {
  browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
})
after(async () => { await browser?.close() })

async function openPet({ width = 1440, theme = 'light', position } = {}) {
  const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
  await mockSession(page)
  await mockAssistant(page)
  await page.addInitScript(({ theme, position }) => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'pet-test' }))
    localStorage.setItem('smartops_theme', theme)
    if (position) localStorage.setItem('smartops_ops_spider_position', JSON.stringify(position))
    else localStorage.removeItem('smartops_ops_spider_position')
  }, { theme, position })
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
  await page.locator('.core-control').waitFor()
  return page
}

function assertSameBox(actual, expected) {
  for (const key of ['x', 'y', 'width', 'height']) {
    assert.ok(Math.abs(actual[key] - expected[key]) < 1, `${key} changed: ${expected[key]} -> ${actual[key]}`)
  }
}

async function assertInViewport(locator, width) {
  const boxes = await locator.evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect()
    return { x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom }
  }))
  assert.ok(boxes.length > 0)
  for (const box of boxes) assert.ok(box.x >= 0 && box.y >= 0 && box.right <= width && box.bottom <= 900, JSON.stringify(box))
}

test('every action remains stationary on hover and keyboard focus', async () => {
  const page = await openPet({ position: { x: 700, y: 400 } })
  try {
    const pet = page.locator('.ops-spider-pet')
    const petBox = await pet.boundingBox()
    await pet.locator('.core-control').click()
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    const buttons = pet.locator('.action-orbit button')
    assert.equal(await buttons.count(), 8)
    for (const button of await buttons.all()) {
      const beforeBox = await button.boundingBox()
      await button.hover()
      await page.waitForTimeout(180)
      assertSameBox(await button.boundingBox(), beforeBox)
      await button.focus()
      assertSameBox(await button.boundingBox(), beforeBox)
      assertSameBox(await pet.boundingBox(), petBox)
    }
  } finally { await page.close() }
})

for (const width of [375, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`menu, chat and context panel follow ${theme} theme at ${width}px`, async () => {
      const page = await openPet({ width, theme })
      try {
        const pet = page.locator('.ops-spider-pet')
        const beforeBox = await pet.boundingBox()
        await page.locator('.core-control').click()
        const buttons = page.locator('.action-orbit button')
        assert.equal(await buttons.count(), 8)
        await assertInViewport(buttons, width)
        assertSameBox(await pet.boundingBox(), beforeBox)
        const background = await buttons.first().evaluate(element => getComputedStyle(element).backgroundColor)
        assert.equal(background, theme === 'light' ? 'rgb(255, 255, 255)' : 'rgb(7, 16, 24)')
        const target = page.getByRole('button', { name: 'AI 对话', exact: true })
        await target.click()
        const chat = page.locator('.pet-chat')
        await chat.waitFor()
        await assertInViewport(chat, width)
        const chatBackground = await chat.evaluate(element => getComputedStyle(element).backgroundColor)
        assert.match(chatBackground, theme === 'light' ? /255, 255, 255/ : /7, 16, 24/)
        await page.getByRole('textbox', { name: '输入运维问题' }).fill('检查服务状态')
        assertSameBox(await pet.boundingBox(), beforeBox)
        await page.getByRole('button', { name: '关闭 AI 对话', exact: true }).click()
        await page.locator('.core-control').click({ button: 'right' })
        const context = page.locator('.context-menu')
        await context.waitFor()
        await assertInViewport(context, width)
        assert.match(await context.evaluate(element => getComputedStyle(element).backgroundColor), theme === 'light' ? /255, 255, 255/ : /7, 16, 24/)
      } finally { await page.close() }
    })
  }
}

test('theme changes update an already open panel without moving the pet', async () => {
  const page = await openPet()
  try {
    await page.locator('.core-control').click()
    const petBox = await page.locator('.ops-spider-pet').boundingBox()
    const firstButton = page.locator('.action-orbit button').first()
    await page.getByLabel('选择主题模式').selectOption('dark')
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark')
    assert.equal(await firstButton.evaluate(element => getComputedStyle(element).backgroundColor), 'rgb(7, 16, 24)')
    assertSameBox(await page.locator('.ops-spider-pet').boundingBox(), petBox)
    await page.getByRole('button', { name: 'AI 对话', exact: true }).click()
    await page.getByLabel('选择主题模式').selectOption('light')
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light')
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.pet-chat')).backgroundColor.includes('255, 255, 255'))
    assert.match(await page.locator('.pet-chat').evaluate(element => getComputedStyle(element).backgroundColor), /255, 255, 255/)
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.getByLabel('选择主题模式').selectOption('system')
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark')
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.pet-chat')).backgroundColor.includes('7, 16, 24'))
    assert.match(await page.locator('.pet-chat').evaluate(element => getComputedStyle(element).backgroundColor), /7, 16, 24/)
    await page.emulateMedia({ colorScheme: 'light' })
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light')
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.pet-chat')).backgroundColor.includes('255, 255, 255'))
    assert.match(await page.locator('.pet-chat').evaluate(element => getComputedStyle(element).backgroundColor), /255, 255, 255/)
  } finally { await page.close() }
})

test('open panels lock dragging, closing them restores direct dragging and click activation', async () => {
  const page = await openPet({ position: { x: 700, y: 400 } })
  try {
    const pet = page.locator('.ops-spider-pet')
    await page.locator('.core-control').click()
    const beforeBox = await pet.boundingBox()
    const center = { x: beforeBox.x + beforeBox.width / 2, y: beforeBox.y + beforeBox.height / 2 }
    await page.mouse.move(center.x, center.y)
    await page.mouse.down()
    await page.mouse.move(center.x - 100, center.y + 100, { steps: 6 })
    await page.mouse.up()
    assertSameBox(await pet.boundingBox(), beforeBox)
    await page.keyboard.press('Escape')
    assert.equal(await page.locator('.action-orbit').count(), 0)
    await page.mouse.move(center.x, center.y)
    await page.mouse.down()
    await page.mouse.move(center.x - 100, center.y + 100, { steps: 6 })
    await page.mouse.up()
    await page.waitForTimeout(250)
    const afterBox = await pet.boundingBox()
    assert.ok(Math.abs(afterBox.x - (beforeBox.x - 100)) < 1)
    assert.ok(Math.abs(afterBox.y - (beforeBox.y + 100)) < 1)
    await page.locator('.core-control').click()
    assert.equal(await page.locator('.action-orbit button').count(), 8)
    await page.getByRole('button', { name: '知识库', exact: true }).last().click()
    await page.waitForURL('**/knowledge')
    assert.equal(await page.locator('.action-orbit').count(), 0)
  } finally { await page.close() }
})

test('panels remain on screen near every corner and after resizing', async () => {
  for (const position of [{ x: 272, y: 20 }, { x: 1352, y: 20 }, { x: 272, y: 812 }]) {
    const page = await openPet({ position })
    try {
      await page.locator('.core-control').click()
      await assertInViewport(page.locator('.action-orbit button'), 1440)
      await page.getByRole('button', { name: 'AI 对话', exact: true }).click()
      await assertInViewport(page.locator('.pet-chat'), 1440)
      await page.setViewportSize({ width: 375, height: 900 })
      await page.waitForTimeout(300)
      await assertInViewport(page.locator('.pet-chat'), 375)
    } finally { await page.close() }
  }
})
