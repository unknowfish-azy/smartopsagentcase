# Jenkins

Jenkins用于构建、测试和部署自动化。

推荐流水线：

```text
Checkout
  ↓
Backend Test
  ↓
AI Service Test
  ↓
Frontend Build
  ↓
Docker Build
  ↓
Security/Config Check
  ↓
Deploy
  ↓
Health Check