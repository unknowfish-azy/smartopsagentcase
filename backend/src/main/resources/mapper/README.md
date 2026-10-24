# Mapper XML目录说明

当前项目 V0.1 使用 Spring Data JPA。

因此当前目录暂不存放 MyBatis Mapper XML 文件。

当前数据库访问链路：

Controller
↓
Service
↓
Repository
↓
Spring Data JPA
↓
MySQL

当前 Repository 位于：

com.smartops.mapper

后续如果项目正式切换到 MyBatis / MyBatis-Plus，
再在本目录增加对应的 XML Mapper 文件。

例如：

ServerMapper.xml
ServerMetricMapper.xml

切换前不得同时混用两套持久化方案。