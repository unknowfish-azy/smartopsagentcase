# 安全整改 · DNS rebinding 注入实验执行记录（2026-11-06 晚）

> 对应整改项：SEC-06 残余（连接期 IP pin）。此前状态：`NOT_RUN`（仅单测证明 fail-closed）。

## 一、结论

| 项 | 结果 |
| --- | --- |
| 本机受控 DNS rebinding 注入 | PASS（`PinnedDnsRebindingTest` 1/1，1.34s） |
| 未 pin 客户端（攻击可达性对照） | 命中内网蜜罐，HTTP 200 |
| 生产 pin 路径（`PinnedDns` 作 DnsResolver） | 只用已校验公网地址建连，蜜罐计数不变 |
| pin 缺失（fail-closed 对照） | `UnknownHostException` 拒绝建连，不回落 DNS |
| 后端全量回归 | 769 项 / 0 失败 / 0 错误 / 1 skipped |

## 二、实验边界（如实）

- **真实的部分**：DNS 应答走真实 UDP 协议；`public → 127.0.0.1` 的应答切换发生在同一受控 DNS 进程内；建连走真实 TCP；蜜罐与 pin 相关代码均为生产实现（`PinnedDns`）。
- **未做的部分**：未修改系统 DNS（无管理员权限），未使用公网出口与公网权威 DNS，「公网环境下的真实 rebinding」仍为 `NOT_RUN`，需部署环境复验。
- 因此本实验证明「校验后 DNS 改答不能把连接带入内网」的机制成立，不等价于公网攻击链路的完整复现。

## 三、拓扑与步骤

```text
受控 DNS (127.0.0.1:随机UDP端口)
  rebind.sec.test  A=93.184.216.34  (校验阶段，公网)
  切换后            A=127.0.0.1     (连接阶段，内网)

蜜罐 TCP (127.0.0.1:随机端口) —— 记录连接次数
```

1. `OutboundUrlPolicy.isPublicAddress(93.184.216.34)` 为真（与出站校验同一判定）；
2. `PinnedDns.pin("rebind.sec.test", [93.184.216.34])` 模拟校验通过后的 pin；
3. 受控 DNS 切答 `127.0.0.1`（rebinding 时刻）；
4. 对照 1：未 pin 客户端（解析器直接向受控 DNS 发真实 UDP 查询）→ 请求蜜罐，HTTP 200，命中数 1；
5. 对照 2：生产接线客户端（`PinnedDns::resolve`）→ TCP 指向 `93.184.216.34`，蜜罐命中数仍为 1；
6. 对照 3：`PinnedDns.clear` 后再请求 → `UnknownHostException`（fail-closed），蜜罐命中数仍为 1。

## 四、环境与命令

| 项 | 值 |
| --- | --- |
| JDK | `C:\Users\33908\scoop\apps\openjdk17\current`（17） |
| Maven | `mvn -s .mvn/smartops-settings.xml`，工作目录 `backend` |
| 依赖 | Apache HttpClient 5.2.3（`DnsResolver`、`ConnectionConfig`） |
| 端口 | 全随机端口（UDP DNS、TCP 蜜罐），不与平台 8080/8002/6379 冲突 |

```powershell
$env:JAVA_HOME='C:\Users\33908\scoop\apps\openjdk17\current'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
mvn -s .mvn/smartops-settings.xml test -Dtest=PinnedDnsRebindingTest -DfailIfNoTests=false
mvn -s .mvn/smartops-settings.xml test
```

## 五、变更文件

| 文件 | 说明 |
| --- | --- |
| `backend/src/test/java/com/smartops/security/PinnedDnsRebindingTest.java` | 新增：受控 UDP DNS + 蜜罐 + 三组对照（未改生产代码） |

测试内的 HttpClient 接线（`DnsResolver`、禁代理/重定向/重试、短超时）与 `ModelProviderClient` 的生产接线保持一致，仅解析器不同，用于构造「未 pin 攻击可达」的对照。

## 六、后续（仍需授权 / 部署环境）

- 公网出口 + 可控权威 DNS 下的真实 rebinding 复验；
- nginx `/ai-api` 内网 CIDR 隔离与 `docker compose` 部署面验证；
- TM-25 爬取并发上限、TM-23 slow-drip 未验证。
