import request from '../utils/request.js'

const data = promise => promise.then(response => response.data)
const confirmation = password => ({ headers: { 'X-Admin-Password': password } })
export const mfaApi = {
  status: () => data(request.get('/api/admin/mfa')),
  setup: password => data(request.post('/api/admin/mfa/setup', {}, confirmation(password))),
  enable: (challenge, code, password) => data(request.post('/api/admin/mfa/enable', { challenge, code }, confirmation(password))),
  recovery: (code, password) => data(request.post('/api/admin/mfa/recovery', { code }, confirmation(password))),
  disable: (code, password) => data(request.post('/api/admin/mfa/disable', { code }, confirmation(password))),
  notices: () => data(request.get('/api/admin/mfa/notices')),
  readNotice: id => data(request.post(`/api/auth/mfa/notices/${encodeURIComponent(id)}/read`)),
}
