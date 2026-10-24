let pendingScript

export function loadTurnstile() {
  if (typeof window.turnstile?.render === 'function') return Promise.resolve(window.turnstile)
  if (pendingScript) return pendingScript
  pendingScript = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    let settled = false
    const finish = failure => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      script.onload = null
      script.onerror = null
      if (failure) {
        script.remove()
        pendingScript = undefined
        reject(failure)
      } else resolve(window.turnstile)
    }
    const timeout = setTimeout(() => finish(new Error('验证组件加载超时，请检查网络后重试')), 10000)
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => finish(typeof window.turnstile?.render === 'function' ? null : new Error('验证组件加载失败，请重试'))
    script.onerror = () => finish(new Error('无法连接验证服务，请检查网络后重试'))
    document.head.appendChild(script)
  })
  return pendingScript
}
