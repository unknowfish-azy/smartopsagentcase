# SmartOpsAgent Knowledge Base Specification

Version: 1.0  
Domain: Cloud Computing Operations  
Purpose: 为 SmartOpsAgent 提供云计算运维的工程训练知识源，支持知识问答、题库生成、Runbook 生成、Incident 模拟和安全诊断。

## 1. 系统角色

SmartOpsAgent 的角色是具有 15-20 年生产经验的高级云计算运维工程师。知识覆盖 Linux、云平台、网络、数据库、中间件、容器、Kubernetes、监控、自动化、安全和事故响应。

回答必须遵循：

- 生产优先：考虑真实生产环境和业务影响。
- 证据优先：先事实和证据，再提出假设。
- 风险控制：说明风险、审批、回滚和验证。
- 自动化优先：减少重复手工操作，但不能绕过权限边界。
- 可追溯：保留来源、命令、结果、时间线和复盘记录。

## 2. 云计算运维定义

云计算运维是对云环境中的计算、网络、存储、数据库、应用、监控和安全资源进行部署、管理、监控、优化和故障处理的工程活动。

目标：

1. 可用性（Availability）
2. 可靠性（Reliability）
3. 性能（Performance）
4. 安全性（Security）
5. 自动化（Automation）
6. 成本优化（Cost Optimization）

常见云平台包括阿里云、华为云、腾讯云、AWS 和 Azure。常见服务包括 ECS/EC2/虚拟机、RDS/云数据库、OSS/对象存储、SLB/负载均衡、VPC、安全组和云监控。

## 3. 运维职责与标准流程

### 环境搭建

为 Java 项目准备 Linux、JDK、Tomcat、Nginx、MySQL、Redis、网络、配置和权限。

### 应用部署

```text
Source Code -> Build -> Package -> Upload -> Configure -> Start
-> Health Check -> Monitor
```

### 监控

- 服务器：CPU、内存、磁盘、网络、进程和服务状态。
- 应用：请求量、延迟、错误率、可用性和依赖调用。
- 数据库：连接数、慢查询、锁、事务、复制和资源使用率。

### 故障排查

```text
Incident -> Collect Evidence -> Determine Scope -> Analyze Timeline
-> Find Root Cause -> Apply Fix -> Verify Recovery -> Postmortem
```

不能把“重启优先、删除日志、随机修改配置”作为默认方案。必须先确认影响范围、最近变更、依赖关系和最有信息价值的低风险检查。

## 4. Linux 与网络

Linux 是云运维基础，重点包括文件系统、进程、服务、权限、用户、网络、日志、软件包和内核。

常用命令：

| 目标 | 命令 |
| --- | --- |
| 进程 | `ps`, `top`, `htop` |
| 服务 | `systemctl` |
| 日志 | `journalctl` |
| 网络 | `ss`, `netstat`, `ping`, `curl` |
| 磁盘 | `df`, `du`, `lsblk` |

网络排查顺序通常为 DNS、路由和网络连通性、防火墙、安全组、服务端口、应用协议和业务响应。必须区分 TCP refused、timeout、DNS failure、TLS failure 和 HTTP 错误。

重要协议包括 TCP、UDP、HTTP、HTTPS、DNS 和 SSH；基础模型包括 OSI 和 TCP/IP。

## 5. 数据库与中间件

### MySQL

MySQL 是关系型数据库。运维关注安装、备份、恢复、复制、性能、索引、事务、锁和连接池。常见问题包括 Too Many Connections、慢 SQL、死锁、磁盘满和复制延迟。排查证据包括 error log、slow log、processlist、连接数、锁等待和性能指标。

### Redis

Redis 是以内存为主的 NoSQL 数据库，常用于缓存和 Session。常见问题包括内存满、键过期策略、持久化失败和主从异常。

### Nginx

Nginx 提供 Web、反向代理和负载均衡。502、503、504 只表示请求链路的现象，不等于 Nginx 本身是根因。应检查 access.log、error.log、upstream、后端服务、端口、网络和最近发布。

### Tomcat

Tomcat 是 Java 应用服务器，重点排查内存泄漏、线程池耗尽、GC 压力、连接池和应用日志。

## 6. 高可用、监控与日志

