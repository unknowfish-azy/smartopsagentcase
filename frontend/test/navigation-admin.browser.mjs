import { chromium } from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>new URL(r.request().url()).pathname.startsWith('/api/')?r.fulfill({json:{code:200,data:r.request().url().includes('/auth/session')?{user:{id:99,username:'admin-review',role:'admin',portal:'admin'},csrfToken:'test'}: {items:[],total:0}}}):r.continue())
 await page.goto('http://127.0.0.1:5189/admin')
 await page.getByRole('button',{name:'搜索页面',exact:true}).click()
 const input=page.getByRole('combobox',{name:'搜索页面名称'});await input.fill('账户');await page.keyboard.press('Enter');await page.waitForURL('**/admin/users')
 await page.reload();await page.locator('.admin-tabs a[href="/admin/users"]').waitFor()
 assert.ok(await page.locator('.admin-nav-symbol').count()>0)
 await page.screenshot({path:'test-artifacts/menu-design/admin-light.png'})
 await page.getByRole('button',{name:'搜索页面',exact:true}).click();await input.fill('审计');await page.screenshot({path:'test-artifacts/menu-design/admin-search.png'})
 assert.deepEqual(errors,[]);console.log('PASS admin search, icons, tab persistence after refresh')
}finally {await browser.close()}
