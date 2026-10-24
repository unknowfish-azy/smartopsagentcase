// Reference knowledge only. No command executor or infrastructure API is imported here.
export const networkEnvironmentSource = {
  id: 'course-network-environment-summary-2026-09-24',
  kind: 'user_provided_course_summary', attachmentVerified: false,
  source: '用户提供的 Linux 网络与初始化课程摘要（原附件未核验）',
  version: '1.0', sourceFile: null,
  note: 'source_course 表示用户摘要归于课程的内容，不是已核验原文。expert_enhancement 与 production_rule 单独列出。'
}

const read = (command, purpose, parameters = '只读证据；记录主机、时间、权限和目标，输出应脱敏。') => ({
  command, purpose, parameters, read_only: true, risk: 'READ_ONLY', risk_level: 'LOW',
  executionAllowed: false, verification: '核对输出与目标、时间和业务场景；查询成功不等于健康。'
})
const change = (command, purpose, parameters, extra = {}) => ({
  command, purpose, parameters, read_only: false, risk: 'MEDIUM', risk_level: 'MEDIUM',
  executionAllowed: false, requires_preview: true, approval_required: true,
  verification: '比较变更前后证据并从独立客户端验证；失败按预先批准的回滚方案恢复。', ...extra
})
const node = (id, title, category, source_course, expert_enhancement, commands, relatedIds, tags) => ({
  id, title, category, type: 'ENGINEERING KNOWLEDGE', level: 'Senior',
  source_course, expert_enhancement, production_rule: expert_enhancement,
  concept: source_course, architecture: expert_enhancement.join(' → '),
  scenario: title, diagnosis: expert_enhancement, commands, relatedIds, tags,
  risk: '知识参考；变更必须预览、评估连接依赖并审批，不能自动执行。',
  verification: '以 IP、Route、DNS、SSH、Socket、Service、Application 及对应基线证据验收，不以退出码代替业务验证。',
  experience: '区分观察、推断、假设和建议；未知项保留 UNKNOWN。'
})

