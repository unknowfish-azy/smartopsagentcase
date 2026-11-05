package com.smartops.mapper;

import com.smartops.entity.ServerEntity;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@MybatisTest(properties = "spring.flyway.enabled=false")
class ServerMapperTest {

    @Autowired
    private ServerMapper serverMapper;

    @Test
    void selectAllShouldReturnData() {

        List<ServerEntity> list =
                serverMapper.selectAll();

        assertNotNull(list);
        assertFalse(list.isEmpty());
    }

    @Test
    void selectByIdShouldReturnServer() {

        ServerEntity server =
                serverMapper.selectById(1L);

        assertNotNull(server);
        assertEquals(
                "Test-Server-01",
                server.getName()
        );
    }

    @Test
    void countByNameShouldReturnOne() {

        int count =
                serverMapper.countByName(
                        "Test-Server-01"
                );

        assertEquals(1, count);
    }
}