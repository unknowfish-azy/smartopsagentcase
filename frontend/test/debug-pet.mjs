import { chromium } from 'playwright';
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true });
const page = await browser.newPage({viewport:{width:375,height:900}});
await page.route('**/api/auth/session', r=>r.fulfill({json:{code:200,data:{user:{id:1,username:'pet-test',role:'operator',portal:'user',mustChangePassword:false,authVersion:0},csrfToken:'x'}}}));
await page.route('**/api/assistant/options', r=>r.fulfill({json:{code:200,data:{selectedKey:'mini',options:[{key:'mini',name:'智维 Mini',kind:'builtin',model:'qwen3:1.7b',enabled:true,available:true,status:'ready'}]}}}));
await page.addInitScript(()=>{localStorage.setItem('smartops_preview_auth',JSON.stringify({username:'pet-test'}));localStorage.setItem('smartops_theme','light')});
await page.goto('http://127.0.0.1:5173/',{waitUntil:'domcontentloaded'}); await page.locator('.core-control').waitFor(); await page.locator('.core-control').click(); console.log('actions',await page.locator('.action-orbit button').count(), await page.locator('.action-orbit button').allTextContents()); await page.getByRole('button',{name:'AI 对话',exact:true}).click(); await page.waitForTimeout(500); console.log('chat',await page.locator('.pet-chat').count(), await page.locator('.pet-chat').evaluate(e=>({display:getComputedStyle(e).display,bg:getComputedStyle(e).backgroundColor,rect:e.getBoundingClientRect().toJSON(),html:e.outerHTML.slice(0,300)})).catch(e=>String(e))); await page.screenshot({path:'D:/SmartOpsAgent/test-artifacts/debug-pet.png',fullPage:true}); await browser.close();