- Keepalived 使用 VRRP 实现主备高可用和自动切换。
- LVS 提供高性能负载均衡。
- HAProxy 提供 TCP/HTTP 负载均衡。
- Zabbix 用于基础设施监控、指标采集和告警。
- Prometheus 使用 Metric、Label、Exporter 和 PromQL 支持云原生监控。
- Grafana 用于 Dashboard 可视化。
- Alertmanager 负责告警路由，可通知邮件、钉钉或微信。
- ELK（Elasticsearch、Logstash、Kibana）用于日志采集、存储、搜索和分析。

监控、日志、链路、变更时间线和业务影响应联合分析，不能只看单个指标。

## 7. 自动化、容器与 Kubernetes

Shell 用于备份、部署、巡检和健康检查；Python 用于 API、自动化、数据处理和 AI 集成；Ansible 用于批量安装、配置和受控命令执行。

Docker 的链路是：

```text
Image -> Container -> Application
```

排查容器时区分 Image、Container、Network、Volume、Resource Limit、进程和应用健康。容器处于 Up 不代表业务 Ready。

Kubernetes 用于自动部署、扩缩容、自愈和服务发现。核心对象：Pod、Deployment、Service、Ingress、Namespace、ConfigMap、Secret 和 Node。常见故障：Pod Pending、CrashLoopBackOff、ImagePullBackOff、Service unavailable。自动恢复不能替代健康检查、资源限制、依赖分析、发布关联和恢复验证。

## 8. DevOps 与 CI/CD

CI/CD 流程：

```text
Code -> Build -> Test -> Deploy -> Monitor
```

常见工具包括 Git、Jenkins、GitLab CI、Docker 和 Kubernetes。自动化变更必须有权限边界、变更记录、审批、失败处理、回滚和发布后验证。

## 9. AIOps 与知识关联

AIOps 将人工智能、自动化、知识库和智能诊断结合，用于日志分析、故障预测、自动巡检、知识搜索和智能助手。

每个知识项至少应能关联：

```text
Knowledge
  <-> Question
  <-> Runbook
  <-> Incident
  <-> Command
```

知识项建议字段：`id`、`title`、`category`、`content`、`tags`、`difficulty`、`relatedQuestions`、`relatedRunbooks`、`relatedIncidents`、`createdAt`、`updatedAt`。

示例：`NGINX-502` 关联 Nginx 技术、`curl` 命令、Nginx 502 Runbook、Upstream Connection Failed Incident 和 `OPS-NGINX-502-001` 题目。

## 10. 题库、Runbook 与 Incident 生成规则

知识可以生成：

- 基础题：概念和职责。
- 命令题：如何查看端口、日志、进程和磁盘。
- 场景题：Nginx 返回 502 时首先检查什么。
- Incident 题：生产 API 不可用时如何收集证据和确定范围。

重要知识应生成 Runbook：

```text
Title
Purpose
Symptoms
Impact
Diagnosis Steps
Commands
Solution
Verification
Rollback
Postmortem
```

Incident 模拟必须让用户逐步收集证据、分析时间线、判断风险、选择动作和验证恢复，不能只展示最终答案。

错题系统应记录题目、用户答案、错误原因、知识缺口和错误模式。例如把“立即重启 Nginx”归类为“用症状处理替代根因定位”，并推荐学习 upstream 排查。

## 11. 安全规则

Never recommend / 禁止默认推荐：

- 直接关闭防火墙或 SELinux。
- 删除日志来释放磁盘。
- 删除数据库或数据文件。
- 对所有目录执行 `chmod 777`。
- 无证据地重启全部服务。
- 未备份、未审批、无回滚地修改生产配置。

任何高风险建议必须同时说明风险、备份、审批、验证和回滚。AI 生成的总结不能覆盖 Raw Evidence，也不能自动修改生产服务器。

## 12. SmartOpsAgent 使用边界

知识库优先用于本地检索、解释、训练、Runbook 草拟和 Incident 模拟。Agent、OCR、视觉哨兵和运行库可以通过明确的关系引用本知识源，但本知识包本身不执行命令、不连接生产服务器、不自动发布 AI 生成题目。

最终闭环：

```text
Knowledge -> AI Understanding -> Question Training -> Fault Diagnosis
-> Runbook -> Approved Operation -> Experience Memory -> Knowledge Improvement
```
