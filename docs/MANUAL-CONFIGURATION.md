# SmartOpsAgent 手动配置说明

> 本文基于 2026-09-18 源码扫描生成。只列出当前代码、脚本或测试实际读取的变量；不会提供真实密码、API Key 或 Token。

## 一、必须手动配置

生产环境启动前必须设置：

| 变量 | 必须性 | 用途 | 位置 | 示例格式（非真实值） | 敏感 | 生产要求 |
|---|---|---|---|---|---|---|
| `MYSQL_PASSWORD` | 必须 | Backend 连接 MySQL | `.env` / 环境变量 | `<mysql-password>` | 是 | 不得为空或使用默认密码 |
| `SMARTOPS_API_KEY_ENCRYPTION_KEY` | 必须 | AES-256-GCM 加密模型 API Key | `.env` / 环境变量 | 32 字节随机值的 Base64 | 是 | 每个环境独立，安全备份，不得轮换后遗失旧密文解密能力 |
| `SMARTOPS_INTERNAL_TOKEN` | 必须 | AI Service 调用 Backend Internal API | `.env` / 环境变量 | 高熵随机字符串 | 是 | Backend 与内部调用方一致，不得传给浏览器 |
| `LLM_PROVIDER` | 必须 | 选择 `mock`、`ollama` 或后续兼容 Provider | `.env` | `mock` | 否 | 生产不得把 Mock 标为真实模型 |

## 二、可选配置

| 变量 | 条件 | 用途 | 示例格式 | 敏感 |
|---|---|---|---|---|
| `MYSQL_URL` | 非默认 MySQL 地址时 | JDBC URL | `jdbc:mysql://db:3306/smartops?...` | 否 |
| `MYSQL_USERNAME` | 非默认用户时 | MySQL 用户名 | `smartops_app` | 否 |
| `REDIS_PASSWORD` | Redis 开启认证时 | Redis 密码 | `<redis-password>` | 是 |
| `LLM_API_KEY` | 远程模型需要鉴权时 | 模型服务密钥 | `<provider-api-key>` | 是 |
| `LLM_BASE_URL` | 使用 Local/Remote 模型时 | 模型服务地址 | `https://provider.example/v1` | 否 |
| `LLM_MODEL` | 非 Mock 模型时 | 模型名称 | `<provider-model-name>` | 否 |
| `OLLAMA_BASE_URL` | 使用 Ollama 时 | Ollama 地址 | `http://localhost:11434` | 否 |
| `KNOWLEDGE_SERVICE_URL` | AI Service 使用 RAG 时 | Knowledge 地址 | `http://localhost:8002` | 否 |
| `VITE_API_BASE_URL` | 前端不与 Backend 同源时 | Backend 地址 | `http://localhost:8080` | 否 |
| `SMARTOPS_INTERNAL_BYPASS` | 仅显式本地开发 | 跳过 Internal Token Filter | `false` | 否 |