export const linuxNetworkEnvironmentNodes = [
  node('linux.identity.model', 'HostIdentity：主机身份不是 IP', 'Host Identity',
    '课程摘要包含 IP、网关、DNS、网卡名、主机名和连接 UUID。',
    ['关联 hostname/FQDN、machine-id、接口 name/MAC、连接 profile UUID、IPv4/prefix、gateway、DNS/routes、timezone/time sync/security state', '接口 MAC、NetworkManager 连接 UUID 和 machine-id 是不同标识', 'FQDN 是策略选择，不是所有主机必须使用的固定要求；hostname 变更不自动创建 DNS 记录'],
    [read('hostnamectl', '读取主机身份'), read('ip link', '发现接口和 MAC'), read('nmcli -f NAME,UUID,DEVICE connection show', '映射连接与设备'), read('cat /etc/machine-id', '核对机器标识', '标识属于主机元数据，不公开传播；不在已部署机器上盲目重置。')],
    ['linux.identity.hostname', 'linux.vm.clone.identity'], ['HostIdentity', 'FQDN', 'machine-id', 'UUID', 'MAC']),
  node('linux.network.interface.naming', 'Linux 接口命名与实际设备发现', 'Network',
    '传统 eth0/eth1；可预测名称 eno1、enp2s0、ens33；en 表示 Ethernet，wl 无线，ww 无线广域网，o onboard、s slot、p PCI 路径。',
    ['先 ip link 或 nmcli device status 发现真实接口，不假设第一块叫 eth0', '后缀是设备位置/索引，名称依 udev/systemd 命名策略而变，不是所有名称都能用同一公式拆解', '接口名不等于连接 profile 名；多连接可绑定同一设备'],
    [read('ip link', '查看接口存在、UP 与 LOWER_UP/carrier'), read('nmcli device status', '检查设备管理状态')],
    ['linux.network.networkmanager', 'LINUX-NET-001'], ['eth0', 'eno1', 'enp2s0', 'ens33', 'wl', 'ww', 'interface naming']),
  node('linux.network.networkmanager', 'NetworkManager 与 CentOS 7/9 配置路径', 'Network',
    'NetworkManager 管理 device、connection、IP、DNS、route 和 autoconnect；工具包括 nmcli、nmtui、nm-connection-editor。CentOS 7 ifcfg 使用 ONBOOT/BOOTPROTO/IPADDR/NETMASK/GATEWAY/DNS1。',
    ['先读取 /etc/os-release 并识别实际网络管理栈；不要把 restart network 当通用修复', 'CentOS Linux 7 已结束常规维护；CentOS Stream 9 与旧 CentOS Linux 不是同一生命周期', 'RHEL/Stream 9 优先 NetworkManager keyfile（/etc/NetworkManager/system-connections）；ifcfg 支持因版本和插件而异', 'NetworkManager active 只证明服务运行；连接可能 unmanaged、disconnected 或地址/路由错误'],
    [read('cat /etc/os-release', '识别发行版'), read('systemctl status NetworkManager --no-pager', '查询管理服务'), read('nmcli device status', '检查设备'), read('nmcli connection show', '查看 profile')],
    ['linux.network.nmcli.change', 'LINUX-NET-001'], ['NetworkManager', 'CentOS 7', 'CentOS 9', 'keyfile', 'ifcfg', 'ONBOOT', 'BOOTPROTO', 'NETMASK', 'DNS1']),
  node('linux.network.nmcli.change', 'nmcli 网络变更与当前 SSH 连接依赖', 'Network Change',
    '课程摘要通过 nmcli connection modify 设置 ipv4.addresses/gateway/method/dns，再 connection up；修改前备份配置。',
    ['发现目标 host/interface/profile UUID，记录 SmartOps→SSH→NetworkManager→interface→IP 依赖', '采集 ip addr、ip route、resolv.conf、nmcli device status/connection show；profile 备份应保护密码且不使用 --show-secrets', '验证地址/prefix/网关可达性、IPAM 分配与冲突风险；ping 无回应不能证明地址空闲', '预览并审批；普通配置 MEDIUM，影响当前远程路径至少 HIGH；准备控制台或独立管理路径及版本支持的 checkpoint/定时回滚', '配置 modify 不等于 active connection 已应用；up/reapply 能改变路由并切断 SSH；不要先 down 当前连接', '验证新连接、第二个 SSH 会话、DNS/路由/端口/业务，再解除回滚保护'],
    [read('ip addr', '变更前地址快照'), read('ip route', '路由快照'), read('cat /etc/resolv.conf', 'DNS 快照'), read('nmcli -f NAME,UUID,DEVICE connection show --active', '当前连接映射'),
      change('nmcli connection modify "<connection>" ipv4.addresses "<address>/<prefix>" ipv4.gateway "<gateway>" ipv4.method manual ipv4.dns "<dns1>,<dns2>"', '预览静态 IPv4 profile 修改', '替换已核验的 profile 名或使用 uuid selector；示例地址与 DNS 不可直接用于生产。', { remoteRisk: 'HIGH', operation_type: 'NETWORK_CONFIGURATION' }),
      change('nmcli connection modify "<connection>" connection.autoconnect yes', '修改自动连接', '明确设备/连接身份和重启后启动策略。', { remoteRisk: 'HIGH' }),
      change('nmcli connection modify "<connection>" ipv4.routes "<prefix> <next-hop>"', '修改静态路由', '此设置会替换对应属性；核对全部现有路由，不能意外覆盖管理路径。', { remoteRisk: 'HIGH' }),
      change('nmcli connection modify "<connection>" connection.interface-name "<interface>"', '绑定接口', '先发现实际网卡；克隆后检查 MAC 与绑定条件。', { remoteRisk: 'HIGH' }),
      change('nmcli connection up "<connection>"', '应用连接', '可能立即切断控制通道，要求独立恢复入口。', { remoteRisk: 'HIGH' }),
      change('nmcli connection down "<connection>"', '课程断开连接示例', 'lab/demo；禁止把当前 SSH 依赖连接直接断开。', { risk: 'HIGH', risk_level: 'HIGH', remoteRisk: 'HIGH', source_context: 'lab/demo' })],
    ['linux.network.interface.naming', 'LINUX-REMOTE-001'], ['nmcli', 'ipv4.addresses', 'ipv4.routes', 'connection.interface-name', 'CURRENT CONNECTION DEPENDENCY', 'DHCP', 'static']),
  node('linux.network.evidence', '网络证据与诊断阶梯（非 OSI 层编号）', 'Network Diagnosis',
    'ip a 看地址，ip route 看路由，ip neigh 看邻居，resolv.conf 看 DNS；ping 用于连通性观察。',
    ['复用 LINUX-NET-001：Interface→IP→Route→Neighbor→DNS→TCP→Port→Firewall→SELinux→Application；这是排查清单，不是 OSI L1–L10', '按证据选择相关分支，记录已排除层，不重复机械探测每层', 'resolv.conf 可能由 NetworkManager/systemd-resolved 管理；文件存在不证明解析成功', 'ping 仅测试 ICMP：失败可能是过滤，成功不证明 TCP/HTTP 可用；限制探测次数和超时', 'ip route get 反映选路，ip neigh 主要反映本地链路；跨网段不要求出现目标主机 ARP'],
    [read('ip a', '地址和前缀'), read('ip route', '默认与静态路由'), read('ip route get <destination-ip>', '实际目标选路'), read('ip neigh', '邻居状态'), read('cat /etc/resolv.conf', '解析器配置'), read('getent hosts <fqdn>', '按系统 NSS 解析'), read('ping -c 4 -W 2 <target>', '有界 ICMP 探测', '只探测授权目标；会产生少量网络流量。')],
    ['LINUX-NET-001', 'linux.service.socket'], ['Network Diagnostic Ladder', 'DNS', 'route', 'neighbor', 'ARP', 'ping']),
  node('linux.identity.hostname', 'Hostname / FQDN 与 DNS 的边界', 'Host Identity',
    'hostname、hostnamectl 查看名称；hostnamectl set-hostname 或 /etc/hostname 修改持久主机名，课程建议 FQDN。',
    ['先核对命名规范与 CMDB；使用 example.test 等文档域名，不冒用他人域名', 'hostname ≠ DNS record；分别核对正向/反向 DNS、/etc/hosts、证书与应用注册', '变更可能影响日志归属、证书和集群身份；检查依赖后审批'],
    [read('hostname', '当前 hostname'), read('hostnamectl', '持久/瞬态主机名'), read('cat /etc/hostname', '持久配置'), change('hostnamectl set-hostname <fqdn>', '设置主机名', '核验 DNS、证书、应用身份；修改不会自动发布 DNS。')],
    ['linux.identity.model', 'linux.vm.clone.identity'], ['hostname', 'FQDN', 'DNS record']),
  node('linux.service.socket', 'Process → Socket → Port → Service → Client', 'Service Connectivity',
    'ss -tnl 查看 TCP 数字监听，ss -tna 所有 TCP socket，ss -tnlp 显示进程。-t TCP/-n numeric/-l listen/-a all/-p process。netstat 是旧工具。',
    ['service active、process exists、port LISTEN、HTTP response 是不同事实；并非所有进程都使用 TCP/UDP 端口', '核对 local/peer address、state、Recv-Q/Send-Q；LISTEN 与 ESTABLISHED 不是同一状态，队列含义依 socket 状态而异', '检查 IPv4/IPv6、127.0.0.1/全地址绑定和 network namespace；-p 信息可能因权限隐藏', 'UDP 使用 ss -unap，不用 TCP LISTEN 语义判断 UDP 服务；Unix socket 不占 IP 端口', 'nginx active 且 80 LISTEN 仍需本机、服务器地址、远程客户端和 upstream 验证'],
    [read('ss -tnl', 'TCP 监听'), read('ss -tnlp', '进程端口映射'), read('ss -tna', 'TCP 状态'), read('ss -unap', 'UDP socket'), read('curl --connect-timeout 3 --max-time 10 -I http://127.0.0.1/', '验证本地 HTTP', '只对批准的只读健康路径探测；同时考虑 Host/SNI 与返回内容。')],
    ['linux.security.firewalld', 'linux.security.selinux.state'], ['ss', 'netstat', 'LISTEN', 'ESTABLISHED', 'Recv-Q', 'Send-Q', 'Process-Port Mapping']),
  node('linux.service.port.conflict', '端口冲突与 kill -9 风险', 'Service Connectivity',
    'nginx/httpd 都可能绑定 80；课程中 kill -9 pid 属于实验快速处理示例。',
    ['address already in use → ss 找绑定地址/协议/namespace/PID → 核实业务 owner 与依赖', '同地址、协议、端口通常不能重复绑定；SO_REUSEPORT、不同地址或命名空间是需要明确的例外', '先评估改端口/服务配置，必要停服走优雅停止、审批、回滚和验证；禁止盲杀未知 PID'],
    [read('ss -tnlp', '确定监听 owner'), read('ps -p <pid> -o pid,ppid,user,args', '核对 PID 身份'), change('kill -9 <pid>', 'lab/demo 强制终止', '跳过清理、丢失在途事务、可能损坏数据；PID 会复用，执行前再次确认。', { risk: 'HIGH', risk_level: 'HIGH', source_context: 'lab/demo' })],
    ['linux.service.socket', 'LINUX-REMOTE-001'], ['address already in use', 'nginx', 'httpd', 'kill -9', 'port conflict']),
  node('linux.security.firewalld', 'Firewalld：实验关闭与生产最小放行', 'Security Baseline',
    '课程实验使用 systemctl stop/disable firewalld 简化网络测试。',
    ['先确认服务监听、active zone、接口绑定、runtime/permanent 差异与已有策略', '生产不默认停用防火墙，只在审批后最小放行目标服务/来源，并保留 SSH 管理入口', '外部失败也可能是云安全组、ACL、路由、NAT 或客户端；firewalld 未运行不代表没有 nftables 规则'],
    [read('systemctl status firewalld --no-pager', '查看服务状态'), read('firewall-cmd --get-active-zones', '查询生效 zone'), read('firewall-cmd --zone=<zone> --list-all', '查询指定 zone 规则'), change('systemctl stop firewalld', '实验停止防火墙', 'lab/demo；撤销主机安全边界，生产不得默认采用。', { risk: 'HIGH', risk_level: 'HIGH', source_context: 'lab/demo' }), change('systemctl disable firewalld', '实验禁用开机启动', 'lab/demo；disable 与 stop 不同，重启后策略也需验证。', { risk: 'HIGH', risk_level: 'HIGH', source_context: 'lab/demo' })],
    ['linux.service.socket', 'linux.bootstrap.baseline'], ['firewalld', 'zone', 'nftables', 'security baseline']),
  node('linux.security.selinux.state', 'SELinux 状态与拒绝证据', 'Security Baseline',
    'getenforce 输出 Enforcing/Permissive/Disabled；实验 setenforce 0 与 /etc/selinux/config 配置。',
    ['Enforcing 执行策略；Permissive 记录拒绝但不阻断；Disabled 不启用 SELinux', 'Permission denied 也可能是 DAC/ACL、挂载选项、服务用户或 SELinux；先看审计 AVC 和标签', '只有适用 AVC/策略证据才能归因 SELinux；localhost 成功且外部失败优先看绑定/网络/防火墙，而非直接怪 SELinux', '自定义目录、端口、二进制需核验标签/端口类型；不要盲目 audit2allow 或 setenforce 0', '持久关闭在新版本有额外要求，可能需启动参数/重启；重新启用考虑 relabel 和维护窗口'],
    [read('getenforce', '当前强制访问控制状态'), read('sestatus', '策略和配置状态'), read('ausearch -m AVC -ts recent', '查询最近拒绝', '需要适当审计权限；无 AVC 不证明不存在其它安全限制。'), read('ls -Z <path>', '安全标签'), change('setenforce 0', '实验切换 Permissive', 'lab/demo；不是永久关闭；生产临时诊断也需审批、限定时间并恢复。', { risk: 'HIGH', risk_level: 'HIGH', source_context: 'lab/demo' })],
    ['linux.security.firewalld', 'linux.bootstrap.baseline'], ['SELinux', 'getenforce', 'AVC', 'Enforcing', 'Permissive', 'Disabled']),
  node('linux.time.chrony', 'Chrony：运行状态与同步状态分开验证', 'Time',
    '课程使用 systemctl status/start/enable chronyd 与 timedatectl。',
    ['该节点为本批唯一 Chrony 标准节点，ServerBaseline 引用它，不重复生成时间知识', 'chronyd active 或 enabled 不代表已同步；验证 tracking、sources、可达性、offset、stratum 与 Leap status', '时区只影响显示；同步校准时钟。大幅时间跳变会影响证书、日志关联、任务调度和数据库，不自动 makestep', 'NTP 源必须可信且被网络策略允许；容器和虚拟机先明确宿主时钟责任'],
    [read('systemctl status chronyd --no-pager', '服务运行状态'), read('timedatectl', '时区与系统时间状态'), read('chronyc tracking', '同步质量'), read('chronyc sources -v', '时间源选择与可达性'), change('systemctl start chronyd', '启动时间同步服务', '审批后检查源和偏移，避免大幅跳时。'), change('systemctl enable chronyd', '设置开机启动', 'enable 本身不证明服务运行或已同步。')],
    ['linux.bootstrap.baseline', 'LINUX-SCHED-003'], ['Chrony', 'chronyd', 'NTP', 'timedatectl', 'time synchronization']),
  node('linux.bootstrap.tools', 'YUM/DNF 与 Missing Tool Resolver', 'Server Initialization',
    '最小安装使用 YUM 仓库并补充 lrzsz、sysstat、curl、wget、net-tools、bash-completion、vim。',
    ['工具用途：lrzsz 文件传输；sysstat 观察；curl HTTP；wget 下载；net-tools 旧网络；bash-completion 补全；vim 编辑', 'ifconfig 缺失先用 ip，缺失命令 ≠ 网络故障；依次 command→provider package→trusted repository→preview→approval→install→verify', '检查发行版版本、仓库签名、metadata 和包可用性；EOL 镜像不能靠盲换源恢复安全维护', '安装包是主机变更，非 LOW 只读；不要默认批量升级全部包'],
    [read('command -v ifconfig', '确认命令缺失'), read('rpm -q net-tools', '确认提供包'), read('dnf repolist --enabled', '仓库清单', 'CentOS 7 使用 yum；查询可能访问网络或更新本地缓存。'), read('dnf provides */ifconfig', '解析提供包', '仅可信仓库；允许元数据缓存，不安装软件。'), change('dnf install <approved-package>', '安装缺失工具', '先查看事务和依赖；CentOS 7 对应 yum；安装需要批准。')],
    ['linux.bootstrap.baseline'], ['Missing Tool Resolver', 'YUM', 'DNF', 'lrzsz', 'sysstat', 'net-tools', 'bash-completion', 'vim']),
  node('linux.bootstrap.baseline', 'Golden Linux Image / ServerReadiness / EnvironmentBaseline', 'Server Initialization',
    '课程最小化服务器经网络、仓库、工具、Chrony 配置后关机并创建模板/克隆。',
    ['Minimal OS→Identity→Network→Repository→Tools→Time→Security→SSH→Baseline→Validation→Snapshot→Template', 'ServerReadiness 为 NOT_READY/PARTIALLY_READY/READY/DEGRADED；未采集项 UNKNOWN，缺证据不能判 READY', 'identity/network/dns/time_sync/ssh/storage/package_manager/security_state 均为 required；其中 repository FAIL 不能宣称服务器完全正常', 'EnvironmentBaseline 记录 OS/kernel、hostname/FQDN、IP/MAC/routes/DNS、timezone/ntp、packages/services/ports、firewall/SELinux、disk/memory/cpu、采集时间与模板版本', '安全 PASS 表示符合批准策略，不表示关闭；新主机验证失败为 PARTIALLY_READY，已验收主机退化为 DEGRADED', '模板去除凭据/令牌和主机专属状态，快照不是异机备份；监控 Agent 安装需独立授权'],
    [read('uname -r', '内核基线'), read('df -h', '空间基线'), read('free -m', '内存基线'), read('systemctl --failed', '失败服务'), read('rpm -qa', '包清单'), read('ss -tnlp', '监听基线')],
    ['linux.identity.model', 'linux.time.chrony', 'linux.bootstrap.tools', 'linux.security.firewalld', 'linux.security.selinux.state', 'linux.vm.clone.identity'], ['Golden Linux Image', 'ServerReadiness', 'ServerBaseline', 'EnvironmentBaseline', 'NOT_READY', 'PARTIALLY_READY', 'READY', 'DEGRADED']),
  node('linux.vm.clone.identity', '模板克隆、身份核验与配置漂移', 'VM Lifecycle',
    '课程先关闭模板机，再通过克隆获得实验服务器。',
    ['Clone ≠ Ready：先隔离网络，核验 hostname/FQDN、IP、MAC、machine-id、SSH host key 指纹、profile、DNS、时间和安全状态', '由镜像制备工具按发行版要求处理 machine-id/SSH host keys；不得在已注册生产主机上盲删标识或重生成密钥', 'MAC 是否重分配取决于虚拟化平台，profile UUID 不等于 MAC；证书/监控 token/cluster node identity 也需核对', '记录 template_id/clone_id/source_snapshot/created_at/network_profile/assigned_ip 并登记 CMDB；已用 IP 不能上线试错', 'Template vs Current：package/service/network/firewall/SELinux/config drift；hostname/IP 等预期差异应由每台主机 desired state 覆盖，不能一概告警', '恢复 SSH 前通过可信渠道验证新指纹，不关闭 StrictHostKeyChecking 掩盖冲突'],
    [read('hostnamectl', '克隆后名称'), read('ip a', 'MAC/IP 冲突检查'), read('cat /etc/machine-id', '比对机器标识'), read('ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub', '读取公钥指纹', '只读取公钥，密钥类型按目标实际文件选择；不输出私钥。')],
    ['linux.identity.model', 'linux.bootstrap.baseline', 'LINUX-REMOTE-001'], ['clone', 'snapshot', 'Identity Reset', 'Configuration Drift', 'Clone Drift', 'CMDB', 'Host Digital Twin'])
]

