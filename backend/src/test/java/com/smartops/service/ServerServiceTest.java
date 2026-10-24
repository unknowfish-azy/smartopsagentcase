package com.smartops.service;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.mapper.ServerMapper;
import com.smartops.service.impl.ServerServiceImpl;
import com.smartops.vo.ServerVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ServerServiceTest {

    @Mock
    private ServerMapper serverMapper;

    private ServerService serverService;

    @BeforeEach
    void setUp() {
        serverService =
                new ServerServiceImpl(serverMapper);
    }

    @Test
    void createServerShouldSuccess() {

        ServerCreateRequest request =
                new ServerCreateRequest();

        request.setName("Server-01");
        request.setHost("127.0.0.1");
        request.setPort(22);
        request.setOs("Ubuntu 24.04");

        when(serverMapper.countByName("Server-01"))
                .thenReturn(0);

        doAnswer(invocation -> {

            ServerEntity entity =
                    invocation.getArgument(0);

            entity.setId(1L);

            return 1;

        }).when(serverMapper)
                .insert(any(ServerEntity.class));

        ServerVO result =
                serverService.create(request);

        assertNotNull(result);
        assertEquals(1L, result.getId());
        assertEquals(
                "Server-01",
                result.getName()
        );

        verify(serverMapper)
                .countByName("Server-01");

        verify(serverMapper)
                .insert(any(ServerEntity.class));
    }

    @Test
    void duplicateServerNameShouldFail() {

        ServerCreateRequest request =
                new ServerCreateRequest();

        request.setName("Server-01");
        request.setHost("127.0.0.1");
        request.setPort(22);

        when(serverMapper.countByName("Server-01"))
                .thenReturn(1);

        assertThrows(
                RuntimeException.class,
                () -> serverService.create(request)
        );

        verify(serverMapper, never())
                .insert(any(ServerEntity.class));
    }
}