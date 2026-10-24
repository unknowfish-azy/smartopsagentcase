// Pure workspace rules; transport remains in the API and terminal components.
export function visibleRuntimeIds(tabs, active, layout) {
  if (!tabs.some(tab => tab.runtimeId === active)) return []
  return layout === 'SINGLE' ? [active] : [active, ...tabs.map(tab => tab.runtimeId).filter(id => id !== active)].slice(0, 4)
}
export function remoteChild(directory, name) {
  if (!name || name === '.' || name === '..' || /[\\/\x00-\x1f]/.test(name)) throw new Error('请输入单个文件名，不能包含路径或控制字符')
  return `${directory.replace(/\/$/, '')}/${name}`
}
export function terminalEndpoint(base, origin) {
  const url = new URL(base || '/', origin)
  url.protocol = ['https:', 'wss:'].includes(url.protocol) ? 'wss:' : 'ws:'
  url.pathname = `${url.pathname.replace(/\/$/, '')}/ws/operations/terminal`
  url.search = ''; url.hash = ''
  return url.toString()
}
