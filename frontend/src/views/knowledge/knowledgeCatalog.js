import { linuxCoreNodes } from '../../../../knowledge/linux/coreKnowledge.js'
import { normalizeKnowledgeEntry, rankKnowledgeEntries } from './knowledgeModel.js'
import { linuxStorageNodes } from '../../../../knowledge/linux/storageKnowledge.js'
import { linuxFileNetworkRemoteNodes } from '../../../../knowledge/linux/fileNetworkRemoteKnowledge.js'
import { linuxSchedulerNodes } from '../../../../knowledge/linux/schedulerKnowledge.js'
import { networkEnvironmentEntries } from '../../../../knowledge/linux/networkEnvironmentKnowledge.js'
import { networkFoundationEntries } from '../../../../knowledge/linux/networkFoundationKnowledge.js'
import { networkL1L2VlanEntries, networkL1L2VlanIncidents, networkL1L2VlanRunbooks, networkL1L2VlanQuestions, networkL1L2VlanWrongAnswers, networkL1L2VlanRules, networkDigitalTwinSchema } from '../../../../knowledge/linux/networkL1L2VlanKnowledge.js'
import { networkRoutingEntries, networkRoutingIncidents, networkRoutingRunbooks, networkRoutingQuestions, networkRoutingWrongAnswers, networkRoutingRules, networkRoutingSchemas, resolveRoute, explainRoute } from '../../../../knowledge/linux/networkRoutingKnowledge.js'
import { linuxServiceEntries, linuxServiceIncidents, linuxServiceRunbooks, linuxServiceQuestions, linuxServiceWrongAnswers, linuxServiceRules, linuxServiceSchema, serviceEvidencePath } from '../../../../knowledge/linux/linuxServiceKnowledge.js'
import { webLampEntries, webLampIncidents, webLampRunbooks, webLampQuestions, webLampWrongAnswers, webLampRules, webLampSchema, parseServiceUrl, webEvidencePath, verificationLevelForEvidence } from '../../../../knowledge/linux/webLampKnowledge.js'
import { dnsBindEntries, dnsBindRules } from '../../../../knowledge/linux/dnsBindKnowledge.js'
import { fileSyncEntries, fileSyncRules } from '../../../../knowledge/linux/fileSyncKnowledge.js'
import { sambaEntries, sambaRules } from '../../../../knowledge/linux/sambaKnowledge.js'
import { mysql80Entries, mysql80Rules } from '../../../../knowledge/linux/mysql80Knowledge.js'
import { mysqlSqlEntries, mysqlSqlRules } from '../../../../knowledge/linux/mysqlSqlKnowledge.js'
import { shellCoreEntries, shellCoreRules } from '../../../../knowledge/linux/shellCoreKnowledge.js'
import { shellFlowEntries, shellFlowRules } from '../../../../knowledge/linux/shellFlowAutomationKnowledge.js'
import { shellAdvancedEntries, shellAdvancedRules } from '../../../../knowledge/linux/shellAdvancedAutomationKnowledge.js'
import { containerdHarborEntries, containerdHarborRules } from '../../../../knowledge/linux/containerdHarborKnowledge.js'
import { kubernetesFoundationEntries, kubernetesFoundationRules } from '../../../../knowledge/linux/kubernetesFoundationKnowledge.js'
import { dockerOperationsEntries, dockerOperationsRules } from '../../../../knowledge/linux/dockerOperationsKnowledge.js'
import { kubernetesResourceEntries, kubernetesResourceRules } from '../../../../knowledge/linux/kubernetesResourceOperationsKnowledge.js'
import { kubernetesSchedulingLifecycleEntries, kubernetesSchedulingLifecycleRules } from '../../../../knowledge/linux/kubernetesSchedulingLifecycleKnowledge.js'
import { kubernetesControllerServiceEntries, kubernetesControllerServiceRules } from '../../../../knowledge/linux/kubernetesControllerServiceKnowledge.js'
import { kubernetesIngressEntries, kubernetesIngressRules } from '../../../../knowledge/linux/kubernetesIngressKnowledge.js'
import { cloudNativeToolEntries } from '../../../../knowledge/cloud_ops/cloudNativeToolCatalog.js'
import { cloudNativeToolRunbookEntries } from '../../../../knowledge/cloud_ops/cloudNativeToolRunbooks.js'
import { cloudNativeLabEntries } from '../../../../knowledge/cloud_ops/cloudNativeLabCatalog.js'
import { cloudNativeObservabilityEntries } from '../../../../knowledge/cloud_ops/cloudNativeObservabilityCatalog.js'
import { cloudNativeGitOpsEntries } from '../../../../knowledge/cloud_ops/cloudNativeGitOpsCatalog.js'
import { cloudNativeSupplyChainSecurityEntries } from '../../../../knowledge/cloud_ops/cloudNativeSupplyChainSecurityCatalog.js'
import { ansibleEntries } from '../../../../knowledge/linux/ansibleAutomationKnowledge.js'
import { linuxAccessEntries } from '../../../../knowledge/linux/linuxIdentityAccessKnowledge.js'
import { nginxOpsEntries } from '../../../../knowledge/linux/nginxOperationsKnowledge.js'
import { mysql8AdminEntries } from '../../../../knowledge/linux/mysql8AdministrationKnowledge.js'

export const knowledgeDomains = [
  { id: 'linux', label: 'Linux 基础', detail: '文件描述符 / Shell 输入输出 / 用户权限 / Ansible 自动化' },
  { id: 'cloud-operations', label: 'CLOUD OPERATIONS', detail: '云计算 / DevOps / 云原生 / AIOps' },
  { id: 'docker', label: 'DOCKER', detail: '容器 / 镜像 / 网络 / 资源' },
  { id: 'mysql', label: 'MYSQL', detail: '连接 / 锁 / 复制 / 性能 / 备份恢复' },
  { id: 'nginx', label: 'NGINX', detail: 'HTTP / Upstream / TLS / 缓存 / 网关排障' },
  { id: 'ubuntu', label: 'UBUNTU', detail: 'Systemd / 磁盘 / 进程 / DNS' },
  { id: 'centos', label: 'CENTOS', detail: 'SELinux / Yum / 网络 / 权限' }
]

