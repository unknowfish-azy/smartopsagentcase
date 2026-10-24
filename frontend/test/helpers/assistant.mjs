export const miniOption = { key: 'mini', name: '智维 Mini', kind: 'builtin', model: 'qwen3:1.7b', enabled: true, available: true, status: 'ready', detail: '本地运行时可用', timeoutSeconds: 120 }
export const externalOption = { key: 'connection:7', name: '我的外部模型', kind: 'connection', model: 'external-test', enabled: true, available: true, status: 'configured', detail: '已配置，未实时验证', timeoutSeconds: 60 }

export async function blockLiveApi(page) {
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { code: 200, data: [] } }))
  await page.routeWebSocket('**/*', socket => socket.close())
}

export async function mockAssistant(page, state = {}) {
  state.options ??= [miniOption]
  state.selectedKey ??= 'mini'
  state.chats ??= []
  state.preferences ??= []
  await page.route('**/api/assistant/options', route => route.fulfill({ json: { code: 200, data: { selectedKey: state.selectedKey, options: state.options } } }))
  await page.route('**/api/assistant/preference', route => {
    const { providerKey } = route.request().postDataJSON()
    state.preferences.push(providerKey)
    state.selectedKey = providerKey
    return route.fulfill({ json: { code: 200, data: { selectedKey: providerKey } } })
  })
  await page.route('**/api/assistant/chat', route => {
    const payload = route.request().postDataJSON()
    state.chats.push(payload)
    return route.fulfill({ json: { code: 200, data: { content: '已收到：' + payload.message, providerKey: payload.providerKey, providerName: payload.providerKey === 'mini' ? '智维 Mini' : '我的外部模型', model: 'test-model', citations: [], readOnly: true } } })
  })
  return state
}
