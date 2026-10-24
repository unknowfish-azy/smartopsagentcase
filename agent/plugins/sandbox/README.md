# Sandbox Plugin

Sandbox Plugin 是 SmartOps Harness 的安全执行隔离层。

它负责限制 Agent、Plugin、Tool 在执行过程中可以访问的：

```text
文件系统
进程
Shell
网络
环境变量
临时目录
资源