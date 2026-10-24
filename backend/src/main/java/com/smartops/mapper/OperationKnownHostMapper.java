package com.smartops.mapper;

import com.smartops.entity.OperationKnownHost;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface OperationKnownHostMapper {
    OperationKnownHost findBySessionHostAndPort(@Param("sessionId") Long sessionId,
                                                @Param("host") String host,
                                                @Param("port") int port);

    int insert(OperationKnownHost knownHost);

    int update(OperationKnownHost knownHost);
}
