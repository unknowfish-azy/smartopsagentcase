import request from '../utils/request.ts'

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
export const teamInviteLinksApi = {
  list: id => data(request.get(`${base(id)}/invite-links`)),
  create: (id, role) => data(request.post(`${base(id)}/invite-links`, { role })),
  preview: token => data(request.get(`/api/teams/invite-links/${segment(token)}`)),
  accept: token => data(request.post(`/api/teams/invite-links/${segment(token)}/accept`)),
  revoke: (id, linkId) => data(request.delete(`${base(id)}/invite-links/${segment(linkId)}`))
}
export const teamSharesApi = {
  list: (id, resourceType = 'knowledge') => data(request.get(`${base(id)}/shares`, { params: { resourceType } })),
  share: (id, resourceType, resourceId) => data(request.post(`${base(id)}/shares`, { resourceType, resourceId })),
  unshare: (id, resourceType, resourceId) => data(request.delete(`${base(id)}/shares/${segment(resourceType)}/${segment(resourceId)}`)),
  knowledge: (id, libraryId) => data(request.get(`${base(id)}/shares/knowledge/${segment(libraryId)}`)),
  knowledgeEntries: (id, libraryId, params) => data(request.get(`${base(id)}/shares/knowledge/${segment(libraryId)}/entries`, { params }))
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
