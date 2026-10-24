import { builtinPlugins, pluginCategories, pluginEntries } from './catalog.ts'
export const PLUGIN_STORAGE_KEY = 'smartops_plugin_workspace_v1'
const owns = (value, key) => Object.prototype.hasOwnProperty.call(value, key)
export function initialWorkspace() { return { version: 1, custom: [], installed: { 'ops-knowledge': true, 'ops-connections': true, 'ops-models': true } } }
export function catalogFor(state) { return [...builtinPlugins, ...state.custom] }
export function validateManifest(input: any, catalog: any): any {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('清单必须是 JSON 对象。')
  const allowed = ['id', 'name', 'version', 'description', 'category', 'entry', 'dependencies']
  if (Object.keys(input).some(key => !allowed.includes(key))) throw new Error('仅支持模板中的字段；清单不能包含脚本、地址或密钥。')
  const text = (key, max) => {
    if (typeof input[key] !== 'string' || !input[key].trim() || input[key].length > max) throw new Error(`${key} 必须是 1–${max} 字符的文本。`)
    return input[key].trim()
  }
  const id = text('id', 64)
  if (!/^[a-z][a-z0-9-]{2,63}$/.test(id) || ['constructor', 'prototype'].includes(id)) throw new Error('id 需为 3–64 位小写字母、数字或连字符。')
  if (catalog.some(item => item.id === id)) throw new Error('该插件 ID 已存在，请使用新的 ID。')
  const version = text('version', 30)
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('version 使用 1.0.0 格式。')
  if (!pluginCategories.includes(input.category)) throw new Error('请选择支持的插件分类。')
  if (!owns(pluginEntries, input.entry)) throw new Error('entry 必须是模板中的现有功能标识。')
  if (!Array.isArray(input.dependencies) || input.dependencies.length > 20 || input.dependencies.some(id => typeof id !== 'string' || !catalog.some(item => item.id === id))) throw new Error('dependencies 必须列出已存在的插件 ID。')
  return { id, name: text('name', 40), shortName: text('name', 40), version, description: text('description', 400), category: input.category, entry: input.entry, dependencies: [...new Set(input.dependencies)], icon: 'Grid', source: 'custom', capabilities: ['自定义功能入口'], boundary: '本地自定义清单，仅链接已有功能，不加载外部代码。' }
}
export function importManifest(state, text, sourceUrl = '') {
  if (text.length > 20000) throw new Error('清单不能超过 20,000 字符。')
  let input
  try { input = JSON.parse(text) } catch { throw new Error('JSON 格式不正确，请检查引号与逗号。') }
  const plugin = validateManifest(input, catalogFor(state))
  if (sourceUrl) plugin.sourceUrl = sourceUrl
  return { ...state, custom: [...state.custom, plugin] }
}
export function changePlugin(state, id, action) {
  const catalog = catalogFor(state), plugin = catalog.find(item => item.id === id)
  if (!plugin) throw new Error('插件不存在。')
  if (!['add', 'enable', 'disable', 'remove', 'delete'].includes(action)) throw new Error('不支持的操作。')
  const installed = { ...state.installed }
  if (action === 'add' || action === 'enable') {
    const missing = plugin.dependencies.filter(dep => installed[dep] !== true)
    if (missing.length) throw new Error(`请先添加并启用：${missing.map(id => catalog.find(item => item.id === id)?.name || id).join('、')}`)
    installed[id] = true
  } else {
    const dependents = catalog.filter(item => item.dependencies.includes(id) && (action === 'delete' || (action === 'disable' ? installed[item.id] === true : owns(installed, item.id))))
    if (dependents.length) throw new Error(`请先处理依赖此插件的条目：${dependents.map(item => item.name).join('、')}`)
    if (action === 'disable') installed[id] = false
    else delete installed[id]
  }
  if (action === 'delete' && plugin.source !== 'custom') throw new Error('内置插件仅可从工作区移除。')
  return { ...state, installed, custom: action === 'delete' ? state.custom.filter(item => item.id !== id) : state.custom }
}
export function decodeWorkspace(raw) {
  if (!raw) return initialWorkspace()
  const data = JSON.parse(raw)
  if (data?.version !== 1 || !Array.isArray(data.custom) || !data.installed || typeof data.installed !== 'object' || Array.isArray(data.installed)) throw new Error('保存的插件配置格式无效。')
  const state = { version: 1, custom: [], installed: {} }
  for (const item of data.custom) {
    const input = Object.fromEntries(['id', 'name', 'version', 'description', 'category', 'entry', 'dependencies'].map(key => [key, item[key]]))
    const plugin = validateManifest(input, catalogFor(state))
    if (typeof item.sourceUrl === 'string') plugin.sourceUrl = item.sourceUrl
    state.custom.push(plugin)
  }
  for (const item of catalogFor(state)) if (owns(data.installed, item.id) && typeof data.installed[item.id] === 'boolean') state.installed[item.id] = data.installed[item.id]
  for (const item of catalogFor(state)) if (state.installed[item.id] && item.dependencies.some(dep => !state.installed[dep])) state.installed[item.id] = false
  return state
}
