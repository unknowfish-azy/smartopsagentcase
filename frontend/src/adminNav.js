// 管理员层导航配置（侧栏 + 面包屑 + 多标签页共用同一份）。
// 单个数据源避免侧栏与标签页标题漂移。

export const adminNavigation = [
  { label: '管理工作台', items: [{ path: '/admin', label: '管理总览' }] },
  { label: '身份与空间', items: [{ path: '/admin/users', label: '账户管理' }, { path: '/admin/governance', label: '管理员与授权' }, { path: '/admin/teams', label: '团队管理' }] },
  { label: '系统管理', items: [{ path: '/admin/system/dept', label: '部门管理' }, { path: '/admin/system/post', label: '岗位管理' }, { path: '/admin/system/role', label: '角色管理' }, { path: '/admin/system/menu', label: '菜单管理' }, { path: '/admin/system/dict', label: '字典管理' }, { path: '/admin/system/notice', label: '通知公告' }] },
  { label: '安全与审计', items: [{ path: '/admin/sessions', label: '活动会话' }, { path: '/admin/system/loginlog', label: '登录日志' }, { path: '/admin/audit', label: '审计记录' }, { path: '/admin/security', label: '二次认证' }] },
  // Agent 治理扩展：仅在真实契约就绪后才提供入口（知识质量因缺少评测版本契约暂不挂载）。
  { label: 'Agent 治理', items: [{ path: '/admin/approvals', label: '审批监督' }, { path: '/admin/models', label: '模型治理' }] },
  { label: '服务与部署', items: [{ path: '/admin/readiness', label: '服务接入检查' }] }
]

// 路径 → 标题 的扁平映射，供标签页/面包屑使用。
export const adminTitle = Object.fromEntries(adminNavigation.flatMap(group => group.items).map(item => [item.path, item.label]))

// 当前路径所属的导航分组（用于面包屑「分组 / 页面」）。
export function adminBreadcrumb(path) {
  for (const group of adminNavigation) {
    const item = group.items.find(i => i.path === path)
    if (item) return { group: group.label, item: item.label }
  }
  return null
}
