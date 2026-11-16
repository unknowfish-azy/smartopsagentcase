/**
 * 终端输入总线：runtimeId → send 函数注册表。
 * OperationsTerminal 挂载时注册自己的 WebSocket send；命令片段等功能经此
 * 把文本送进真实终端输入通道（等同用户键盘输入），绝不绕过终端直接执行。
 */

const senders = new Map()

export function registerTerminalInput(runtimeId, sender) {
  if (!runtimeId || typeof sender !== 'function') return
  senders.set(runtimeId, sender)
}

export function unregisterTerminalInput(runtimeId) {
  senders.delete(runtimeId)
}

/** 向终端写文本（按键盘输入路径）。返回是否送达。 */
export function writeToTerminal(runtimeId, data) {
  const sender = senders.get(runtimeId)
  if (!sender || typeof data !== 'string') return false
  try {
    sender('INPUT', { data })
    return true
  } catch {
    return false
  }
}

export function hasTerminalInput(runtimeId) {
  return senders.has(runtimeId)
}
