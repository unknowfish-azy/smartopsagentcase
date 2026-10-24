const securityEntry = (id, title, summary, tags, sections) => ({
  id: `cloud-native.supply-chain.${id}`,
  domain: 'cloud-operations',
  platform: 'Cloud Native',
  service: 'supply-chain-security',
  type: 'SUPPLY CHAIN SECURITY RUNBOOK',
  title,
  summary,
  source: 'SmartOpsAgent Cloud Native Supply Chain Security Pack',
  section: 'SUPPLY_CHAIN_SECURITY',
  version: '1.0',
  risk: '涉及镜像、凭据、准入策略或证书变更时必须先验证范围并经过授权',
  tags: ['Supply Chain Security', '云原生安全', '镜像安全', ...tags],
  content: [
    `# ${title}`,
    `## 目标\n${summary}`,
    ...sections,
    '## 安全边界\n默认只执行读取、检查和生成报告。删除镜像、阻断工作负载、修改准入策略、吊销证书、轮换生产凭据等操作必须展示影响范围并获得确认。',
    '## 证据留存\n记录目标仓库、镜像 Digest、扫描或验证工具版本、规则版本、命令、退出码、原始输出、操作者、时间、环境、处置结果和 TraceId。Token、密码、私钥与机器人账号密钥必须脱敏。'
  ].join('\n\n')
})