export const linuxNetworkEnvironmentIncidents = [
  ['INC-NET-001', '网卡不可用', 'linux.network.interface.naming', '接口缺失或 NO-CARRIER', 'ip link；核对虚拟网卡连接、驱动与物理链路'],
  ['INC-NET-002', '没有 IPv4 地址', 'linux.network.networkmanager', '设备存在但无预期地址', 'ip a；确认 DHCP/static、profile 激活状态和 DHCP 服务器'],
  ['INC-NET-003', '默认路由缺失', 'linux.network.evidence', '跨网段不可达', 'ip route 与 ip route get；确认网络设计是否需要默认路由'],
  ['INC-NET-004', 'DNS 解析失败', 'linux.network.evidence', 'DNS_PROBE_FINISHED_NXDOMAIN', 'getent hosts；检查拼写、域权威记录、resolver 和 DNS 网络路径'],
  ['INC-NET-005', 'NetworkManager 不可用', 'linux.network.networkmanager', 'nmcli 无法联系服务', '先确认是否由其它网络栈管理，再查询状态与日志'],
  ['INC-NET-006', '静态 IP 配置错误', 'linux.network.nmcli.change', '前缀/网关/地址与规划不符', '对比 IPAM、profile 和 active state，预览审批并准备回滚'],
  ['INC-NET-007', '网络变更导致 SSH 中断', 'linux.network.nmcli.change', '变更后控制通道丢失', '使用预先准备的控制台/独立管理通道查看地址路由；按预批准计划回滚，不能假装还能 SSH'],
  ['INC-NET-008', '服务端口未监听', 'linux.service.socket', 'ERR_CONNECTION_REFUSED', '核对目的地址/端口、ss、namespace 与服务日志；拒绝也可能来自防火墙 REJECT'],
  ['INC-PORT-CONFLICT-001', '端口冲突', 'linux.service.port.conflict', 'address already in use', 'ss -tnlp 找 owner；核实业务影响，不盲目 kill -9'],
  ['INC-FIREWALL-001', '防火墙策略阻断', 'linux.security.firewalld', '本地可用远端失败', '核对监听、zone、云安全组和路径；以规则/流量证据确认，不直接关闭'],
  ['INC-SELINUX-001', 'SELinux 拒绝', 'linux.security.selinux.state', 'Permission denied 与相关 AVC', '比对 AVC、标签、服务用户和策略；排除 DAC/ACL，不默认 setenforce 0'],
  ['INC-HOSTNAME-001', 'Hostname/FQDN 不一致', 'linux.identity.hostname', '日志、DNS、证书名称不一致', '分别核对 hostnamectl、DNS、证书与应用注册'],
  ['INC-CLONE-IDENTITY-001', '克隆主机身份冲突', 'linux.vm.clone.identity', '重复 IP/MAC/machine-id 或 SSH 身份异常', '隔离冲突实例，从控制台核验模板与主机标识，审批后修正并验证']
].map(([id, title, relatedId, symptoms, diagnosis]) => ({
  id, title, type: 'INCIDENT', category: 'Incident Library', origin: 'expert_enhancement', status: 'REFERENCE_SCENARIO',
  symptoms, observed: symptoms, hypothesis: '待系统证据确认，症状不是根因。',
  diagnosis: [diagnosis, '记录支持和矛盾证据、受影响业务与控制通道依赖'],
  verification: '从授权客户端复验对应层与业务端点，记录稳定窗口；未验证不得 RESOLVED/VERIFIED。',
  rollback: '仅对经批准的变更使用事先保存的状态和独立恢复入口。',
  risk: id === 'INC-NET-007' ? 'HIGH' : 'READ_ONLY', executionAllowed: false,
  relatedIds: [relatedId], tags: [id, symptoms, title]
}))

