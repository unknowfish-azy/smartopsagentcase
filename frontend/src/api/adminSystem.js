import request from '../utils/request.js'

// 管理层系统管理 API：部门/岗位/角色/菜单/字典/公告/登录日志。
// 全部位于 /api/admin/system/**，由后端 hasRole("ADMIN") + AdminConfirmationFilter 守卫：
// 非 GET 请求必须携带 X-Admin-Password（当前管理员密码），否则 403。
const data = promise => promise.then(response => response.data)
// 管理员复核密码：每次写操作都要传，后端会校验当前管理员密码。
const verification = password => ({ headers: { 'X-Admin-Password': password } })

export const systemApi = {
  /* 部门 */
  depts: () => data(request.get('/api/admin/system/depts')),
  createDept: (body, adminPassword) => data(request.post('/api/admin/system/depts', body, verification(adminPassword))),
  updateDept: (id, body, adminPassword) => data(request.put(`/api/admin/system/depts/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deleteDept: (id, adminPassword) => data(request.delete(`/api/admin/system/depts/${encodeURIComponent(id)}`, verification(adminPassword))),
  deptStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/depts/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),

  /* 岗位 */
  posts: () => data(request.get('/api/admin/system/posts')),
  createPost: (body, adminPassword) => data(request.post('/api/admin/system/posts', body, verification(adminPassword))),
  updatePost: (id, body, adminPassword) => data(request.put(`/api/admin/system/posts/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deletePost: (id, adminPassword) => data(request.delete(`/api/admin/system/posts/${encodeURIComponent(id)}`, verification(adminPassword))),
  postStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/posts/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),

  /* 角色 */
  roles: () => data(request.get('/api/admin/system/roles')),
  createRole: (body, adminPassword) => data(request.post('/api/admin/system/roles', body, verification(adminPassword))),
  updateRole: (id, body, adminPassword) => data(request.put(`/api/admin/system/roles/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deleteRole: (id, adminPassword) => data(request.delete(`/api/admin/system/roles/${encodeURIComponent(id)}`, verification(adminPassword))),
  roleStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/roles/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),
  roleMenus: id => data(request.get(`/api/admin/system/roles/${encodeURIComponent(id)}/menus`)),
  grantMenus: (id, menuIds, adminPassword) => data(request.put(`/api/admin/system/roles/${encodeURIComponent(id)}/menus`, { menuIds }, verification(adminPassword))),

  /* 菜单 */
  menus: () => data(request.get('/api/admin/system/menus')),
  createMenu: (body, adminPassword) => data(request.post('/api/admin/system/menus', body, verification(adminPassword))),
  updateMenu: (id, body, adminPassword) => data(request.put(`/api/admin/system/menus/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deleteMenu: (id, adminPassword) => data(request.delete(`/api/admin/system/menus/${encodeURIComponent(id)}`, verification(adminPassword))),
  menuStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/menus/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),

  /* 字典 */
  dictTypes: () => data(request.get('/api/admin/system/dicts/types')),
  createDictType: (body, adminPassword) => data(request.post('/api/admin/system/dicts/types', body, verification(adminPassword))),
  updateDictType: (id, body, adminPassword) => data(request.put(`/api/admin/system/dicts/types/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deleteDictType: (id, adminPassword) => data(request.delete(`/api/admin/system/dicts/types/${encodeURIComponent(id)}`, verification(adminPassword))),
  dictTypeStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/dicts/types/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),
  dictData: type => data(request.get(`/api/admin/system/dicts/${encodeURIComponent(type)}/data`)),
  createDictData: (body, adminPassword) => data(request.post('/api/admin/system/dicts/data', body, verification(adminPassword))),
  updateDictData: (id, body, adminPassword) => data(request.put(`/api/admin/system/dicts/data/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  deleteDictData: (id, adminPassword) => data(request.delete(`/api/admin/system/dicts/data/${encodeURIComponent(id)}`, verification(adminPassword))),
  dictDataStatus: (id, status, adminPassword) => data(request.put(`/api/admin/system/dicts/data/${encodeURIComponent(id)}/status`, { status }, verification(adminPassword))),

  /* 公告 */
  notices: includeDraft => data(request.get('/api/admin/system/notices', { params: { includeDraft } })),
  createNotice: (body, adminPassword) => data(request.post('/api/admin/system/notices', body, verification(adminPassword))),
  updateNotice: (id, body, adminPassword) => data(request.put(`/api/admin/system/notices/${encodeURIComponent(id)}`, body, verification(adminPassword))),
  publishNotice: (id, adminPassword) => data(request.post(`/api/admin/system/notices/${encodeURIComponent(id)}/publish`, {}, verification(adminPassword))),
  deleteNotice: (id, adminPassword) => data(request.delete(`/api/admin/system/notices/${encodeURIComponent(id)}`, verification(adminPassword))),

  /* 登录日志 */
  loginLogs: params => data(request.get('/api/admin/system/login-logs', { params }))
}
