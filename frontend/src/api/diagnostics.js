import request from '../utils/request.js'

const data = promise => promise.then(response => response.data?.data ?? response.data)
export const diagnosticsApi = {
  health: () => data(request.get('/api/diagnostics/health')),
  adminHealth: () => data(request.get('/api/diagnostics/admin/health')),
  targets: () => data(request.get('/api/diagnostics/targets')),
  http: payload => data(request.post('/api/diagnostics/http', payload)),
  certificate: targetId => data(request.post('/api/diagnostics/certificate', { targetId }))
}