export const knowledgeEntries = [
  ...networkEnvironmentEntries,
  ...networkFoundationEntries,
  ...networkL1L2VlanEntries,
  ...networkRoutingEntries,
  ...linuxServiceEntries,
  ...webLampEntries,
  ...dnsBindEntries,
  ...fileSyncEntries,
  ...sambaEntries,
  ...mysql80Entries,
  ...mysqlSqlEntries,
  ...shellCoreEntries,
  ...shellFlowEntries,
  ...shellAdvancedEntries,
  ...containerdHarborEntries,
  ...kubernetesFoundationEntries,
  ...dockerOperationsEntries,
  ...kubernetesResourceEntries,
  ...kubernetesSchedulingLifecycleEntries,
  ...kubernetesControllerServiceEntries,
  ...kubernetesIngressEntries,
  ...ansibleEntries,
  ...linuxAccessEntries,
  ...nginxOpsEntries,
  ...mysql8AdminEntries,
  ...cloudNativeToolEntries,
  ...cloudNativeToolRunbookEntries,
  ...cloudNativeLabEntries,
  ...cloudNativeObservabilityEntries,
  ...cloudNativeGitOpsEntries,
  ...cloudNativeSupplyChainSecurityEntries,
  ...linuxCoreNodes.map(node => ({
    ...node,
    domain: 'linux', platform: 'Linux', service: 'shell', type: '工程知识卡',
    summary: node.scenario, source: 'Linux Core Knowledge v0.1', section: node.category,
    version: '0.1', risk: '参考资料 · 操作前查看命令风险',
    content: [
      `概念\n${node.concept}`, `原理\n${node.architecture}`,
      `命令卡\n${node.commands.map(item => `${item.command}\n用途：${item.purpose}\n条件：${item.parameters}\n风险：${item.risk}`).join('\n\n')}`,
      `生产场景\n${node.scenario}`, `排查流程\n${node.diagnosis.map((step, index) => `${index + 1}. ${step}`).join('\n')}`,
      `风险\n${node.risk}`, `工程经验\n${node.experience}`, `验证\n${node.verification}`,
      `关联知识\n${node.relatedIds.join('、')}`
    ].join('\n\n')
  })),
  ...linuxStorageNodes.map(node => ({
    ...node,
    domain: 'linux', platform: 'Linux', service: 'storage', type: 'STORAGE ENGINEERING',
    summary: node.scenario, source: 'Linux Storage Engineering v1.0', section: node.category,
    version: '1.0', risk: node.risk,
    content: [
      `概念\n${node.concept}`, `架构\n${node.architecture}`,
      `命令卡\n${node.commands.map(item => `${item.command}\n用途：${item.purpose}\n参数：${item.parameters}\n风险：${item.risk}`).join('\n\n')}`,
      `生产场景\n${node.scenario}`, `排查流程\n${node.diagnosis.map((step, index) => `${index + 1}. ${step}`).join('\n')}`,
      `风险\n${node.risk}`, `工程经验\n${node.experience}`, `验证\n${node.verification}`, `关联知识\n${node.relatedIds.join('、')}`
    ].join('\n\n')
  })),
  ...linuxFileNetworkRemoteNodes.map(node => ({
    ...node,
    domain: 'linux', platform: 'Linux', service: 'file-network-remote', type: 'ENGINEERING KNOWLEDGE',
    summary: node.scenario, source: 'Linux File Network Remote Operations v1.0', section: node.category,
    version: '1.0', risk: node.risk,
    content: [
      `概念\n${node.concept}`, `架构\n${node.architecture}`,
      `命令卡\n${node.commands.map(item => `${item.command}\n用途：${item.purpose}\n参数：${item.parameters}\n风险：${item.risk}`).join('\n\n')}`,
      `生产场景\n${node.scenario}`, `排查流程\n${node.diagnosis.map((step, index) => `${index + 1}. ${step}`).join('\n')}`,
      `风险\n${node.risk}`, `工程经验\n${node.experience}`, `验证\n${node.verification}`, `关联知识\n${node.relatedIds.join('、')}`
    ].join('\n\n')
  })),
  ...linuxSchedulerNodes.map(node => ({
    ...node,
    domain: 'linux', platform: 'Linux', service: 'scheduler', type: 'SCHEDULER ENGINEERING',
    summary: node.scenario, source: 'Linux Scheduler Engineering v1.0', section: node.category,
    version: '1.0', risk: node.risk,
    content: [
      `概念\n${node.concept}`, `架构\n${node.architecture}`,
      `命令卡\n${node.commands.map(item => `${item.command}\n用途：${item.purpose}\n参数：${item.parameters}\n风险：${item.risk}`).join('\n\n')}`,
      `生产场景\n${node.scenario}`, `排查流程\n${node.diagnosis.map((step, index) => `${index + 1}. ${step}`).join('\n')}`,
      `风险\n${node.risk}`, `工程经验\n${node.experience}`, `验证\n${node.verification}`, `关联知识\n${node.relatedIds.join('、')}`
    ].join('\n\n')
  })),
  {
    id: 'smartops-developer-knowledge-spec', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'knowledge base', type: 'DEVELOPER SPECIFICATION',
    title: 'SmartOpsAgent Knowledge Base Specification', summary: '定义 SmartOpsAgent 的云运维角色、知识组织、题库、Runbook、Incident、Agent 联动和安全边界。',
    content: 'Developer Knowledge Pack. Knowledge Base Specification. SmartOpsAgent 是具有生产运维经验的云计算运维助手。每个知识项可以关联 Question、Runbook、Incident 和 Command；知识可以生成基础题、命令题、场景题和事故题；重要知识应包含 Symptoms、Impact、Diagnosis Steps、Commands、Solution、Verification、Rollback 和 Postmortem。AI 必须证据优先、控制风险、保留原始证据，不得自动修改生产服务器。完整规范见 knowledge/cloud_ops/cloud_computing_ops_kb.md。',
    source: 'Local / SmartOpsAgent Developer Knowledge Pack', section: 'Knowledge Base Specification', version: '1.0', risk: 'REFERENCE', tags: ['Knowledge Base Specification', 'Question Bank', 'Runbook', 'Incident', 'Command', 'Agent', 'OCR', 'Visual Sentinel', '安全边界']
  },
  {
    id: 'ocr-image-operations-notes', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'ocr', type: 'OCR KNOWLEDGE CANDIDATE',
    title: 'OCR 图片运维笔记：Kubernetes、镜像源与节点拓扑', summary: '将 Kubernetes 架构、镜像源、快照初始化和节点工作负载图片校正为中文 Markdown 运维笔记。',
    content: '来源：C:/Users/33908/Desktop/ocr。内容包含控制面与工作节点链路、单主与多主架构、Yum/Containerd/Docker 镜像源、快照初始化流程、Nginx/MySQL/Redis 与存储拓扑。OCR 结果必须人工审核，不能直接执行图片中的命令。完整资料见 knowledge/ocr/ocr_image_notes.md。',
    source: 'User-provided OCR image set / manually corrected', section: 'OCR Image Operations', version: '1.0', risk: 'REVIEW_REQUIRED', tags: ['OCR', 'Kubernetes', 'Containerd', 'Docker', 'Yum', '快照', '人工审核']
  },
  {
    id: 'cloud-operations-definition', domain: 'cloud-operations', platform: 'Cloud', service: 'cloud operations', type: 'KNOWLEDGE PACK',
    title: '云计算运维基础定义', summary: '云计算运维通过标准化流程、自动化工具和管理体系，部署、管理、监控、优化云环境中的计算、网络、存储、应用和基础服务。',
    content: '云计算运维的目标是保证业务稳定运行，提高可靠性和运维效率，降低人工操作风险，实现自动化和智能化运维。云代表厂商提供的计算、网络、存储、数据库、安全和监控资源；计算具有按需使用、弹性扩展、资源池化和自动化管理特点；运维包含运行、维护和优化。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Definition', version: 'Version-independent', risk: 'REFERENCE', tags: ['cloud computing', 'cloud operations', '弹性扩展', '资源池化', 'AIOps']
  },
  {
    id: 'cloud-operations-responsibilities', domain: 'cloud-operations', platform: 'Cloud', service: 'operations', type: 'KNOWLEDGE PACK',
    title: '云计算运维工程师职责', summary: '运维工程师负责环境搭建、项目部署、监控、故障排查、巡检、客户支持和运维文档。',
    content: '项目环境包括 Linux、JDK、Tomcat、MySQL、Redis、Nginx 和环境变量。部署流程是代码、构建、上传、安装依赖、配置环境、启动服务、测试访问。监控对象包括 CPU、内存、磁盘、网络、服务状态、请求量、响应时间、数据库连接数和慢 SQL。故障处理遵循现象、影响范围、收集证据、定位问题、制定方案、执行修复、验证恢复、记录复盘。巡检包括服务器、服务、备份、日志和安全检查。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Responsibilities', version: 'Version-independent', risk: 'READ_ONLY', tags: ['部署', '监控', '故障排查', '巡检', '运维文档', '证据优先']
  },
  {
    id: 'cloud-operations-roles', domain: 'cloud-operations', platform: 'Cloud', service: 'career', type: 'CAREER GUIDE',
    title: '云计算运维岗位方向', summary: '岗位方向包括 Linux 运维、网络、DBA、DevOps、容器、Kubernetes、技术支持和实施工程师。',
    content: 'Linux 系统运维负责服务器、系统管理、服务部署和性能优化；网络工程师负责 TCP/IP、交换机、路由器和网络故障；DBA 负责 MySQL、Redis、MongoDB 的部署、备份、优化和恢复；DevOps 负责开发与运维自动化；容器和 Kubernetes 工程师负责运行时、集群、编排、扩缩容和服务治理；技术支持负责客户问题定位；实施工程师负责上线、环境部署和培训。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Roles', version: 'Version-independent', risk: 'REFERENCE', tags: ['Linux 运维', '网络工程师', 'DBA', 'DevOps', '技术支持', '实施工程师']
  },
  {
    id: 'cloud-operations-foundations', domain: 'cloud-operations', platform: 'Linux', service: 'foundation', type: 'LEARNING PATH',
    title: '云计算运维基础技术体系', summary: '基础技术路线包括 Linux、网络、Shell、Python、数据库和 Web 服务。',
    content: 'Linux 是云服务器基础操作系统，学习文件管理、用户权限、进程、服务、日志、网络和 Shell。网络基础包括 OSI、TCP/IP、交换机、路由器、DNS、HTTP 和 HTTPS。Shell 用于批量部署、巡检和日志处理；Python 用于自动化工具、API 调用和数据处理。MySQL 是关系型数据库，Redis 是内存型缓存，MongoDB 是文档型数据库。Nginx 提供 Web、反向代理、负载均衡和 HTTPS，Tomcat 运行 Java Web 项目。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Technology Foundations', version: 'Version-independent', risk: 'REFERENCE', tags: ['Linux', 'TCP/IP', 'DNS', 'HTTP', 'Shell', 'Python', 'MySQL', 'Redis', 'MongoDB', 'Nginx', 'Tomcat']
  },
  {
    id: 'cloud-operations-ha-and-load-balancing', domain: 'cloud-operations', platform: 'Linux', service: 'high availability', type: 'ARCHITECTURE GUIDE',
    title: '高可用与负载均衡技术', summary: 'Keepalived、LVS 和 HAProxy 用于主备切换、TCP/HTTP 负载均衡和高性能流量分发。',
    content: 'Keepalived 基于 VRRP 实现服务高可用和主备切换。LVS（Linux Virtual Server）提供高性能负载均衡。HAProxy 支持 TCP 和 HTTP 负载均衡。设计高可用架构时要同时考虑健康检查、故障切换、依赖服务、恢复验证和回滚。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'High Availability', version: 'Version-independent', risk: 'REFERENCE', tags: ['Keepalived', 'VRRP', 'LVS', 'HAProxy', '高可用', '负载均衡']
  },
  {
    id: 'cloud-operations-observability', domain: 'cloud-operations', platform: 'Cloud Native', service: 'observability', type: 'OBSERVABILITY GUIDE',
    title: '云计算运维监控与日志体系', summary: 'Zabbix、Prometheus、Grafana、Alertmanager 和 ELK 组成指标、告警、可视化和日志分析体系。',
    content: 'Zabbix 用于服务器监控、指标采集和告警；Prometheus 面向云原生监控，核心是 Metrics 和 PromQL；Grafana 展示监控 Dashboard；Alertmanager 管理告警并通过邮件、微信或钉钉通知；ELK 由 Elasticsearch、Logstash、Kibana 组成，用于日志采集、搜索和分析。可观测性需要把指标、日志、链路、变更时间线和影响范围结合起来。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Monitoring And Logs', version: 'Version-independent', risk: 'READ_ONLY', tags: ['Zabbix', 'Prometheus', 'PromQL', 'Grafana', 'Alertmanager', 'ELK', '日志分析', '可观测性']
  },
  {
    id: 'cloud-operations-cicd-automation', domain: 'cloud-operations', platform: 'DevOps', service: 'delivery', type: 'AUTOMATION GUIDE',
    title: '自动化运维与 CI/CD', summary: 'Ansible、Git 和 Jenkins 将批量配置、持续集成和持续交付连接成自动化发布流程。',
    content: 'Ansible 用于批量安装软件、批量执行命令和批量配置服务器。CI/CD 的目标是自动化软件发布，典型流程是代码提交、自动构建、自动测试和自动部署。所有自动化动作都应有权限边界、变更记录、审批、失败处理、回滚和发布后验证。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Automation And Delivery', version: 'Version-independent', risk: 'APPROVAL_REQUIRED', tags: ['Ansible', 'Git', 'Jenkins', 'CI/CD', '持续集成', '持续交付', '回滚']
  },
  {
    id: 'cloud-operations-containers', domain: 'cloud-operations', platform: 'Docker', service: 'container', type: 'CONTAINER GUIDE',
    title: 'Docker 与容器运行时', summary: 'Docker 将应用和依赖打包成镜像，再以容器运行；Containerd 负责容器生命周期和运行时管理。',
    content: 'Docker 的基本链路是代码、Docker Image、Container、运行服务。容器 up 不等于业务 ready，必须结合进程监听、健康检查、依赖服务、日志和真实请求验证。Containerd 是容器运行时，负责启动、管理和运行容器。排障时应区分镜像问题、容器进程问题、网络问题、存储问题和应用健康问题。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Containers', version: 'Docker Engine 20+', risk: 'READ_ONLY', tags: ['Docker', 'Containerd', 'Image', 'Container', 'healthcheck', 'readiness']
  },
  {
    id: 'cloud-operations-kubernetes', domain: 'cloud-operations', platform: 'Kubernetes', service: 'orchestration', type: 'CLOUD NATIVE GUIDE',
    title: 'Kubernetes 容器编排', summary: 'Kubernetes 用于自动部署、自动扩缩容、自动恢复和服务管理，核心对象包括 Pod、Service、Deployment、Namespace 和 Node。',
    content: 'Kubernetes 是容器编排平台。Pod 承载容器，Deployment 管理期望副本和滚动发布，Service 提供服务发现和访问入口，Namespace 进行逻辑隔离，Node 提供运行资源。自动扩缩容和自动恢复不能替代健康检查、资源限制、依赖分析、发布关联和恢复验证。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Kubernetes', version: 'Kubernetes 1.24+', risk: 'READ_ONLY', tags: ['Kubernetes', 'K8S', 'Pod', 'Service', 'Deployment', 'Namespace', 'Node', '自动扩缩容']
  },
  {
    id: 'cloud-operations-learning-path', domain: 'cloud-operations', platform: 'Cloud', service: 'learning', type: 'LEARNING PATH',
    title: '云计算运维学习路线', summary: '从 Linux 和网络基础开始，逐步学习脚本、数据库、Web、监控、Docker、Kubernetes、DevOps 和 AI 运维。',
    content: '推荐阶段：1 Linux 基础；2 网络基础；3 Shell/Python 自动化；4 数据库；5 Web 服务；6 监控体系；7 Docker；8 Kubernetes；9 DevOps；10 AI 运维。每个阶段都应配合实验环境、部署任务、日志分析、故障排查、复盘记录和安全边界，而不是只记忆概念。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'Learning Path', version: 'Version-independent', risk: 'REFERENCE', tags: ['学习路线', 'Linux', '网络', 'Shell', 'Python', 'Docker', 'Kubernetes', 'DevOps', 'AI 运维']
  },
  {
    id: 'cloud-operations-aiops', domain: 'cloud-operations', platform: 'AIOps', service: 'intelligent operations', type: 'AI OPERATIONS GUIDE',
    title: 'AI 时代的智能运维', summary: 'AIOps 将人工智能、自动化、知识库和智能诊断结合，用于故障预测、日志分析、巡检和智能问答。',
    content: 'AI 运维可以辅助故障预测、日志分析、自动巡检和智能问答。AI 生成的结论必须和原始证据分离，优先事实、影响范围、时间线、变更关联和低风险检查；不能因为模型建议就自动修改生产服务器。知识库、Runbook、Operation History 和题库可以共同形成学习、诊断、复盘和能力提升闭环。',
    source: 'Built-in / Cloud Computing Operations Pack', section: 'AIOps', version: 'Version-independent', risk: 'APPROVAL_REQUIRED', tags: ['AIOps', '人工智能', '智能诊断', '知识库', '故障预测', '日志分析', '智能问答', '证据优先']
  },
  { id: 'nginx-502-diagnosis', domain: 'nginx', platform: 'Nginx', service: 'nginx', type: 'DIAGNOSIS RUNBOOK', title: '502 Bad Gateway Diagnosis Runbook', summary: '从 upstream、网络、DNS 与应用健康状态逐层确认 502 的边界。', content: '先确认影响范围，再检查 Nginx error log、upstream listener、网络连通性、容器状态和最近变更。不要把 502 直接等同于 Nginx 故障。', source: 'Built-in / Nginx Operations Pack', section: 'Diagnosis', version: '1.24+', risk: 'READ_ONLY', tags: ['502', 'upstream', 'gateway', 'http'] },
  { id: 'docker-readiness', domain: 'docker', platform: 'Docker', service: 'container', type: 'DIAGNOSIS RUNBOOK', title: 'Container Up vs Application Ready', summary: '区分容器存活、进程监听、健康检查与依赖服务就绪状态。', content: '容器 up 不代表应用 ready，需要检查进程、健康检查、依赖服务、日志和真实请求。', source: 'Built-in / Docker Operations Pack', section: 'Symptoms', version: 'Engine 20+', risk: 'READ_ONLY', tags: ['healthcheck', 'container', 'restart', 'readiness'] },
  { id: 'mysql-connections', domain: 'mysql', platform: 'MySQL', service: 'mysql', type: 'DIAGNOSIS RUNBOOK', title: 'MySQL Connection Exhaustion', summary: '区分连接池、长连接、活跃会话、资源压力与 max_connections。', content: 'MySQL connection timeout 不等于数据库宕机，应结合连接数、线程、锁、网络和应用连接池证据判断。', source: 'Built-in / MySQL Operations Pack', section: 'Investigation', version: '5.7 / 8.0+', risk: 'READ_ONLY', tags: ['connection', 'timeout', 'max_connections', 'database'] },
  { id: 'ubuntu-disk', domain: 'ubuntu', platform: 'Ubuntu', service: 'host', type: 'DIAGNOSIS RUNBOOK', title: 'Ubuntu Disk And Inode Pressure', summary: '结合容量、inode、日志增长和挂载状态判断磁盘故障边界。', content: '磁盘使用率高时同时检查 inode、挂载点、日志增长、打开但已删除文件和清理风险。', source: 'Built-in / Ubuntu Operations Pack', section: 'Evidence', version: '20.04 / 22.04 / 24.04', risk: 'READ_ONLY', tags: ['disk', 'inode', 'filesystem', 'log'] },
  { id: 'centos-selinux', domain: 'centos', platform: 'CentOS', service: 'host', type: 'ANTI-PATTERN', title: 'Permission Denied Is Not A Reason For chmod 777', summary: '先检查 owner、ACL 与 SELinux context，再决定是否需要安全变更。', content: '权限错误不能直接通过 chmod 777 掩盖，应先收集 owner、ACL、SELinux、进程用户和审计证据。', source: 'Built-in / CentOS Operations Pack', section: 'Common Mistakes', version: '7 / Stream', risk: 'HIGH', tags: ['permission', 'selinux', 'acl', 'security'] }
  ,
  {
    id: 'smartopsagent-enterprise-operation-brain', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'operation brain', type: 'ENGINEERING KNOWLEDGE',
    title: 'SmartOpsAgent 企业级运维智能体规范', summary: '定义观察、证据、分析、审批、验证和经验沉淀闭环，供知识查阅与题库训练使用。',
    content: 'SmartOpsAgent 不是普通聊天机器人。回答必须先事实、后分析、最后建议；默认只观察、只分析、只建议。知识可关联 Question、Wrong Question、Runbook、Incident 和 Command。生产操作必须经过风险说明、人工审批、回滚和验证。完整源文件：knowledge/smartopsagent_brain.md。',
    source: 'Local / SmartOpsAgent Enterprise Operation Brain', section: 'System Philosophy', version: '1.0', risk: 'REFERENCE', tags: ['Observe', 'Evidence First', 'Human Approval', 'Runbook', 'Incident', '错题学习', '安全审批']
  },
  {
    id: 'linux-cpu-high', domain: 'cloud-operations', platform: 'Linux', service: 'host', type: 'DIAGNOSIS RUNBOOK',
    title: 'Linux CPU 高使用率排查', summary: '用 top、ps 和 iostat 区分计算压力、IO 等待、流量突增与异常进程。',
    content: '现象通常是系统慢、请求延迟高或 load 增长。先查看 top、ps aux --sort=-%cpu，再用 iostat 判断 IO 等待；结合监控、流量和最近变更。常见原因包括死循环、流量突增、恶意进程和线程争用。没有确认进程归属、影响范围和替代方案前，不要直接 kill -9 或重启。验证 CPU、load 和业务延迟恢复。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Linux Fault Library', version: 'Version-independent', risk: 'READ_ONLY', tags: ['Linux', 'top', 'ps', 'iostat', 'CPU', 'load', 'high CPU', 'Evidence First']
  },
  {
    id: 'linux-disk-full', domain: 'cloud-operations', platform: 'Linux', service: 'host', type: 'DIAGNOSIS RUNBOOK',
    title: 'Linux 磁盘与 inode 用尽', summary: '同时检查容量、inode、挂载点、日志增长和已删除但仍打开的文件。',
    content: '使用 df -h 查看容量，df -i 查看 inode，du -xhd1 定位目录。确认日志、容器层、挂载点和删除文件句柄后再处理。优先归档或轮转已确认的日志，必要时扩容。禁止对未知路径 rm -rf，禁止删除数据库文件或正在写入的日志。清理后验证服务、容量、inode 和告警。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Linux Fault Library', version: 'Version-independent', risk: 'MEDIUM', tags: ['Linux', 'df -h', 'df -i', 'du', 'disk', 'inode', 'log', 'rm -rf risk']
  },
  {
    id: 'mysql-too-many-connections', domain: 'cloud-operations', platform: 'MySQL', service: 'mysql', type: 'DIAGNOSIS RUNBOOK',
    title: 'MySQL Too Many Connections', summary: '从连接池、长连接、慢请求、锁等待和资源压力判断连接耗尽原因。',
    content: '出现连接超时或 Too many connections 时，先执行只读查询 SHOW PROCESSLIST，查看 Threads_connected、Threads_running 和 max_connections；同时检查应用连接池、连接泄漏、长事务、慢查询和内存压力。连接数高不等于 CPU 高。不要盲目提高 max_connections，先限制异常流量、修复连接泄漏并评估资源，变更前记录配置和回滚值。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'MySQL Fault Library', version: 'MySQL 5.7 / 8.0+', risk: 'READ_ONLY', tags: ['MySQL', 'show processlist', 'Threads_connected', 'Threads_running', 'max_connections', 'connection pool', 'connection leak']
  },
  {
    id: 'mysql-slow-sql', domain: 'cloud-operations', platform: 'MySQL', service: 'mysql', type: 'DIAGNOSIS RUNBOOK',
    title: 'MySQL 慢 SQL 分析', summary: '结合慢查询日志、EXPLAIN、锁等待和业务时间线定位性能瓶颈。',
    content: '先确认慢查询的时间范围、调用接口和影响范围，再查看 slow query log 和 EXPLAIN 计划。检查索引选择、扫描行数、锁等待、事务范围和数据库资源。优先在低风险环境验证索引或 SQL 改写，变更后比较 p95 延迟、错误率和执行计划，保留回滚方案。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'MySQL Fault Library', version: 'MySQL 5.7 / 8.0+', risk: 'READ_ONLY', tags: ['MySQL', 'slow query', 'EXPLAIN', 'index', 'lock', 'performance']
  },
  {
    id: 'nginx-502-production', domain: 'nginx', platform: 'Nginx', service: 'nginx-production', type: 'PRODUCTION DIAGNOSIS',
    title: 'Nginx 502 生产排查', summary: '先看 error.log、upstream 和后端健康，不把 502 直接归因于 Nginx。',
    content: '502 表示网关没有得到有效上游响应。先确认影响范围、开始时间和最近发布；查看 access.log、error.log；检查 upstream 地址和监听端口；用 curl 直连后端；再检查容器、服务健康、DNS 和网络。connect() failed (111: Connection refused) 时优先验证后端进程与监听地址。不要第一步重启 Nginx，避免丢失现场或只掩盖症状。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Nginx Fault Library', version: 'Nginx 1.24+', risk: 'READ_ONLY', tags: ['Nginx', '502', 'access.log', 'error.log', 'upstream', 'curl', 'reverse proxy', 'Evidence First']
  },
  {
    id: 'nginx-504-timeout', domain: 'nginx', platform: 'Nginx', service: 'nginx', type: 'PRODUCTION DIAGNOSIS',
    title: 'Nginx 504 超时排查', summary: '区分网关超时、后端处理慢、数据库等待和网络延迟。',
    content: '504 通常表示上游响应超过等待时间。比较 Nginx timeout、后端处理时间、数据库耗时、线程池和网络延迟。提高 timeout 只能缓解症状，不能替代性能定位。验证时同时看请求延迟、错误率、后端资源和用户影响范围。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Nginx Fault Library', version: 'Nginx 1.24+', risk: 'READ_ONLY', tags: ['Nginx', '504', 'timeout', 'upstream', 'latency', 'database']
  },
  {
    id: 'docker-container-exit', domain: 'docker', platform: 'Docker', service: 'container', type: 'DIAGNOSIS RUNBOOK',
    title: 'Docker 容器异常退出', summary: '通过容器日志、退出码、配置、依赖和资源限制定位启动失败。',
    content: '先使用 docker ps -a、docker logs 和 docker inspect，确认退出码、启动参数、环境变量、挂载、依赖和资源限制。区分镜像问题、进程启动问题、网络问题、卷问题和应用健康问题。容器 Up 不代表业务 Ready，必须结合 healthcheck 和真实请求验证。不要在未保留日志和现场前反复 restart。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Docker Fault Library', version: 'Docker Engine 20+', risk: 'READ_ONLY', tags: ['Docker', 'docker ps', 'docker logs', 'docker inspect', 'exit code', 'healthcheck', 'container']
  },
  {
    id: 'kubernetes-crashloopbackoff', domain: 'cloud-operations', platform: 'Kubernetes', service: 'pod', type: 'DIAGNOSIS RUNBOOK',
    title: 'Kubernetes CrashLoopBackOff 排查', summary: '用 describe、当前日志和 previous 日志分析容器反复崩溃。',
    content: 'CrashLoopBackOff 表示容器反复退出并进入退避重启。先执行 kubectl describe pod 查看事件、探针和调度信息，再执行 kubectl logs 和 kubectl logs --previous 查看当前及上一次日志。检查启动命令、配置、Secret、依赖服务、端口、健康检查和最近发布。不要只删除 Pod，应确认 Deployment 版本、期望副本和恢复验证。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Kubernetes Fault Library', version: 'Kubernetes 1.24+', risk: 'READ_ONLY', tags: ['Kubernetes', 'CrashLoopBackOff', 'kubectl describe pod', 'kubectl logs', 'kubectl logs --previous', 'probe', 'deployment']
  },
  {
    id: 'kubernetes-oomkilled', domain: 'cloud-operations', platform: 'Kubernetes', service: 'pod', type: 'DIAGNOSIS RUNBOOK',
    title: 'Kubernetes OOMKilled 处理', summary: '对比容器限制、工作集、节点压力和应用内存增长，再决定资源调整。',
    content: '确认 Pod 的退出原因、limits、requests、工作集和节点内存压力，结合应用日志和发布版本判断泄漏、突发流量还是限制过小。调整资源前要说明成本、调度影响和回滚值；恢复后验证重启次数、延迟、错误率和节点余量。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Kubernetes Fault Library', version: 'Kubernetes 1.24+', risk: 'MEDIUM', tags: ['Kubernetes', 'OOMKilled', 'memory limit', 'requests', 'limits', 'resource pressure']
  },
  {
    id: 'monitoring-alert-response', domain: 'cloud-operations', platform: 'Cloud Native', service: 'observability', type: 'OPERATIONS WORKFLOW',
    title: '告警响应与证据链', summary: '把指标、日志、链路、变更和用户报告放在同一条时间线上。',
    content: '告警流程是确认告警、判断影响、收集证据、建立假设、低风险验证、修复或回滚、验证恢复、关闭并复盘。不要只看单个指标，也不要因为告警恢复就跳过根因记录。P1/P2 事件要明确升级对象、沟通节奏和下一次更新时间。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Monitoring And Incident', version: 'Version-independent', risk: 'READ_ONLY', tags: ['Prometheus', 'Grafana', 'Zabbix', 'Alertmanager', 'metrics', 'logs', 'timeline', 'incident']
  },
  {
    id: 'incident-response-workflow', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'incident response', type: 'INCIDENT RUNBOOK',
    title: 'Incident 响应工作流', summary: '从现象、影响和时间线开始，经过证据、处置、验证和复盘形成闭环。',
    content: 'Incident 至少记录 incident_id、严重度、影响范围、开始时间、时间线、证据、假设、根因、处置、恢复验证、预防措施和关联 Runbook。回答时先写事实，再写置信度和待验证假设；如果证据不足，明确说明未知并继续收集。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Incident Management', version: '1.0', risk: 'READ_ONLY', tags: ['Incident', 'P1', 'P2', 'timeline', 'evidence', 'root cause', 'postmortem']
  },
  {
    id: 'runbook-standard', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'runbook', type: 'RUNBOOK STANDARD',
    title: '运维 Runbook 编写标准', summary: '每个操作流程都要写清前置检查、风险、审批、回滚和验证。',
    content: 'Runbook 包含目的、适用环境、版本、症状、前置检查、只读命令、决策分支、修复步骤、风险、审批点、回滚、验证、升级条件和复盘链接。命令必须标注只读或有副作用，Runbook 是指导文档，不代表系统会自动执行命令。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Runbook System', version: '1.0', risk: 'APPROVAL_REQUIRED', tags: ['Runbook', 'pre-check', 'rollback', 'verification', 'approval', 'change safety']
  },
  {
    id: 'wrong-answer-learning', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'question bank', type: 'LEARNING SYSTEM',
    title: '错题原因与间隔复习', summary: '记录为什么错、知识薄弱点、置信度和下次复习时间，而不是保存所有做过的题。',
    content: '只有真正答错、低置信度答对或重复犯错的题目进入错题库。错因可分为概念误解、命令混淆、配置误解、诊断路径错误、风险判断错误、记忆错误、粗心、猜测和未知。首次答错尽快复习，重复错误缩短间隔，连续正确逐渐拉长间隔。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Question Bank', version: '1.0', risk: 'REFERENCE', tags: ['Question Bank', 'Wrong Question', 'spaced repetition', 'mastery', 'confidence', 'timeSpent']
  },
  {
    id: 'remote-operation-safety', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'remote operations', type: 'SAFETY POLICY',
    title: '远程运维安全审批', summary: '高风险操作必须命令预览、风险说明、人工审批、执行记录和恢复验证。',
    content: '默认不执行生产操作，不自动修改数据库、不删除日志、不关闭防火墙、不使用 chmod 777、不盲目重启服务。远程命令展示目的、目标、风险、预期结果和回滚方式；删除、停机、回滚、扩容等高风险动作需要二次确认。执行后必须记录结果并验证服务和业务。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Security', version: '1.0', risk: 'HIGH', tags: ['SSH', 'remote operation', 'command preview', 'approval', 'rollback', 'audit', 'production safety']
  },
  {
    id: 'visual-sentinel-event', domain: 'cloud-operations', platform: 'SmartOpsAgent', service: 'visual sentinel', type: 'VISION OPERATIONS',
    title: '视觉巡检哨兵事件', summary: '将用户主动提供的截图或窗口识别为可审计的 VisionEvent，不替代日志和指标。',
    content: 'Spider Sentinel 可处理用户主动提供的截图、窗口或浏览器画面，通过 OCR 和界面识别提取错误文本、位置、来源、时间和置信度。视觉证据只能作为线索，必须与日志、监控和变更时间线交叉验证；禁止后台偷偷截图或访问未授权数据。',
    source: 'Built-in / SmartOpsAgent Enterprise Operation Brain', section: 'Visual Sentinel', version: '1.0', risk: 'READ_ONLY', tags: ['Spider Sentinel', 'OCR', 'VisionEvent', 'screenshot', 'confidence', 'privacy', 'evidence']
  }
]