export const cloudNativeSupplyChainSecurityEntries = [
  securityEntry('trivy-image-scan', 'Trivy 容器镜像漏洞与配置扫描', '在镜像进入测试或生产环境前发现系统包、应用依赖、Secret 和错误配置风险。', ['Trivy', 'CVE', 'Misconfiguration'], [
    '## 前置检查\n确认 Trivy 版本、漏洞数据库更新时间、镜像名称、Tag 与 Digest。优先使用不可变 Digest，避免扫描结果与实际发布镜像不一致。',
    '## 操作步骤\n1. 执行 `trivy image --download-db-only` 更新数据库。\n2. 执行 `trivy image --severity HIGH,CRITICAL --ignore-unfixed --format table IMAGE@DIGEST` 查看高危漏洞。\n3. 执行 `trivy image --scanners vuln,secret,misconfig IMAGE@DIGEST` 扩展检查。\n4. CI 中使用 `--exit-code 1` 建立门禁，并保存 JSON 或 SARIF 报告。\n5. 对照基础镜像、软件包版本和厂商公告制定修复计划。',
    '## 常见报错原因\n镜像仓库认证失败；漏洞数据库下载受限；代理或 DNS 异常；镜像架构不匹配；扫描缓存损坏；私有 CA 未被信任；只扫描 Tag 导致结果漂移。',
    '## 验证\n执行 `trivy image --format json --output trivy-result.json IMAGE@DIGEST`，确认报告中的 ArtifactName、ArtifactType、Digest、漏洞数量和门禁退出码与流水线记录一致。',
    '## 处置与回退\n优先升级依赖或基础镜像并重新构建。暂时豁免必须限定 CVE、镜像、到期时间和责任人；门禁误报时先恢复上一版规则，不直接关闭全部扫描。'
  ]),
  securityEntry('sbom-governance', 'SBOM 生成、校验与组件治理', '为镜像生成可追踪的软件物料清单，并关联组件、许可证、漏洞和发布版本。', ['SBOM', 'CycloneDX', 'SPDX', 'Syft'], [
    '## 操作步骤\n1. 使用 `syft IMAGE@DIGEST -o cyclonedx-json=sbom.cdx.json` 生成 CycloneDX SBOM。\n2. 或使用 `trivy image --format cyclonedx --output sbom.cdx.json IMAGE@DIGEST`。\n3. 保存镜像 Digest、构建 Commit、生成工具及版本。\n4. 使用 Schema 校验器检查格式。\n5. 将 SBOM 与制品、签名、扫描报告及发布记录建立关联。',
    '## 常见报错原因\n镜像层不可读；私有仓库无权限；组件缺少 PURL；多阶段构建带入无关依赖；SBOM 与新构建镜像 Digest 不一致；许可证字段缺失。',
    '## 验证\n确认 CycloneDX 或 SPDX 文件可解析，metadata.component、components、hashes 与目标镜像匹配；随机抽查关键运行时依赖是否存在。',
    '## 风险与治理\nSBOM 可能暴露内部包名和组件版本，应按资产敏感级别授权访问。发布后重新构建必须生成新 SBOM，禁止沿用旧文件。'
  ]),
  securityEntry('image-signing', 'Cosign 镜像签名与身份验证', '验证镜像来源、构建身份和制品完整性，降低镜像被替换或来源不明的风险。', ['Cosign', 'Sigstore', '签名', 'Attestation'], [
    '## 操作步骤\n1. 固定目标 `IMAGE@DIGEST`。\n2. 在受控流水线执行 `cosign sign IMAGE@DIGEST` 或使用 Keyless 身份签名。\n3. 执行 `cosign verify IMAGE@DIGEST --certificate-identity IDENTITY --certificate-oidc-issuer ISSUER`。\n4. 使用 `cosign attest` 关联 SBOM、SLSA provenance 或扫描证明。\n5. 将验证策略接入发布门禁。',
    '## 常见报错原因\n使用 Tag 而非 Digest；OIDC 身份或 Issuer 不匹配；签名存储仓库无权限；Fulcio/Rekor 网络不可达；公钥错误；签名对应旧 Digest。',
    '## 验证\n`cosign verify` 必须返回受信身份、Issuer 和目标 Digest；再用 `cosign verify-attestation` 检查证明类型和 Predicate 内容。',
    '## 密钥与回退\n私钥不得写入 Git、日志或普通配置文件。密钥泄露时立即停用对应身份、轮换密钥、重新签名可信制品并审查历史发布记录。'
  ]),
  securityEntry('harbor-governance', 'Harbor 项目、复制与机器人账号治理', '建立私有镜像仓库的项目隔离、最小权限、保留策略、复制、扫描和审计流程。', ['Harbor', 'Robot Account', 'Registry'], [
    '## 操作步骤\n1. 按团队或环境创建私有 Project。\n2. 为 CI 创建 Harbor robot account，仅授予推送目标仓库所需权限。\n3. 配置漏洞扫描、不可变 Tag、保留与垃圾回收策略。\n4. 配置跨站点复制并先执行 Dry Run。\n5. 定期审计成员、机器人账号、Webhook、复制任务和下载日志。',
    '## 常见报错原因\nRobot Token 过期或权限不足；仓库路径写错；私有 CA 未加入节点信任；复制端点网络不通；保留规则误匹配；垃圾回收期间制品不可用。',
    '## 验证\n使用最小权限账号执行登录、拉取和受控推送测试；确认未授权仓库访问被拒绝；检查复制任务状态、扫描结果和审计日志。',
    '## 风险与恢复\n删除 Artifact、执行垃圾回收、修改不可变规则前必须备份元数据并确认引用关系。凭据泄露时禁用账号、轮换 Secret 并检查异常推送。'
  ]),
  securityEntry('admission-policy', '镜像准入策略与发布门禁', '在 Kubernetes 创建工作负载前校验镜像仓库、Digest、签名、漏洞证明和安全基线。', ['Admission', 'ClusterImagePolicy', 'Policy Controller'], [
    '## 前置设计\n先在审计模式收集现有工作负载差距，明确系统 Namespace、应急通道、失败策略和策略责任人。门禁规则必须版本化并支持灰度。',
    '## 操作步骤\n1. 定义仅允许可信仓库和 Digest 的规则。\n2. 配置 Sigstore Policy Controller 的 `ClusterImagePolicy` 或等效策略。\n3. 校验签名身份、Attestation 和 SBOM/扫描证明。\n4. 在测试 Namespace 验证允许与拒绝样例。\n5. 逐步从 Audit 切换到 Enforce，并监控拒绝事件。',
    '## 常见报错原因\n策略选择器覆盖系统组件；证书身份匹配过严；Admission Webhook 无可用副本；fail-closed 导致控制面依赖阻塞；旧工作负载使用 Tag；证明格式与策略不一致。',
    '## 验证\n提交一个合规镜像和一个未签名镜像，确认前者成功、后者被拒绝且事件包含明确原因；检查 Webhook 可用性、延迟和审计日志。',
    '## 回滚\n策略异常时按预案回到 Audit 或恢复上一版本，保留拒绝证据。不得直接删除全部安全策略或长期设置 fail-open。'
  ]),
  securityEntry('cert-manager', 'cert-manager 证书签发与故障排查', '管理 Kubernetes 中证书申请、续期、Secret 写入和 ACME 验证故障。', ['cert-manager', 'Certificate', 'ACME', 'TLS'], [
    '## 操作步骤\n1. 执行 `kubectl get certificate,certificaterequest,order,challenge -A` 查看链路。\n2. 执行 `kubectl describe certificate NAME -n NAMESPACE` 检查 Conditions。\n3. 检查 Issuer/ClusterIssuer Ready 状态和 ACME Solver。\n4. 检查 DNS01/HTTP01 解析、Ingress、权限和网络。\n5. 查看 cert-manager controller 日志并验证生成的 TLS Secret。',
    '## 常见报错原因\nDNS 凭据无权限；域名解析未传播；HTTP01 路由被重写；Issuer 引用错误；RBAC 不足；系统时间异常；CA 不受信；Secret 名称冲突；ACME 速率限制。',
    '## 验证\n执行 `kubectl get certificate NAME -n NAMESPACE` 确认 Ready=True；检查 `tls.crt` 的域名、签发者和有效期；使用 `openssl s_client -connect HOST:443 -servername HOST` 验证实际入口证书。',
    '## 风险与恢复\n删除 Certificate、Secret 或更换 Issuer 可能导致 HTTPS 中断。先备份资源和证书元数据，验证新证书后再切换；私钥不得输出到普通日志。'
  ]),
  securityEntry('incident-response', '镜像供应链事件响应与隔离', '当发现恶意镜像、泄露凭据、错误签名或高危漏洞时，形成可审计的隔离、止损和恢复闭环。', ['Incident Response', '镜像供应链事件', '隔离'], [
    '## 事实采集\n记录告警来源、镜像仓库、Tag、Digest、签名身份、运行集群、Namespace、工作负载、首次发现时间、影响范围和当前证据。不要先删除现场。',
    '## 操作步骤\n1. 冻结相关发布流水线和凭据。\n2. 查询所有使用目标 Digest 的工作负载。\n3. 保存镜像元数据、SBOM、扫描报告、签名、审计日志和 Pod 事件。\n4. 经授权后隔离受影响工作负载并切换到已验证 Digest。\n5. 轮换泄露凭据，修复构建链并重新签名。\n6. 完成业务验证、影响评估和复盘。',
    '## 常见报错原因\n只按 Tag 搜索而遗漏同 Digest 镜像；删除镜像导致证据丢失；仅修复集群未封禁流水线凭据；回滚镜像同样受影响；审计日志保留期不足。',
    '## 验证\n确认集群不再运行受影响 Digest，可信版本健康，旧凭据失效，新制品通过扫描、SBOM 和签名验证，所有处置均关联 Incident 与 TraceId。',
    '## 恢复与复盘\n恢复发布前必须完成根因、影响范围、凭据轮换、制品重建和门禁验证。将错误路径、有效证据和改进后的 Runbook 沉淀为待审核知识。'
  ])
]
