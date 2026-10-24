import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/model-integrations', { recursive: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    const errors = [], updates = [], invocations = []
    let items = [], fail = false, failSave = false, failInvoke = false
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({username:'model-ui-check'}))
      localStorage.setItem('smartops_theme', 'dark')
    })
    await page.route('**/api/model-connections**', async route => {
      const request = route.request(), method = request.method(), path = new URL(request.url()).pathname
      const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS' }
      if (method === 'OPTIONS') return route.fulfill({status:204,headers})
      if (fail) return route.fulfill({status:503,headers,json:{message:'offline'}})
      if (path.endsWith('/invoke')) {
        if (failInvoke) return route.fulfill({status:502,headers,json:{message:'provider unavailable'}})
        invocations.push(request.postDataJSON())
        return route.fulfill({headers,json:{connectionId:1,content:'测试回复：先检查日志与服务状态。',usage:{total_tokens:24}}})
      }
      if (method === 'POST') {
        if (failSave) return route.fulfill({status:503,headers,json:{message:'save unavailable'}})
        const {apiKey, ...data} = request.postDataJSON()
        assert.equal(apiKey, 'test-only-key')
        items.push({...data,id:1,apiKeyMasked:'****-key'})
        return route.fulfill({headers,json:items[0]})
      }
      if (method === 'PUT') {
        const payload=request.postDataJSON(); updates.push(payload)
        items[0]={...items[0],...payload}
        return route.fulfill({headers,json:items[0]})
      }
      if (method === 'DELETE') {items=[]; return route.fulfill({status:204,headers})}
      return route.fulfill({headers,json:items})
    })
    await page.goto('http://127.0.0.1:5174/model-settings',{waitUntil:'networkidle'})
    assert.equal(await page.locator('.integration-card').count(),1)
    assert.notEqual(await page.locator('.connection-line').first().evaluate(el => getComputedStyle(el).stroke),'none')
    await page.locator('.add-button').click()
    const dialog = page.getByRole('dialog').filter({has:page.getByRole('button',{name:'保存连接',exact:true})})
    await dialog.getByRole('button',{name:'保存连接',exact:true}).click()
    assert.equal(await dialog.locator('[aria-invalid=true]').count(),4)
    await dialog.getByLabel('连接名称',{exact:true}).fill('测试连接')
    await dialog.getByLabel('Base URL',{exact:true}).fill('https://gateway.example/v1')
    await dialog.getByLabel('模型 ID',{exact:true}).fill('model-test')
    await dialog.getByLabel('API Key',{exact:true}).fill('test-only-key')
    failSave=true
    await dialog.getByRole('button',{name:'保存连接',exact:true}).click()
    await dialog.getByRole('alert').waitFor()
    assert.equal(await dialog.getByLabel('连接名称',{exact:true}).inputValue(),'测试连接')
    assert.equal(items.length,0)
    failSave=false
    await dialog.getByRole('button',{name:'保存连接',exact:true}).click()
    await page.locator('.model-card').waitFor()
    await page.locator('.model-card').getByRole('button',{name:'编辑',exact:true}).click()
    assert.equal(await dialog.getByLabel('API Key',{exact:true}).inputValue(),'')
    await dialog.getByLabel('连接名称',{exact:true}).fill('已编辑连接')
    await dialog.getByRole('button',{name:'保存连接',exact:true}).click()
    await page.getByRole('heading',{name:'已编辑连接',exact:true}).waitFor()
    assert.equal('apiKey' in updates[0],false)
    await page.getByLabel('搜索模型',{exact:true}).fill('no-match')
    assert.equal(await page.locator('.model-card').count(),0)
    await page.getByLabel('搜索模型',{exact:true}).fill('')
    await page.locator('.model-card').getByRole('button',{name:'测试模型',exact:true}).click()
    await page.getByRole('button',{name:'发送测试',exact:true}).click()
    await page.locator('.test-output').waitFor()
    assert.match(await page.locator('.test-output').innerText(),/24 tokens/)
    assert.equal(invocations.length,1)
    assert.equal('apiKey' in invocations[0],false)
    failInvoke=true
    await page.getByRole('button',{name:'发送测试',exact:true}).click()
    await page.getByRole('dialog').getByRole('alert').waitFor()
    assert.equal(await page.locator('.test-output').count(),0,'Failed retest must clear the previous successful reply')
    failInvoke=false
    await page.getByRole('button',{name:'发送测试',exact:true}).click()
    await page.locator('.test-output').waitFor()
    await page.getByRole('dialog').filter({has:page.locator('.test-output')}).getByRole('button',{name:'Close this dialog'}).click()
    await page.locator('.model-card').getByRole('button',{name:'停用',exact:true}).click()
    await page.locator('.model-card').getByRole('button',{name:'启用',exact:true}).waitFor()
    assert.equal(await page.locator('.model-card').getByRole('button',{name:'测试模型',exact:true}).isDisabled(),true)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true)
    await page.evaluate(() => scrollTo(0,0))
    await page.screenshot({path:`test-artifacts/model-integrations/${width}-dark.png`,fullPage:true})
    await page.getByLabel('选择主题模式').selectOption('light')
    await page.evaluate(() => scrollTo(0,0))
    await page.screenshot({path:`test-artifacts/model-integrations/${width}-light.png`,fullPage:true})
    await page.locator('.model-card').getByRole('button',{name:'删除',exact:true}).click()
    await page.getByRole('button',{name:'删除',exact:true}).last().click()
    await page.waitForFunction(() => !document.querySelector('.model-card'))
    fail=true
    await page.getByRole('button',{name:'刷新列表',exact:true}).click()
    await page.getByText('暂时无法读取模型连接',{exact:true}).waitFor()
    assert.equal(await page.evaluate(() => JSON.stringify(localStorage).includes('test-only-key')),false)
    assert.deepEqual(errors,[])
    console.log(`PASS ${width}px create/edit/filter/invoke/toggle/delete/offline, themes and secret handling (mock API)`)
    await page.close()
  }
} finally { await browser.close() }
