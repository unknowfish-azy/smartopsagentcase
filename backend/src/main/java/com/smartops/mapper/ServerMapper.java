package com.smartops.mapper;

import com.smartops.entity.ServerEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ServerMapper {

    /**
     * 查询全部服务器
     */
    List<ServerEntity> selectAll();

    /**
     * 根据ID查询服务器
     */
    ServerEntity selectById(Long id);

    /**
     * 根据服务器名称查询
     */
    ServerEntity selectByName(String name);

    /**
     * 判断服务器名称是否存在
     */
    int countByName(String name);

    /**
     * 新增服务器
     */
    int insert(ServerEntity server);

    /**
     * 修改服务器
     */
    int update(ServerEntity server);

    /**
     * 删除服务器
     */
    int deleteById(Long id);

    /**
     * 更新服务器状态
     */
    int updateStatus(@Param("id") Long id, @Param("status") String status);
}