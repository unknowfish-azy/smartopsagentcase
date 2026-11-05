// Nginx 生产运维知识包：参考 nginx 开源官方文档（nginx.org/docs）与
// 《Nginx 实战》类公开资料，覆盖安装、配置、反向代理、负载均衡、TLS 与排障。
export const nginxOpsProvenance = Object.freeze({
  source: '开源参考资料：nginx.org 官方文档、nginx 官方镜像与公开运维手册',
  references: ['nginx documentation', 'nginx.org commercial docs', 'OpenSSL documentation'],
  verification: '示例参数需按实际版本与业务压测结果调整'
})

const entry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'nginx.ops.' + id,
  domain: 'nginx', platform: 'Nginx', service: 'nginx',
  type: 'NGINX OPERATIONS', title, section, summary, content,
  tags: ['Nginx', '反向代理', 'Web 服务', ...tags],
  source: nginxOpsProvenance.source,
  version: 'Nginx 1.24+ / 1.26 通用原则', risk, executionAllowed: false
})

export const nginxOpsEntries = [
  entry('install-upgrade', '安装、版本确认与平滑升级', '01 / 安装',
    '优先使用发行版或官方仓库；升级前记录版本、模块和配置，验证语法后再平滑切换。',
    '[SRC] 常见安装方式为发行版包管理器、nginx 官方仓库和源码编译。nginx -v 查看版本，nginx -V 查看编译参数与模块，nginx -t 校验配置。systemctl status nginx 查看服务状态，journalctl -u nginx 查看启动错误。\n[OPS] 升级前记录当前版本、第三方模块、配置差异和回滚包。源码替换二进制时可先启动新 master 再平滑退出旧进程，但不能在未验证配置和业务的情况下直接重启。生产变更需维护窗口、审批、回滚路径和业务复验；不要混用不同来源的包与模块。',
    ['nginx -v', 'nginx -V', 'nginx -t', 'systemctl', 'upgrade', 'rollback'], 'APPROVAL_REQUIRED'),
  entry('config-context', '配置层级、include 与语法校验', '02 / 配置模型',
    '主配置分为 main、events、http、server、location、upstream 等上下文；include 组织分片配置。',
    '[SRC] /etc/nginx/nginx.conf 为入口，常见包含 conf.d/*.conf 与 sites-enabled/*；http 块承载全局 HTTP 参数，server 定义虚拟主机，location 匹配 URI，upstream 定义后端组。指令有上下文限制，放错层级会导致 nginx -t 报错。\n[OPS] 改动前先备份并在测试环境 nginx -t；include 路径要确认实际加载文件，避免“改了没生效”。配置中不要硬编码明文凭据；涉及证书、密钥和上游地址的变更要记录来源与有效期。nginx -t 通过只代表语法与部分运行时可解析，不代表业务流量正确。',
    ['nginx.conf', 'http', 'server', 'location', 'upstream', 'include', 'nginx -t'], 'APPROVAL_REQUIRED'),
  entry('location-matching', 'location 匹配优先级与 root/alias', '03 / 路由',
    '精确匹配优先，其次前缀与正则；root 拼接 URI，alias 替换匹配前缀，末尾斜杠影响结果。',
    '[SRC] 匹配顺序大致为 = 精确匹配、^~ 前缀匹配（不再检查正则）、正则匹配（按出现顺序）、普通前缀匹配。try_files 按顺序检查文件或目录，最后可回退到命名 location 或状态码。root 将 URI 追加到路径，alias 用配置路径替换匹配部分。\n[OPS] 404 排查先确认 Host、server_name、location 命中、root/alias 拼接结果和文件权限，再查 rewrite 与应用路由。正则 location 顺序敏感，新增规则可能改变既有匹配。修改路由规则要保留原配置、验证静态与动态请求，并检查大小写、末尾斜杠和 URL 编码。',
    ['location', '= 精确匹配', '^~', 'regex', 'root', 'alias', 'try_files'], 'APPROVAL_REQUIRED'),
  entry('reverse-proxy', 'proxy_pass、请求头与超时', '04 / 反向代理',
    'proxy_pass 的 URI 写法决定路径是否重写；Host、X-Forwarded-* 与超时影响后端行为。',
    '[SRC] proxy_pass http://backend; 保留原始 URI；proxy_pass http://backend/; 会替换匹配前缀。常用头：proxy_set_header Host $host、X-Real-IP $remote_addr、X-Forwarded-For、X-Forwarded-Proto。proxy_connect_timeout、proxy_read_timeout、proxy_send_timeout 分别控制连接、读取和发送。\n[VERIFY] 后端若依赖 Host 或 X-Forwarded-Proto 生成绝对地址，缺失头会导致重定向、回调或鉴权异常。\n[OPS] 504 类问题先比较网关超时、后端处理时间与依赖耗时，提高 timeout 只能缓解症状。代理配置变更要验证真实请求、重定向、上传下载和 WebSocket；保留回滚配置并观察错误率。',
    ['proxy_pass', 'proxy_set_header', 'X-Forwarded-For', 'Host', 'timeout', 'WebSocket'], 'APPROVAL_REQUIRED'),
  entry('upstream-balance', 'upstream 负载均衡、健康检查与 keepalive', '05 / 负载均衡',
    '轮询、最少连接、ip_hash 等策略决定流量分配；max_fails/fail_timeout 提供被动健康检查。',
    '[SRC] upstream 支持默认轮询、least_conn、ip_hash、hash 等策略；server 可带 weight、max_fails、fail_timeout、backup、down。keepalive 减少连接建立开销，需配合 proxy_http_version 1.1 与 Connection 头清理。\n[OPS] 后端节点必须可独立验证，负载均衡不能掩盖单点故障。权重调整要先评估容量与热点；备份节点只在主节点不可用时承接流量。健康检查参数过激会导致抖动，过松会放大故障。变更后验证分布、错误率、延迟与回滚；不要在未确认会话保持需求时切换策略。',
    ['upstream', 'least_conn', 'ip_hash', 'weight', 'max_fails', 'fail_timeout', 'keepalive'], 'APPROVAL_REQUIRED'),
  entry('tls-https', 'TLS 证书链、协议与安全配置', '06 / HTTPS',
    '证书必须包含完整链；协议与套件按安全基线配置；变更证书后必须验证到期时间和客户端兼容性。',
    '[SRC] ssl_certificate 配置证书链，ssl_certificate_key 配置私钥；ssl_protocols 建议只保留 TLSv1.2/TLSv1.3；ssl_ciphers 选择安全套件；ssl_session_cache 与 ssl_session_timeout 影响性能。HSTS 通过 Strict-Transport-Security 强制 HTTPS。\n[OPS] 证书文件权限、私钥保护和续期监控属于安全要求。启用 HSTS 前确认所有子域可用 HTTPS，否则会造成访问中断。用 openssl s_client 或外部检测验证证书链、主机名和到期时间；变更后复验浏览器、移动端与后端回调。禁止关闭证书校验或用不安全协议作为临时修复。',
    ['ssl_certificate', '证书链', 'TLSv1.2', 'TLSv1.3', 'HSTS', 'openssl s_client'], 'APPROVAL_REQUIRED'),
  entry('caching', 'proxy_cache、缓存键与失效边界', '07 / 缓存',
    '缓存路径、键和有效期决定命中；Authorization、Cookie 与动态内容必须谨慎缓存。',
    '[SRC] proxy_cache_path 定义存储路径、层级、内存区与淘汰策略；proxy_cache_key 决定缓存粒度；proxy_cache_valid 按状态码设置时间；proxy_cache_bypass 与 proxy_no_cache 控制绕过。\n[OPS] 默认不要缓存带登录态、个性化或写操作的响应。缓存命中率提升不等于正确性，需验证缓存键是否包含必要的 Host、URI、语言和版本。清理缓存要评估命中率与回源压力；变更后检查响应头、回源日志和业务数据一致性。缓存目录磁盘增长要纳入监控和清理策略。',
    ['proxy_cache_path', 'proxy_cache_key', 'proxy_cache_valid', 'bypass', 'cache hit'], 'APPROVAL_REQUIRED'),
  entry('compression-buffering', 'gzip、缓冲与大文件传输', '08 / 性能',
    'gzip 降低传输体积但增加 CPU；缓冲参数影响大文件、流式响应与内存占用。',
    '[SRC] gzip 配置 gzip_types、gzip_min_length、gzip_comp_level；sendfile 提升静态文件效率；proxy_buffering 开启时 Nginx 先缓冲后端响应，关闭后更适合流式或大文件。client_max_body_size 限制上传体积，proxy_buffer_size 与 proxy_buffers 影响响应缓冲。\n[OPS] 压缩级别过高会增加 CPU，需压测权衡。大文件上传失败先查 client_max_body_size、磁盘、超时和后端限制，不要只调大 Nginx 参数。关闭缓冲会占用后端连接更久，可能降低吞吐。性能变更必须有基线、压测结果、回滚值和线上观察窗口。',
    ['gzip', 'sendfile', 'proxy_buffering', 'client_max_body_size', 'proxy_buffers', 'baseline'], 'APPROVAL_REQUIRED'),
  entry('rate-limit-security', '限流限连、安全响应头与暴露面', '09 / 防护',
    'limit_req/limit_conn 控制突发与并发；安全头降低点击劫持、嗅探和版本泄露风险。',
    '[SRC] limit_req_zone 定义按 IP 或键的速率，limit_req 在 location 启用并设置 burst/nodelay；limit_conn_zone 与 limit_conn 控制并发连接。server_tokens off 隐藏版本；常用安全头包括 X-Content-Type-Options、X-Frame-Options 或 frame-ancestors、Referrer-Policy。\n[OPS] 限流阈值要结合真实流量与压测，过低会误伤正常用户，过高失去保护意义。安全头可能影响嵌入、回调或旧客户端，需灰度验证。禁止用关闭防火墙、开放目录列表或放宽上传类型来“快速恢复”。所有防护策略变更都要记录原因、影响范围和回滚方式。',
    ['limit_req', 'limit_conn', 'burst', 'server_tokens', 'security headers'], 'APPROVAL_REQUIRED'),
  entry('reload-rollback', 'reload、worker 生命周期与零中断变更', '10 / 变更安全',
    'reload 加载新配置并平滑替换 worker；失败可能导致旧配置继续生效或进程异常，需验证与回滚。',
    '[SRC] nginx -t 校验配置，systemctl reload nginx 触发平滑重载；worker_shutdown_timeout 控制旧 worker 退出等待。restart 会中断连接，reload 通常不中断但依赖配置正确。nginx -s reload 与 systemctl reload 的适用环境不同。\n[OPS] 变更流程：备份配置 → 校验语法 → 灰度或低峰执行 → 检查进程与端口 → 验证真实请求与错误日志 → 观察稳定窗口 → 保留回滚。reload 后旧 worker 可能仍在处理长连接，不能立刻判定变更完全生效。失败时优先回滚到已验证配置，再定位原因；不要把连续 restart 当作排查手段。',
    ['reload', 'nginx -t', 'worker_shutdown_timeout', 'graceful', 'rollback'], 'APPROVAL_REQUIRED'),
  entry('diagnosis', '访问日志、错误日志与分层排障', '11 / 故障诊断',
    '先用 access/error log 固定时间窗口，再按 DNS、TCP、TLS、HTTP、upstream、应用逐层取证。',
    '[OPS] 错误日志中的 connect() failed、Connection refused、timeout、upstream prematurely closed 分别指向不同层：连接拒绝查后端监听与端口；超时查后端处理、依赖与网络；提前关闭查后端崩溃、超时或协议不匹配。访问日志可确认状态码、请求耗时、upstream 地址与请求量。\n证据顺序：影响范围与开始时间 → 最近变更 → error.log 与 access.log → 后端直连验证 → 监听与网络 → 应用日志与依赖。不要第一步重启 Nginx，避免丢失现场。修复后复验真实业务端点、错误率和延迟，并记录根因与回滚。',
    ['access.log', 'error.log', 'Connection refused', 'upstream timeout', 'direct probe', 'evidence chain'], 'APPROVAL_REQUIRED')
]
