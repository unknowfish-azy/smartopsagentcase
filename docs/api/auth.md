# Authentication API

## 1. 接口定位

Authentication 模块负责 SmartOpsAgent 的用户身份认证、当前用户信息获取以及权限基础控制。

认证模块主要解决：

```text
用户身份确认
    ↓
获取访问令牌
    ↓
访问受保护 API
    ↓
权限校验
    ↓
Agent 操作授权