export const linuxNetworkEnvironmentRunbooks = [{
  id: 'RB-LINUX-BOOTSTRAP-001', title: 'Linux 标准模板初始化', type: 'RUNBOOK', category: 'Server Bootstrap',
  origin: 'expert_enhancement', problem: '建立可追溯、可复验、无身份冲突的标准模板。',
  prerequisites: ['批准的 OS/仓库与命名/IPAM 规划', '控制台或独立恢复路径', '实验与生产安全策略分别定义'],
  phases: ['identity', 'network', 'repository', 'tools', 'time', 'security', 'access', 'baseline', 'validation', 'snapshot'],
  diagnosis: ['只读发现主机、接口、管理栈与控制通道', '比对网络、仓库、时间、安全、SSH、磁盘和服务证据', '生成最小变更预览与风险清单；人工审批后由独立操作层执行', '验证网络/DNS/route/SSH/time/port/application，并保存带时间戳基线', '按镜像工具规则清理主机专属状态；维护窗口关机生成版本化模板'],
  expectedResult: '全部 required 检查符合批准策略且证据新鲜，才 READY。',
  abnormalResult: '未检查为 UNKNOWN；仓库失败为 PARTIALLY_READY；已验收主机偏离基线为 DEGRADED。',
  resolution: '只推荐针对失败项的审批变更，不自动执行整份 Runbook。',
  verification: '第二条 SSH 会话、授权客户端业务请求、Chrony sources/tracking 和安全规则复核。',
  rollback: '预存 profile/路由/安全配置，保留控制台与模板版本；禁止依赖即将修改的唯一 SSH 通道。',
  risk: 'HIGH', executionAllowed: false,
  relatedIds: ['linux.bootstrap.baseline', 'linux.time.chrony', 'linux.vm.clone.identity'], tags: ['RB-LINUX-BOOTSTRAP-001', 'Golden Linux Image']
}]