export { networkL1L2VlanEntries, networkL1L2VlanIncidents, networkL1L2VlanRunbooks, networkL1L2VlanQuestions, networkL1L2VlanWrongAnswers, networkL1L2VlanRules, networkDigitalTwinSchema, networkRoutingEntries, networkRoutingIncidents, networkRoutingRunbooks, networkRoutingQuestions, networkRoutingWrongAnswers, networkRoutingRules, networkRoutingSchemas, resolveRoute, explainRoute, linuxServiceEntries, linuxServiceIncidents, linuxServiceRunbooks, linuxServiceQuestions, linuxServiceWrongAnswers, linuxServiceRules, linuxServiceSchema, serviceEvidencePath, webLampEntries, webLampIncidents, webLampRunbooks, webLampQuestions, webLampWrongAnswers, webLampRules, webLampSchema, parseServiceUrl, webEvidencePath, verificationLevelForEvidence }

const linuxProcessEntry = {
  id: 'linux-process-management', moduleId: 'LINUX-PROCESS-001', domain: 'cloud-operations', platform: 'Linux', service: 'process', type: 'PROCESS MANAGEMENT MODULE',
  title: 'Linux Process Management', summary: 'Read-only evidence workflow for PID, PPID, CPU, IO, memory and process lifecycle states.',
  content: 'Programs and processes are different objects. Use ps aux, ps -ef, top, uptime, iostat, free -h, dmesg and /proc for evidence. States include R, S, D, T, Z zombie and X. Prefer SIGTERM before SIGKILL; kill -9 is escalation guidance only. Investigate D state through storage IO and trace zombie processes through PPID. Related modules: LINUX-MEMORY, LINUX-CPU, LINUX-DISK, LINUX-SYSTEMD, LINUX-SHELL, LINUX-PERFORMANCE.',
  source: 'Local / Linux Process Management Knowledge Module', section: 'LINUX-PROCESS-001', version: 'Version-independent', risk: 'READ_ONLY', relatedTool: 'processes', tags: ['LINUX-PROCESS-001', 'Linux', 'process', 'PID', 'PPID', 'ps aux', 'top', 'kill', 'D state', 'zombie', 'iostat', '/proc']
}
knowledgeEntries.push(linuxProcessEntry)
const searchableKnowledgeEntries = knowledgeEntries.map(entry => {
  const domainId = String(entry.domain || 'uncategorized')
  const serviceId = String(entry.service || 'general')
  const sectionId = String(entry.section || 'general')
  return {
    ...normalizeKnowledgeEntry(entry),
    directory: Object.freeze({
      domainId,
      serviceId,
      sectionId,
      pathKey: `${domainId}/${serviceId}/${sectionId}`
    })
  }
})

