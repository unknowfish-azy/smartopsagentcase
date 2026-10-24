export function passwordError(password, role = 'operator', policy = {}) {
  const minimum = role === 'admin' ? (policy.adminPasswordMinLength || 16) : (policy.userPasswordMinLength || 12)
  const maximum = policy.passwordMaxBytes || 72
  if (password.length < minimum) return '密码至少需要 ' + minimum + ' 个字符'
  if (new TextEncoder().encode(password).length > maximum) return '密码不能超过 ' + maximum + ' 个 UTF-8 字节'
  return ''
}

export function registrationError(form, policy = {}) {
  if (!/^[a-zA-Z0-9._-]{3,64}$/.test(form.username)) return '账号须为 3–64 位字母、数字、点、下划线或短横线'
  const error = passwordError(form.password, 'operator', policy)
  if (error) return error
  if (form.password !== form.confirmPassword) return '两次输入的密码不一致'
  return ''
}