const questionRows = [
  ['SINGLE_CHOICE', 'Linux 首个网卡一定是 eth0 吗？', '不一定；先 ip link/nmcli 发现。', 'NETWORK_IDENTITY_ERROR', '一定是 eth0', 'linux.network.interface.naming'],
  ['MULTIPLE_CHOICE', 'HostIdentity 应包含哪些标识？', 'hostname/FQDN、machine-id、接口/MAC、profile UUID、IP/routes/DNS、时间和安全状态。', 'NETWORK_IDENTITY_ERROR', '只有 IP', 'linux.identity.model'],
  ['TRUE_FALSE', 'NetworkManager active 是否说明网络健康？', '否；分别验证地址、选路、解析、端口和应用。', 'NETWORK_HEALTH_CONFUSION', 'active 就是健康', 'linux.network.networkmanager'],
  ['COMMAND_SELECTION', '如何找占用 80 端口的进程？', 'ss -tnlp，核对地址、协议、namespace 与 owner；权限不足可能不显示 PID。', 'PORT_ANALYSIS_ERROR', 'kill -9 任意 PID', 'linux.service.port.conflict'],
  ['NETWORK_TROUBLESHOOTING', '远程修改 IP 是低风险吗？', '否；当前 SSH 依赖目标路径时至少 HIGH，预览、审批、控制台与回滚缺一不可。', 'CONNECTION_DEPENDENCY_ERROR', 'IP 修改是低风险', 'linux.network.nmcli.change'],
  ['PORT_ANALYSIS', 'LISTEN 与 ESTABLISHED 是否相同？', '否；监听与已建立连接是不同状态，均不能单独证明应用健康。', 'SOCKET_STATE_ERROR', '相同', 'linux.service.socket'],
  ['SERVICE_ANALYSIS', 'nginx active 是否代表网页可访问？', '否；依次核对 socket、绑定地址、路径、安全策略、HTTP 与 upstream。', 'SERVICE_CONNECTIVITY_CONFUSION', 'active 就可访问', 'linux.service.socket'],
  ['SERVER_BOOTSTRAP', '初始化时网页不通就关闭 firewalld 吗？', '否；先定位监听与规则；课程关闭步骤只属 lab/demo。', 'SECURITY_RISK_ERROR', '先停 firewalld', 'linux.security.firewalld'],
  ['CLONE_ANALYSIS', '克隆完成能立即上线吗？', '不能；隔离核验 hostname/IP/MAC/machine-id/SSH identity、DNS 与基线。', 'IDENTITY_CLONE_ERROR', 'Clone = Ready', 'linux.vm.clone.identity'],
  ['TRUE_FALSE', '修改 hostname 后 DNS 自动改变吗？', '否；DNS 记录、证书和服务发现需独立管理和验证。', 'HOSTNAME_DNS_CONFUSION', '会自动改变', 'linux.identity.hostname'],
  ['TRUE_FALSE', 'SELinux Enforcing 意味着程序不能运行吗？', '否；按策略授权的程序正常运行，需相关 AVC 才能判断策略拒绝。', 'SECURITY_RISK_ERROR', '所有程序都被阻止', 'linux.security.selinux.state'],
  ['SERVER_BOOTSTRAP', 'chronyd active 等于同步了吗？', '否；结合 chronyc tracking/sources、偏移与源状态验证。', 'TIME_READINESS_ERROR', 'active 就同步', 'linux.time.chrony']
]
export const linuxNetworkEnvironmentQuestions = questionRows.map(([questionType, question, answer, wrongReasonType, wrongAnswer, relatedId], index) => ({
  id: `Q-NETENV-${String(index + 1).padStart(3, '0')}`, title: question, question, answer,
  type: 'QUESTION', category: 'Question Bank', questionType, wrongReasonType, origin: 'expert_enhancement',
  options: questionType === 'MULTIPLE_CHOICE' ? ['hostname/FQDN 与 machine-id', '接口 MAC、连接 UUID 与 IP/routes/DNS', '时间同步与安全状态', '只有 IP 即可'] : [answer, wrongAnswer],
  correctOptionIndexes: questionType === 'MULTIPLE_CHOICE' ? [0, 1, 2] : [0], relatedIds: [relatedId], tags: [questionType, question], risk: 'REFERENCE'
}))
export const linuxNetworkEnvironmentWrongAnswers = questionRows.map(([, question, correction, wrong_reason_type, misconception, relatedId], index) => ({
  id: `WRONG-NETENV-${String(index + 1).padStart(3, '0')}`, title: question, type: 'WRONG_ANSWER', category: 'Wrong Answer Bank',
  origin: 'expert_enhancement', misconception, correction, wrong_reason_type, relatedIds: [relatedId], tags: [wrong_reason_type, misconception], risk: 'REFERENCE'
}))

