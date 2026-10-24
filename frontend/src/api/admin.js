import request from '../utils/request.js'

export const AUDIT_ACTIONS = Object.freeze([
  { value: 'LOGIN', label: '登录' }, { value: 'LOGOUT', label: '退出' },
  { value: 'CREATE_USER', label: '创建账号' }, { value: 'UPDATE_USER', label: '修改账号' },
  { value: 'RESET_PASSWORD', label: '重置密码' }, { value: 'CHANGE_PASSWORD', label: '修改密码' },
  { value: 'REVOKE_SESSION', label: '撤销会话' },
  { value: 'REGISTER', label: '普通账号注册' }, { value: 'REGISTRATION_POLICY', label: '注册策略' },
  { value: 'ADMIN_VERIFY', label: '管理员身份复核' }, { value: 'HUMAN_VERIFY', label: '人机验证拦截' },
  { value: 'MFA_ENABLE', label: '绑定二次认证' }, { value: 'MFA_DISABLE', label: '关闭二次认证' },
  { value: 'MFA_VERIFY', label: '二次认证验证' }, { value: 'MFA_RECOVERY_ROTATE', label: '重生成恢复码' }, { value: 'MFA_RECOVERY_USE', label: '使用恢复码' },
  { value: 'TEAM_CREATE', label: '创建团队' }, { value: 'TEAM_UPDATE', label: '修改团队' },
  { value: 'TEAM_INVITE', label: '邀请成员' }, { value: 'TEAM_INVITE_RESPOND', label: '处理团队邀请' },
  { value: 'TEAM_INVITE_CANCEL', label: '撤销团队邀请' }, { value: 'TEAM_MEMBER_ROLE', label: '团队角色变更' },
  { value: 'TEAM_MEMBER_REMOVE', label: '移除或退出团队' }, { value: 'TEAM_STATUS', label: '冻结或恢复团队' },
  { value: 'CHAT_CONVERSATION_CREATE', label: '创建附件会话' }, { value: 'CHAT_CONVERSATION_DELETE', label: '删除附件会话' },
  { value: 'CHAT_ATTACHMENT_UPLOAD', label: '上传私有附件' }
])
export const AUDIT_OUTCOMES = Object.freeze([
  { value: 'SUCCESS', label: '成功' }, { value: 'FAILURE', label: '失败' }, { value: 'DENIED', label: '拒绝' }
])

const data = promise => promise.then(response => response.data)
const verification = password => ({ headers: { 'X-Admin-Password': password } })
export const adminApi = {
  overview: () => data(request.get('/api/admin/overview')),
  users: params => data(request.get('/api/admin/users', { params })),
  governance: () => data(request.get('/api/admin/governance')),
  appointAdmin: (id, input, adminPassword) => data(request.post(`/api/admin/governance/${encodeURIComponent(id)}`, input, verification(adminPassword))),
  revokeAdmin: (id, adminPassword) => data(request.delete(`/api/admin/governance/${encodeURIComponent(id)}`, verification(adminPassword))),
  transferRoot: (id, adminPassword) => data(request.post(`/api/admin/governance/transfer/${encodeURIComponent(id)}`, {}, verification(adminPassword))),
  createUser: (account, adminPassword) => data(request.post('/api/admin/users', account, verification(adminPassword))),
  updateUser: (id, changes, adminPassword) => data(request.put(`/api/admin/users/${encodeURIComponent(id)}`, changes, verification(adminPassword))),
  resetPassword: (id, password, adminPassword) => data(request.post(`/api/admin/users/${encodeURIComponent(id)}/reset-password`, { password }, verification(adminPassword))),
  sessions: () => data(request.get('/api/admin/sessions')),
  revokeSession: (id, adminPassword) => data(request.delete(`/api/admin/sessions/${encodeURIComponent(id)}`, verification(adminPassword))),
  registration: () => data(request.get('/api/admin/registration')),
  updateRegistration: (enabled, adminPassword) => data(request.put('/api/admin/registration', { enabled }, verification(adminPassword))),
  audit: params => data(request.get('/api/admin/audit', { params }))
}
