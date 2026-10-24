import request from '../utils/request.js'

const data = promise => promise.then(response => response.data)
const segment = value => encodeURIComponent(value)
const base = id => `/api/teams/${segment(id)}`
export const teamApi = {
  list: params => data(request.get('/api/teams', { params })),
  create: input => data(request.post('/api/teams', input)),
  detail: id => data(request.get(base(id))),
  update: (id, input) => data(request.put(base(id), input)),
  invitations: params => data(request.get('/api/teams/invitations', { params })),
  invite: (id, input) => data(request.post(`${base(id)}/invitations`, input)),
  respond: (id, accept) => data(request.post(`/api/teams/invitations/${segment(id)}/respond`, { accept })),
  cancelInvite: (id, invitationId) => data(request.delete(`${base(id)}/invitations/${segment(invitationId)}`)),
  changeRole: (id, userId, role) => data(request.put(`${base(id)}/members/${segment(userId)}`, { role })),
  removeMember: (id, userId) => data(request.delete(`${base(id)}/members/${segment(userId)}`))
  ,activity: (id, params) => data(request.get(`${base(id)}/activity`, { params }))
}
export const adminTeamsApi = {
  list: params => data(request.get('/api/admin/teams', { params })),
  members: id => data(request.get(`/api/admin/teams/${segment(id)}/members`)),
  setStatus: (id, status, password) => data(request.put(`/api/admin/teams/${segment(id)}/status`, { status }, { headers: { 'X-Admin-Password': password } }))
}
export const teamNotificationsApi = {
  list: (unreadOnly = false) => data(request.get('/api/team-notifications', { params: { unreadOnly } })),
  markRead: id => data(request.post(`/api/team-notifications/${segment(id)}/read`))
}
