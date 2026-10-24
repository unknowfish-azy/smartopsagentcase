# 智维 Mini 默认本地助手

用户已确认：本地小模型+项目知识检索；无外部模型即可对话；以后自行选择已接入模型；不自动替换、不偷偷降级；本批仅建议/只读检索，无命令执行。保留所有现有账号、连接、历史。

## 架构与边界

前端对话页与桌宠继续共用aiChat store，改走Java认证后的统一assistant API。Java负责当前用户模型选择、数据库偏好与外部连接调用；内置engine直接调用回环地址Ollama原生API。旧AI服务示例接口不作为Mini生成引擎，不将mock回复冒充真实模型。API不接受baseUrl、工具调用或自定义system角色。

- runtime/model放Git忽略的.runtime/mini，官方运行包校验SHA256；只监听127.0.0.1:11434，OLLAMA_NO_CLOUD=1，不调用收费API。
- 默认模型qwen3:1.7b；实际性能以本机验证为准。模型缺失/运行时离线明确返回503；繁忙429；不生成模拟成功回复。
- 读取白名单knowledge/linux/**/*.md、knowledge/cloud_ops/*.md、knowledge/assistant/*.md、knowledge/smartopsagent_brain.md；不扫描.env、.runtime、用户上传或其他账号数据。路径必须仍在知识根目录内，不跟随外部符号链接。索引有文件/大小/片段上限。
- 轻量中文/英文词项检索，最多3段参考知识；模型消息和历史有大小上限，模型上下文8192、输出最多512token、think=false。只返回服务端检索的参考来源，不信任模型生成路径，知识内容视为引用数据而非指令。
- 单个本地生成并发；HTTP超时120秒，前端请求150秒。状态探测2秒、短缓存；外部连接仅标记configured，不进行实际付费探测。
- 数据库新增assistant_preference(user_id PK,provider_key VARCHAR64,updated_at)，默认mini；每个账号独立。新增V004迁移，不改V001-003。

## 固定接口契约

全部接口需有效登录，强制改密阶段禁止；变更需CSRF。响应包为{code,message,data}。

- GET /api/assistant/options -> {selectedKey,options:[{key,name,kind,model,enabled,available,status,detail,timeoutSeconds}]}。
  mini项key='mini',name='智维 Mini',kind='builtin',status='ready'|'offline'|'model_missing'，enabled=true，available表示实测运行时可用。
  外部项key='connection:'+id,kind='connection',status='configured'|'disabled'，available只代表已启用，detail说明未实时验证；不返回密钥、baseUrl、其他用户连接。
  未保存偏好默认mini，即使已有外部连接也不自动选首个。保存的连接被删/停用时保留选择并展示unavailable，不静默改用其他模型。
- PUT /api/assistant/preference {providerKey} -> {selectedKey}；仅mini或本人启用的连接可以保存。
- POST /api/assistant/chat {providerKey?,message,history:[{role:'user'|'assistant',content}]} -> {content,providerKey,providerName,model,citations:[{id,title,source,snippet}],usage,readOnly:true}。
  message非空<=2000字符，history<=12条且每条<=4000、总历史<=16000字符。providerKey省略时使用数据库默认。发送到外部的上下文由服务端拼接，不自动跨会话混入内容。
  外部调用失败仍返回错误，前端提供显式“改用智维 Mini”按钮；点击后保存偏好但不自动重发敏感问题，用户再次发送/重试。

## Core Worker接口（主线程依赖）

`com.smartops.assistant.MiniAssistantEngine` @Service:
- `RuntimeStatus status()`；record RuntimeStatus(boolean available,String status,String detail,String model)。
- `Reply generate(String message,List<Map<String,String>> history)`；record Reply(String content,String model,List<Evidence> citations,Map<String,Object> usage)。
- record Evidence(String id,String title,String source,String snippet)。

worker仅backend/src/main/java/com/smartops/assistant/**及对应test/**和knowledge/assistant/**；不要改pom/config/schema/controller。属性@Value默认smartops.mini.base-url=http://127.0.0.1:11434，model=qwen3:1.7b，knowledge-root=../knowledge；公共配置由主线程处理。

## 工作与验收

- [ ] Core worker先测试后实现真实Ollama引擎、受限知识检索、来源、异常与忙碌保护。
- [ ] Frontend worker只改frontend/**：统一模型选择、偏好恢复、两入口共用、来源显示、显式fallback、历史兼容及主题/手机测试。
- [ ] 主线程先测试后实现assistant API、账号隔离偏好、外部调用路由、追加迁移与本地启停脚本；不清理当前脏工作区、不分支、不提交。
- [ ] 全量后端/前端测试构建、独立安全复核、数据库备份迁移、部署；真实Mini中文对话/知识检索/追问、现有连接保留，浏览器截图与回归。

本机内存约15.7GiB、D盘剩余约40GiB。下载已获工具授权，后台进行中。不能将下载成功等同于推理可用；必须实际生成并报告性能/限制。测试外部连接仅mock，不消耗用户模型额度。
