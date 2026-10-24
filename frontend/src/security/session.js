import { shallowRef } from 'vue'
import request from '../utils/request.js'

export const currentSession = shallowRef(null)
let pendingSession

export function clearSession() {
  currentSession.value = null
  delete request.defaults.headers.common['X-CSRF-TOKEN']
  try { localStorage.removeItem('smartops_preview_auth') } catch {}
}

export async function loadSession() {
  if (pendingSession) return pendingSession
  pendingSession = request.get('/api/auth/session').then(response => {
    const { user, csrfToken } = response.data
    currentSession.value = user
    request.defaults.headers.common['X-CSRF-TOKEN'] = csrfToken
    try {
      if (user) {
        localStorage.setItem('smartops_preview_auth', JSON.stringify(user))
        localStorage.setItem('smartops_preview_user', user.username)
      } else localStorage.removeItem('smartops_preview_auth')
    } catch {}
    return user
  }).catch(error => { clearSession(); throw error }).finally(() => { pendingSession = null })
  return pendingSession
}

export async function loginSession(username, password, portal = 'user', humanToken = '') {
  await loadSession()
  const response = await request.post('/api/auth/login', { username, password, portal, humanToken })
  if (response.data?.mfaRequired === true) {
    clearSession()
    return response.data
  }
  return loadSession()
}

export async function completeMfa(challenge, code) {
  await loadSession()
  await request.post('/api/auth/mfa/complete', { challenge, code })
  return loadSession()
}

export async function cancelMfa() {
  await loadSession()
  await request.post('/api/auth/mfa/cancel')
}

export async function changePassword(currentPassword, newPassword) {
  await loadSession()
  await request.post('/api/auth/password', { currentPassword, newPassword })
  clearSession()
}

export async function registrationPolicy() {
  return (await request.get('/api/auth/registration')).data
}

export async function humanVerificationPolicy(action) {
  await loadSession()
  return (await request.get('/api/auth/human-verification', { params: { action } })).data
}

/**
 * 本地图形点选人机验证：提交点击坐标，换取一次性 humanToken。
 *
 * @param {string} action login / admin_login / register
 * @param {string} nonce  策略下发的会话挑战
 * @param {Array<{x:number,y:number}>} clicks 按提示顺序的点击坐标（viewBox 坐标系）
 * @returns {Promise<{targets:number, token:string}>}
 */
export async function humanVerificationProof(action, nonce, clicks) {
  await loadSession()
  return (await request.post('/api/auth/human-verification/verify', { action, nonce, clicks })).data
}

export async function registerAccount({ username, password, confirmPassword, humanToken = '' }) {
  await loadSession()
  return (await request.post('/api/auth/register', { username, password, confirmPassword, humanToken })).data
}

request.interceptors.request.use(config => {
  if (currentSession.value?.mustChangePassword && !['/api/auth/session', '/api/auth/login', '/api/auth/password', '/api/auth/logout'].includes(config.url)) {
    return Promise.reject(new Error('请先修改密码后重新登录'))
  }
  return config
})

export async function logoutSession() {
  await loadSession()
  await request.post('/api/auth/logout')
  clearSession()
}
