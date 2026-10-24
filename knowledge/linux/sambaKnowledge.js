// Samba / SMB / CIFS reference pack from the user-provided teaching material.
// Lab actions such as disabling firewalld or SELinux are not production fixes.
const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'linux.samba.' + id, domain: 'linux', platform: 'Linux / Windows',
  service: 'samba', type: 'SAMBA / SMB / CIFS KNOWLEDGE', title, section,
  summary, content, tags: ['Samba', 'SMB', 'CIFS', ...tags],
  source: '用户提供的 Samba 文件共享教学材料', version: 'Reference pack',
  risk, executionAllowed: false
})

export const sambaEntries = [
  entry('model', 'Samba、SMB/CIFS 与文件共享选型', '01 / 基础概念',
    'Samba 通过 SMB/CIFS 提供 Windows 与 Linux 间的共享访问；要区分文件传输和像本地目录一样挂载。',
    '[SRC] FTP 偏文件传输，NFS 偏 Linux↔Linux 挂载，Samba 偏 Windows↔Linux 局域网共享。SMB（Server Message Block）也称 CIFS，可用于共享文件和打印机，并支持并发访问。\n[OPS] 选择前先问：需要一次性传输，还是持续使用远程目录？客户端是 Windows 还是 Linux？Linux 客户端应区分 smbclient（交互访问）与 mount.cifs（挂载）。不要仅因出现“挂载”就判断为 NFS。',
    ['FTP', 'NFS', 'Windows', 'Linux', 'file sharing']),
  entry('services', 'smbd、nmbd 与网络端口', '02 / 服务与网络',
    'smbd 负责共享和文件传输，nmbd 负责传统 NetBIOS 名称服务；服务状态要分开验证。',
    '[SRC] smbd 对应共享目录、权限和文件传输，涉及 TCP 139/445；nmbd 负责名称解析，涉及 UDP 137/138。服务文件示例为 smb.service、nmb.service，程序为 /usr/sbin/smbd、/usr/sbin/nmbd。\n[OPS] systemctl status smb、systemctl status nmb；再用 smbclient -L //<server>/ -U <user> 判断共享发现。nmbd 异常不自动等于所有 SMB 直接访问都失败，需结合访问方式和端口证据。',
    ['smbd', 'nmbd', 'TCP 139', 'TCP 445', 'UDP 137', 'UDP 138', 'NetBIOS']),
  entry('config', 'smb.conf 与共享对象模型', '03 / 配置',
    '从 [global]、共享标签、path、认证和访问控制共同决定最终行为。',
    '[SRC] 主配置为 /etc/samba/smb.conf；常见段落包括 [global]、[homes]、[printers] 和自定义共享。[global] 可包含 workgroup、server string、log file、max log size、security、passdb backend、load printers、cups options。\n共享示例：[smb_share] comment = samba service; path = /samba/share; guest ok = no; writable = yes。guest ok 与 public 在材料中表达匿名访问开关。\n[OPS] 配置文件正确不等于服务已重新加载，也不等于底层 Linux 目录可写。修改后做配置语法检查（testparm -s）并按审批 reload/restart，再进行客户端复验。',
    ['smb.conf', 'global', 'path', 'guest ok', 'public', 'testparm']),
  entry('auth', 'Linux 用户、Samba 认证与共享授权', '04 / 身份与认证',
    'useradd 创建 Linux 用户不等于已建立 Samba 认证，更不等于已获共享授权。',
    '[SRC] useradd user01 创建 Linux 用户，再用 smbpasswd -a user01 加入 Samba 认证体系。security=user 表示用户名密码认证，passdb backend=tdbsam 是教学示例。\n[OPS] 认证故障分层：id user01 → smbpasswd -a user01 的状态 → valid users/invalid users → 目标共享访问。不要把 Linux 账户存在当作 Samba 登录已完成。密码、私钥和凭证不要进入脚本或日志。',
    ['useradd', 'smbpasswd', 'security=user', 'tdbsam', 'valid users', 'invalid users']),
  entry('permissions', 'Samba 权限与 Linux 文件系统双层模型', '05 / 权限控制',
    'Samba writable=yes 仍可能无法写入；最终结果由共享策略与 owner/group/mode/ACL 共同决定。',
    '[SRC] writable、readonly 控制共享读写；write list = admin, root, @staff 指定写入用户/组；read list = mary, @students 指定只读用户/组；valid users 与 invalid users 控制访问者；hosts allow/hosts deny 控制来源。\n[OPS] 共享可打开但不能创建文件时，依次检查 writable/readonly、write list、ls -ld /samba/share、getfacl /samba/share，再判断是否需要 setfacl -m u:user01:rwx。valid users 与 invalid users 不应随意同时配置；deny/allow 的具体优先级要以实际 Samba 版本和配置验证为准，不凭记忆扩大访问范围。',
    ['writable', 'readonly', 'write list', 'read list', 'hosts allow', 'hosts deny', 'ACL', 'getfacl', 'setfacl'], 'APPROVAL_REQUIRED'),
  entry('clients', 'Windows、smbclient 与 mount.cifs 三阶段访问',
    '06 / 客户端访问',
    '共享发现、访问具体共享和 Linux 挂载是三个不同阶段。',
    '[SRC] Linux 客户端可安装 samba-client；smbclient -L //192.168.126.171/ -U user01 列出共享；smbclient //192.168.126.171/smb_share -U user01 访问具体共享；mount -t cifs -o username=user01,pass=123,rw //192.168.126.171/smb_share /u01/ 挂载到本地。\nWindows 可通过网络共享或映射网络驱动器访问 \\\\服务器\\\\共享名。\n[OPS] mount.cifs 失败时按网络 → 服务 → 共享发现 → 认证 → 具体共享 → 本地挂载点逐层隔离。smbclient -L 成功只代表发现阶段成功，不证明共享可读写或挂载参数正确。',
    ['smbclient', 'smbclient -L', 'mount.cifs', 'Windows network drive', 'mount -t cifs']),
  entry('troubleshooting', 'Samba 标准故障树与证据链', '07 / 故障诊断',
    '从服务器在线、服务、配置、发现、认证、授权、读写、ACL 到网络来源逐层定位。',
    '[OPS] 共享找不到：systemctl status smb/nmb → cat /etc/samba/smb.conf → ls -ld path → smbclient -L。认证失败：区分 Linux 用户、Samba 密码和共享授权。能打开不能写：检查 writable/readonly/write list，再查 owner/group/mode/ACL。Linux 挂载失败：先 smbclient -L，再 smbclient //host/share，最后 mount.cifs。Windows 正常而 Linux 异常：比较三阶段，不直接归因于服务器。\n证据优先级：实际命令输出、服务日志、testparm、配置、网络端口、权限和用户描述。修复后验证读取、创建、删除（仅在获批范围内）和卸载/重挂载。',
    ['smb status', 'testparm', 'logs', 'authentication', 'mount failure', 'evidence chain']),
  entry('safety', '实验简化与生产安全边界', '08 / 安全',
    '停止 firewalld、setenforce 0、禁用 SELinux 仅是实验准备，不能作为生产通用修复。',
    '[SRC] 教程实验使用 systemctl stop/disable firewalld、setenforce 0 和 SELINUX=disabled。\n[OPS] 生产应开放最小必要端口和来源，保留 SELinux 与防火墙策略；allow/deny、用户列表、共享目录 ACL 需最小权限。变更前备份 smb.conf，先 testparm -s，再经审批 reload/restart，使用客户端实际读写复验。不要因为 mount.cifs 失败就关闭安全控制。',
    ['firewalld', 'SELinux', 'least privilege', 'backup', 'testparm'], 'APPROVAL_REQUIRED')
]

export const sambaRules = Object.freeze([
  { id: 'SAMBA-001', trigger: '共享找不到', sequence: ['smb status', 'nmb status', 'smb.conf', 'path', 'smbclient -L', 'network'] },
  { id: 'SAMBA-002', trigger: '认证失败', sequence: ['id user', 'smbpasswd', 'valid/invalid users', 'share access'] },
  { id: 'SAMBA-003', trigger: '共享可打开但不能写', sequence: ['writable/readonly', 'write list', 'ls -ld', 'getfacl', 'approved ACL'] },
  { id: 'SAMBA-004', trigger: 'mount.cifs 失败', sequence: ['network', 'service', 'smbclient -L', 'smbclient share', 'mount point', 'mount options'] },
  { id: 'SAMBA-005', trigger: 'Windows 正常、Linux 异常', sequence: ['compare client path', 'smbclient discovery', 'share access', 'CIFS mount'] }
])