function buildKnowledgeTree() {
  const root = { id: 'knowledge-root', kind: 'root', label: 'KNOWLEDGE BASE', children: [] }
  const folders = new Map([['knowledge-root', root]])
  const declaredDomainIds = new Set(knowledgeDomains.map(domain => domain.id))
  const catalogDomains = [...knowledgeDomains]
  for (const entry of searchableKnowledgeEntries) {
    if (!declaredDomainIds.has(entry.directory.domainId)) {
      declaredDomainIds.add(entry.directory.domainId)
      catalogDomains.push({ id: entry.directory.domainId, label: entry.directory.domainId.toUpperCase(), detail: 'LOCAL KNOWLEDGE PACK' })
    }
  }
  const ensureFolder = (parent, id, label, detail = '') => {
    let folder = folders.get(id)
    if (!folder) {
      folder = { id, kind: 'folder', label, detail, parentId: parent.id, children: [], count: 0 }
      folders.set(id, folder)
      parent.children.push(folder)
    }
    return folder
  }
  for (const domain of catalogDomains) {
    const domainNode = ensureFolder(root, `domain:${domain.id}`, domain.label, domain.detail)
    for (const entry of searchableKnowledgeEntries.filter(item => item.directory.domainId === domain.id)) {
      const { serviceId: service, sectionId: section } = entry.directory
      const serviceNode = ensureFolder(domainNode, `service:${domain.id}:${service}`, service.toUpperCase())
      const sectionNode = ensureFolder(serviceNode, `section:${domain.id}:${service}:${section}`, section)
      sectionNode.children.push({ ...entry, kind: 'entry', parentId: sectionNode.id, directoryId: sectionNode.id, label: entry.title, children: [] })
    }
  }
  const count = node => {
    if (node.kind === 'entry') return 1
    node.count = node.children.reduce((total, child) => total + count(child), 0)
    return node.count
  }
  count(root)
  return root
}

export const knowledgeTree = buildKnowledgeTree()
const knowledgeNodeIndex = new Map()
const indexKnowledgeNode = (node, path = []) => {
  knowledgeNodeIndex.set(node.id, { node, path })
  for (const child of node.children || []) indexKnowledgeNode(child, [...path, node])
}
indexKnowledgeNode(knowledgeTree)
const freezeTree = node => {
  for (const child of node.children || []) freezeTree(child)
  Object.freeze(node.children)
  Object.freeze(node)
}
freezeTree(knowledgeTree)

export function getKnowledgeTree() { return knowledgeTree }
export function getKnowledgeNode(nodeId) { return knowledgeNodeIndex.get(nodeId)?.node || null }
export function getKnowledgePath(nodeId) {
  const item = knowledgeNodeIndex.get(nodeId)
  return item ? [...item.path, item.node] : []
}

export function searchKnowledgeEntries(filters = {}) {
  return rankKnowledgeEntries(searchableKnowledgeEntries, filters)
}