当前代码未读取 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY` 或 `QWEN_API_KEY`。不要仅为了文档完整而添加它们；OpenAI-compatible 密钥当前统一使用 `LLM_API_KEY`，Model Connection 页面则由用户录入并由 Backend 加密保存。

## 三、开发环境配置

1. 将 `.env.example` 复制为 `.env`。
2. 配置本机 MySQL；Redis 无认证时 `REDIS_PASSWORD` 可留空。
3. `LLM_PROVIDER=mock` 可运行无真实模型的开发流程，但页面和报告必须明确标记 Mock。
4. Internal API 推荐仍配置 `SMARTOPS_INTERNAL_TOKEN`。只有显式本机调试可设置 `SMARTOPS_INTERNAL_BYPASS=true`。
5. `application-local.yml` 和 `application-dev.yml` 含开发默认值，绝不能当作生产配置。

## 四、生产环境配置

- 使用 `prod` profile。
- 密码、AES Key、Internal Token 和模型 API Key 必须由秘密管理系统或进程环境注入。
- 保持 `SMARTOPS_INTERNAL_BYPASS=false`。
- 不得把 `.env` 打包进镜像或提交版本库。
- `SMARTOPS_INTERNAL_TOKEN` 只允许在受控内部网络的服务间传输。

## 五、数据库密码

`MYSQL_USERNAME` 与 `MYSQL_PASSWORD` 供 Spring Backend 使用。测试 profile 使用内存 H2，不应复用生产凭据。初始化结构先执行 `scripts/common/init-db.sql`，Inspector 增量表再执行 `scripts/common/migrations/V002__inspector.sql`。

## 六、Redis 密码

实际使用变量为 `REDIS_HOST`、`REDIS_PORT`、`REDIS_DATABASE`、`REDIS_PASSWORD`。Redis 未启用认证时密码可留空；生产环境应限制网络访问并按部署策略启用认证。

## 七、模型 API Key

- 全局 AI Service 使用 `LLM_API_KEY`。
- Model Settings 页面录入的 Key 由 Backend 以 AES-GCM 密文存储，只向普通页面返回掩码。
- `/api/model-connections/{id}/runtime` 不返回明文或密文 Key。
- 当前直接凭据下发调用已禁用；启用真实 Provider 前应实现服务端凭据代理。

## 八、AES-GCM 加密密钥

`SMARTOPS_API_KEY_ENCRYPTION_KEY` 必须是 Base64 编码的 32 字节随机数据。请在安全终端或秘密管理系统中生成，不要把命令输出粘贴到源码、文档或聊天记录。

## 九、内部服务 Token

`SMARTOPS_INTERNAL_TOKEN` 由 Backend 的 Internal Token Filter 使用，请求 Header 为 `X-SmartOps-Internal-Token`。缺失 Token 返回 401，错误 Token 返回 403，Backend 未配置 Token 返回 503。

## 十、GitHub / HTTP Provider Token

当前运行代码未发现 GitHub Token 环境变量。不要预先配置或提交。未来新增 Provider 时应使用独立环境变量和最小权限 Token，并同步更新本文。

## 十一、第三方模型配置

当前 AI Service 配置支持 `mock` 和 `ollama` 分支；Model Connection 数据模型支持 OpenAI-compatible Base URL、Provider、Model Name、Timeout 和加密 API Key。Ollama HTTP 调用仍是模拟占位，不能当作真实连接成功。

## 十二、训练模型路径

新增训练资产根目录为 `data/training/`，保留原 `date/` 不变。当前没有读取训练模型路径的环境变量，也没有已训练模型；如后续新增 `TRAINING_OUTPUT_DIR` 等变量，必须先在代码中实现，再加入本文。

## 十三、GPU / CUDA 配置

本 Phase 只提供标准库 Dataset Validator 和 Evaluation `NOT RUN` 报告，不依赖 GPU、CUDA、PyTorch、Transformers、PEFT 或 TRL。当前未定义 GPU 环境变量。真实训练前需人工确认驱动、CUDA、显存和框架版本。

## 十三点一、训练路径变量状态

当前源码尚未读取 `MODEL_PATH`、`TRAINING_DATA_PATH`、`OUTPUT_DIR`、`CUDA_VISIBLE_DEVICES`、`HF_TOKEN` 或 `TRANSFORMERS_CACHE`。因此这些变量不应被添加到 `.env` 作为“已支持配置”。真实训练实现读取它们后，再同步加入本节；其中 `HF_TOKEN` 必须始终由用户手动配置，不得写入 Dataset、日志或 Registry。

## 十四、如何启动

```powershell
cd D:\SmartOpsAgent
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File scripts/windows/check-config.ps1
```

然后按照 `scripts/windows/start-dev.ps1` 的现有流程启动。注意核对 AI Service 实际监听端口与 `.env.example` 中测试 URL；端口不一致会导致 E2E skip 或失败。

## 十五、如何验证

```powershell
python -m pytest -q
cd backend
mvn test
cd ..\ai-service
python -m pytest app/tests -q
cd ..\knowledge
python -m pytest -q
cd ..\frontend
npm run build
```

配置检查脚本只输出 `OK`、`MISSING` 或 `OPTIONAL`，绝不输出秘密值。

## 十六、绝对不能提交 Git

- `.env`、`.env.*`（`.env.example` 除外）
- 数据库密码、Redis 密码
- `LLM_API_KEY` 与用户 Model Connection API Key
- `SMARTOPS_API_KEY_ENCRYPTION_KEY`
- `SMARTOPS_INTERNAL_TOKEN`
- 任何 Ciphertext 导出、生产日志、数据库备份、私钥或证书私钥

## 十七、常见错误

- Runtime API 返回 401：缺少 Internal Token Header。
- Runtime API 返回 403：Token 与 Backend 配置不一致。
- Runtime API 返回 503：Backend 没有配置 `SMARTOPS_INTERNAL_TOKEN`。
- Backend 无法解密旧 Key：AES Key 被更换或不是有效的 32 字节 Base64。
- 前端 `spawn EPERM`：受限环境阻止 esbuild 子进程；应在受信任环境运行同一构建命令复核。
- MySQL/Redis 测试 skip：服务未启动或 Python 驱动未安装，不代表测试通过。

## 十八、配置完成检查表

- [ ] `.env` 已创建且未纳入版本控制
- [ ] MySQL 账号密码已配置并验证
- [ ] Redis 地址、认证策略已确认
- [ ] AES-256-GCM Key 已安全生成和备份
- [ ] Internal Token 已在 Backend 与内部调用方一致配置
- [ ] Production Bypass 为 `false`
- [ ] LLM Provider、Base URL、Model、Key 已按实际模式配置
- [ ] Knowledge Service URL 已验证
- [ ] Inspector migration 已执行
- [ ] 配置检查未输出任何秘密
- [ ] 测试和构建结果按真实状态记录
