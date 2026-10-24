# Host Networking & Infrastructure Operations Knowledge

## 来源与边界

来源为用户于 2026-09-24 粘贴的课程整理摘要。未找到可确认属于本课程的原附件，因此不声明逐字保留或核验课程原文，不编造文件名、页码或作者。结构化节点的 `source_course` 仅指摘要归于课程的内容；`expert_enhancement`、`production_rule` 为新增工程规则。未来原附件可用时，应核对后补充来源版本与定位信息。

结构化数据：`knowledge/linux/networkEnvironmentKnowledge.js`。通过现有 Knowledge Center 检索，service 为 `network-environment`。节点、Incident、Runbook、Question、Wrong Answer 和规则均可独立检索；Incident 为参考场景，不是真实发生的事故。

## 课程摘要保留

- 接口：eth0/eth1、eno1、enp2s0、ens33，en/wl/ww 和 o/s/p 命名元素。
- NetworkManager：nmcli、nmtui、nm-connection-editor；device 与 connection。
- CentOS 7：ifcfg 的 ONBOOT、BOOTPROTO、IPADDR、NETMASK、GATEWAY、DNS1；CentOS 9 的 NetworkManager 连接配置。
- IP、prefix、gateway、DNS、route、neighbor；ip a、ip link、ip route、ip neigh、ping、resolv.conf。
- hostname、FQDN、hostnamectl、/etc/hostname。
- ss -tnl/-tna/-tnlp、netstat、LISTEN、ESTABLISHED 和进程端口映射。
- 最小化安装、YUM 仓库、lrzsz/sysstat/curl/wget/net-tools/bash-completion/vim。
- Firewalld、SELinux、chronyd、timedatectl、关机、快照、模板和克隆。

课程网络示例（仅参考，禁止直接作为生产值）：

```bash
nmcli connection modify ens33 ipv4.addresses 192.168.126.180/24
nmcli connection modify ens33 ipv4.gateway 192.168.126.2
nmcli connection modify ens33 ipv4.method manual
nmcli connection modify ens33 ipv4.dns "114.114.114.114,8.8.8.8"
nmcli connection up ens33
```

`ens33` 必须确实是连接 profile 名才适用于上述命令，不能从接口名推定；DNS 需符合组织网络与隐私策略。课程中的 kill -9、stop/disable firewalld、setenforce 0、修改 /etc/selinux/config 与直接修改网络保留为 **lab/demo**，不是默认生产修复步骤。

## 工程增强

主链：Host → Identity → Network → Route → DNS → Socket → Service → Firewall → SELinux → Time → Baseline → Incident → Verification → Memory。

HostIdentity 包括 hostname/FQDN、machine-id、接口名/MAC、连接 UUID、IPv4/prefix/gateway、DNS/routes、时区、时间同步与安全状态。IP 不等于主机身份，hostname 不等于 DNS，连接 UUID 不等于 MAC。

网络阶梯是诊断顺序，不是 OSI 层号。先按证据选择相关分支，不要求每次机械执行全部检查。查询命令不改变配置，但探测会产生流量、仓库查询可能刷新缓存、输出可能包含敏感身份信息。

变更链：发现目标 → 快照和受保护备份 → 验证地址与冲突 → 控制通道依赖评估 → 预览 → 审批 → 独立操作层应用 → 第二个 SSH 会话和应用验收 → 必要时回滚。当前 Knowledge/Companion 不执行此链中的远程命令。

网络 profile 修改为 MEDIUM；影响当前 SSH 路径时至少 HIGH，必须有控制台或独立管理链路。备份文件不是可执行回滚机制，断连后不能假设仍可从同一 SSH 修复。

## 模板与基线

Runbook `RB-LINUX-BOOTSTRAP-001` 覆盖 identity、network、repository、tools、time、security、access、baseline、validation、snapshot。

ServerReadiness 仅在 identity/network/dns/time_sync/ssh/storage/package_manager/security_state 全部有新鲜的合规证据时 READY；未知检查不算 PASS。已验收服务器退化为 DEGRADED；初始化部分检查失败或缺失为 PARTIALLY_READY。

模板克隆后先隔离核验身份。machine-id、SSH host identity 和平台标识应由镜像制备流程处理，不提供在运行生产机上直接删除标识的快捷命令。IP/hostname 的计划内差异不是漂移；与每台主机 desired state 比较才有意义。

Chrony 统一引用 `linux.time.chrony`。此次库内未发现已有专用节点，因此建立一个标准节点；chronyd active、enable 和时间同步是三种不同事实，验收需 tracking/sources。

## Agent 规则

视觉错误 ERR_CONNECTION_REFUSED、ERR_CONNECTION_TIMED_OUT、DNS_PROBE_FINISHED_NXDOMAIN、502/503/504 仅为观察。第二证据须独立且与目标/时间匹配，不能把重复 OCR 当 CORROBORATED。调用 ss/systemctl/curl 在此阶段是建议，不是自动执行。

服务 active ≠ socket 监听 ≠ 网络可达 ≠ HTTP 正确 ≠ 业务成功。SELinux 归因需对应 AVC/标签/策略证据；本机成功而远端失败不自动证明 SELinux。高风险实验动作永不作为默认生产建议。

训练集 `SmartOps-Dataset/Linux/network_environment_initialization.jsonl` 为 DRAFT，不代表模型已经训练或知识已获得人工发布批准。
