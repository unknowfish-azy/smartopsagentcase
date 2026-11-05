import request from '../utils/request.ts'

// 与 SecurityAuditService.ACTIONS 保持同序同集：筛选下拉直接消费服务端动作目录，
// 前端多写或少写一个都会让精确筛选被服务端拒绝（400 审计事件类型无效）。
export const AUDIT_ACTIONS = Object.freeze([
  { value: 'LOGIN', label: '登录' }, { value: 'LOGOUT', label: '退出' },
  { value: 'CREATE_USER', label: '创建账号' }, { value: 'UPDATE_USER', label: '修改账号' },
  { value: 'RESET_PASSWORD', label: '重置密码' }, { value: 'CHANGE_PASSWORD', label: '修改密码' },
  { value: 'PROFILE_UPDATE', label: '修改个人资料' }, { value: 'REVOKE_SESSION', label: '撤销会话' },
  { value: 'REGISTER', label: '普通账号注册' }, { value: 'REGISTRATION_POLICY', label: '注册策略' },
  { value: 'ADMIN_VERIFY', label: '管理员身份复核' }, { value: 'HUMAN_VERIFY', label: '人机验证拦截' },
  { value: 'MFA_ENABLE', label: '绑定二次认证' }, { value: 'MFA_DISABLE', label: '关闭二次认证' },
  { value: 'MFA_VERIFY', label: '二次认证验证' }, { value: 'MFA_RECOVERY_ROTATE', label: '重生成恢复码' }, { value: 'MFA_RECOVERY_USE', label: '使用恢复码' },
  { value: 'TEAM_CREATE', label: '创建团队' }, { value: 'TEAM_UPDATE', label: '修改团队' },
  { value: 'TEAM_INVITE', label: '邀请成员' }, { value: 'TEAM_INVITE_RESPOND', label: '处理团队邀请' },
  { value: 'TEAM_INVITE_CANCEL', label: '撤销团队邀请' },
  { value: 'TEAM_INVITE_LINK_CREATE', label: '生成团队邀请链接' }, { value: 'TEAM_INVITE_LINK_JOIN', label: '通过邀请链接加入' },
  { value: 'TEAM_INVITE_LINK_REVOKE', label: '撤销团队邀请链接' },
  { value: 'TEAM_MEMBER_ROLE', label: '团队角色变更' }, { value: 'TEAM_MEMBER_REMOVE', label: '移除或退出团队' }, { value: 'TEAM_STATUS', label: '冻结或恢复团队' },
  { value: 'TEAM_AGENT_RUN_CREATE', label: '提交 Agent 运行' }, { value: 'TEAM_AGENT_RUN_APPROVE', label: '审批 Agent 运行' },
  { value: 'TEAM_AGENT_RUN_EXECUTE', label: '执行 Agent 运行' }, { value: 'TEAM_AGENT_RUN_FINISH', label: '结束 Agent 运行' },
  { value: 'CHAT_CONVERSATION_CREATE', label: '创建附件会话' }, { value: 'CHAT_CONVERSATION_DELETE', label: '删除附件会话' },
  { value: 'CHAT_ATTACHMENT_UPLOAD', label: '上传私有附件' },
  { value: 'DEPT_CREATE', label: '新增部门' }, { value: 'DEPT_UPDATE', label: '修改部门' }, { value: 'DEPT_DELETE', label: '删除部门' }, { value: 'DEPT_STATUS', label: '启停部门' },
  { value: 'POST_CREATE', label: '新增岗位' }, { value: 'POST_UPDATE', label: '修改岗位' }, { value: 'POST_DELETE', label: '删除岗位' }, { value: 'POST_STATUS', label: '启停岗位' },
  { value: 'ROLE_CREATE', label: '新增角色' }, { value: 'ROLE_UPDATE', label: '修改角色' }, { value: 'ROLE_DELETE', label: '删除角色' },
  { value: 'ROLE_STATUS', label: '启停角色' }, { value: 'ROLE_MENU_GRANT', label: '角色菜单授权' },
  { value: 'MENU_CREATE', label: '新增菜单' }, { value: 'MENU_UPDATE', label: '修改菜单' }, { value: 'MENU_DELETE', label: '删除菜单' }, { value: 'MENU_STATUS', label: '启停菜单' },
  { value: 'DICT_TYPE_CREATE', label: '新增字典类型' }, { value: 'DICT_TYPE_UPDATE', label: '修改字典类型' }, { value: 'DICT_TYPE_DELETE', label: '删除字典类型' }, { value: 'DICT_TYPE_STATUS', label: '启停字典类型' },
  { value: 'DICT_DATA_CREATE', label: '新增字典数据' }, { value: 'DICT_DATA_UPDATE', label: '修改字典数据' }, { value: 'DICT_DATA_DELETE', label: '删除字典数据' }, { value: 'DICT_DATA_STATUS', label: '启停字典数据' },
  { value: 'NOTICE_CREATE', label: '新增通知' }, { value: 'NOTICE_UPDATE', label: '修改通知' }, { value: 'NOTICE_DELETE', label: '删除通知' }, { value: 'NOTICE_PUBLISH', label: '发布通知' },
  { value: 'PLATFORM_ADMIN_APPOINT', label: '任命平台管理员' }, { value: 'PLATFORM_ADMIN_REVOKE', label: '撤销平台管理员' },
  { value: 'PLATFORM_ROOT_TRANSFER', label: '转移平台主管理员' }
])
export const AUDIT_OUTCOMES = Object.freeze([
  { value: 'SUCCESS', label: '成功' }, { value: 'FAILURE', label: '失败' }, { value: 'DENIED', label: '拒绝' }
])

const data = promise => promise.then(response => response.data)
const verification = password => ({ headers: { 'X-Admin-Password': password } })
export const adminApi = {
  overview: () => data(request.get('/api/admin/overview')),
  workbench: () => data(request.get('/api/admin/workbench')),
  modelGovernance: () => data(request.get('/api/admin/model-governance')),
  users: params => data(request.get('/api/admin/users', { params })),
  userContext: id => data(request.get(`/api/admin/users/${encodeURIComponent(id)}/context`)),
  governance: () => data(request.get('/api/admin/governance')),
  capabilities: () => data(request.get('/api/admin/governance/capabilities')),
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
  audit: params => data(request.get('/api/admin/audit', { params })),
  auditDetail: id => data(request.get(`/api/admin/audit/${encodeURIComponent(id)}`))
}