export const linuxNetworkEnvironmentRules = [
  { id: 'RULE-NETENV-RISK', title: '网络修改风险与控制通道依赖', kind: 'Risk Rule', sequence: ['identify host/interface/profile', 'capture current state', 'backup', 'validate address/conflict', 'assess current SSH dependency', 'preview', 'approval', 'apply via separately authorized operations', 'verify', 'rollback if failed'], networkMutationRisk: 'MEDIUM', currentConnectionDependencyRisk: 'HIGH', approval_required: true, relatedIds: ['linux.network.nmcli.change'] },
  { id: 'RULE-NETENV-AGENT', title: '视觉现象到网络与服务证据', kind: 'Agent Decision Rule', sequence: ['Observe', 'identify host/interface/current connection', 'collect network state', 'diagnose relevant layer', 'search knowledge', 'form hypothesis', 'recommend least-risk evidence', 'request approval for mutations', 'verify', 'record incident and baseline'], patterns: ['ERR_CONNECTION_REFUSED', 'ERR_CONNECTION_TIMED_OUT', 'DNS_PROBE_FINISHED_NXDOMAIN', '502', '503', '504'], evidenceLevels: ['OBSERVED', 'CORROBORATED', 'CONFIRMED', 'RESOLVED', 'VERIFIED'], rule: '视觉文字只证明观察；相同画面重复不是独立证据。HTTP 502/503/504 不直接证明 nginx/Pod 根因；当前阶段仅建议 ss/systemctl/curl，不自动调用。', relatedIds: ['linux.network.evidence', 'linux.service.socket'] },
  { id: 'RULE-NETENV-VERIFY', title: '变更后验证而非退出码验收', kind: 'Verification Rule', sequence: ['IP', 'Route', 'DNS', 'SSH', 'Port', 'Service', 'Application', 'business result', 'stability window'], rule: '命令成功不代表恢复；涉及服务身份时核对 Host/SNI 和实际业务路径。', relatedIds: ['linux.service.socket', 'linux.time.chrony'] },
  { id: 'RULE-NETENV-BASELINE', title: 'Readiness 与漂移证据', kind: 'Baseline Rule', required: ['identity', 'network', 'dns', 'time_sync', 'ssh', 'storage', 'package_manager', 'security_state'], statuses: ['NOT_READY', 'PARTIALLY_READY', 'READY', 'DEGRADED'], rule: '每项保留 PASS/FAIL/UNKNOWN、采集时间与证据；未采集不 PASS。漂移区分主机预期差异和未批准差异，事故只有审阅归纳后才成为知识。', relatedIds: ['linux.bootstrap.baseline', 'linux.vm.clone.identity'] }
].map(rule => ({ ...rule, type: 'DECISION_RULE', category: rule.kind, origin: 'expert_enhancement', tags: [rule.id, rule.kind], risk: 'REFERENCE', executionAllowed: false }))

const artifacts = [...linuxNetworkEnvironmentNodes, ...linuxNetworkEnvironmentIncidents, ...linuxNetworkEnvironmentRunbooks, ...linuxNetworkEnvironmentQuestions, ...linuxNetworkEnvironmentWrongAnswers, ...linuxNetworkEnvironmentRules]

export const networkEnvironmentEntries = artifacts.map(item => ({
  ...item, packId: 'linux-network-environment', domain: 'linux', platform: 'Linux', service: 'network-environment',
  provenance: networkEnvironmentSource, source: networkEnvironmentSource.source, version: '1.0', section: item.category,
  summary: item.concept || item.problem || item.symptoms || item.question || item.rule || item.title,
  content: [item.id, item.title,
    item.source_course ? `source_course（摘要，非核验原文）\n${item.source_course}` : '',
    item.expert_enhancement ? `expert_enhancement\n${item.expert_enhancement.join('\n')}` : '',
    item.production_rule ? `production_rule\n${item.production_rule.join('\n')}` : '',
    JSON.stringify(item, null, 2)
  ].filter(Boolean).join('\n\n')
}))
