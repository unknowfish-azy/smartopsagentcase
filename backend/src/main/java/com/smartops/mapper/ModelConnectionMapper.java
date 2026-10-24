package com.smartops.mapper;

import com.smartops.entity.ModelConnection;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ModelConnectionMapper {

    int insert(ModelConnection connection);

    int update(ModelConnection connection);

    int deleteById(
            @Param("id") Long id,
            @Param("userId") Long userId
    );

    ModelConnection findById(
            @Param("id") Long id,
            @Param("userId") Long userId
    );

    List<ModelConnection> findByUserId(
            @Param("userId") Long userId
    );
}