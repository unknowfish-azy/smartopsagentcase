export const TEAM_ROLE_LABELS = Object.freeze({ owner: '团队负责人', admin: '副负责人', specialist: '专项负责人', member: '成员', viewer: '观察者' })
export const isTeamManager = role => role === 'owner' || role === 'admin' || role === 'root'
// Keep the original member-management contract; specialist appointment is exposed
// through the dedicated governance flow so legacy callers do not gain authority.
export const assignableRoles = role => role === 'owner' ? ['admin', 'member', 'viewer'] : role === 'admin' ? ['member', 'viewer'] : []
export const assignableSpecialist = role => role === 'owner' || role === 'admin'
export const canManageMember = (role, targetRole, self) => !self && targetRole !== 'owner' && assignableRoles(role).includes(targetRole)
