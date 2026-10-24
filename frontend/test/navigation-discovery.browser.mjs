import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import fs from 'node:fs'
fs.mkdirSync('test-artifacts/menu-design',{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>new URL(r.request().url()).pathname.startsWith('/api/') ? r.fulfill({json:{code:200,data:r.request().url().includes('/auth/session')?{user:{id:99,username:'navigation-review',role:'operator',portal:'user'},csrfToken:'test'}:[]}}) : r.continue())
 await page.goto('http://127.0.0.1:5188/health')
 const trigger=page.getByRole('button',{name:'搜索页面',exact:true});await trigger.waitFor();await page.evaluate(()=>document.documentElement.dataset.theme='dark')
 await page.getByRole('button',{name:'展开主菜单',exact:true}).click()
 await page.screenshot({path:'test-artifacts/menu-design/sidebar-dark.png'})
 await trigger.click();const input=page.getByRole('combobox',{name:'搜索页面名称'});await input.fill('运行')
 assert.ok(await page.locator('dialog').getByRole('option').count()>0)
 await page.screenshot({path:'test-artifacts/menu-design/search-dark.png'})
 await page.keyboard.press('Escape');assert.equal(await trigger.evaluate(el=>el===document.activeElement),true)
 await page.keyboard.press('Control+k');await input.fill('no-such-page');assert.equal(await page.locator('dialog').getByRole('option').count(),0)
 await input.fill('运行');await page.keyboard.press('Enter');await page.waitForURL('**/operations/runs')
 for(const width of [375,768,1024,1440,1920]) {
  await page.setViewportSize({width,height:1000});await page.keyboard.press('Control+k');await input.fill('模型')
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow ${width}`)
  await page.screenshot({path:`test-artifacts/menu-design/search-${width}.png`});await page.keyboard.press('Escape')
 }
 await page.evaluate(()=>document.documentElement.dataset.theme='light');await page.keyboard.press('Control+k');await page.screenshot({path:'test-artifacts/menu-design/search-light.png'})
 assert.deepEqual(errors,[]);console.log('PASS: keyboard/search/focus/empty state/navigation, 5 widths, screenshots in both themes')
} finally {await browser.close()}


