package com.smartops.service;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ServerMapper;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.impl.ServerServiceImpl;
import com.smartops.vo.ServerVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ServerServiceTest {

    @Mock
    private ServerMapper serverMapper;

    @Mock
    private UserAccountService accounts;

    @Mock
    private SecurityAuditService audit;

    private ServerService serverService;

    @BeforeEach
    void setUp() {
        serverService = new ServerServiceImpl(serverMapper, accounts, audit);
    }

    @Test
    void createServerShouldSuccessAndBindOwner() {

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
                serverService.create(user(7), request);

        assertNotNull(result);
        assertEquals(1L, result.getId());
        assertEquals(
                "Server-01",
                result.getName()
        );

        ArgumentCaptor<ServerEntity> captor = ArgumentCaptor.forClass(ServerEntity.class);
        verify(serverMapper).insert(captor.capture());
        assertEquals(7L, captor.getValue().getOwnerId());
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
                () -> serverService.create(user(7), request)
        );

        verify(serverMapper, never())
                .insert(any(ServerEntity.class));
    }

    /** SEC-08：非属主读别人的资产统一 404，且不查询治理能力（看不出存在）。 */
    @Test
    void otherUsersServerIsNotReadable() {
        when(serverMapper.selectById(2L)).thenReturn(server(2L, 99L));
        assertThrows(BusinessException.class, () -> serverService.getById(user(7), 2L));
        assertThrows(BusinessException.class, () -> serverService.update(user(7), 2L, null));
        verify(serverMapper, never()).update(any(ServerEntity.class));
        verify(serverMapper, never()).deleteById(any());
    }

    /** SEC-08：历史无属主行仅平台审计管理员可读，读取留审计。 */
    @Test
    void platformAuditorCanReadLegacyServerWithAudit() {
        when(serverMapper.selectById(2L)).thenReturn(server(2L, null));
        when(accounts.hasPlatformCapability(user(9), "admin.audit")).thenReturn(true);

        assertNotNull(serverService.getById(user(9), 2L));

        verify(audit).record(eq(user(9)), eq("PLATFORM_INFRA_VIEW"), eq("server:2"), eq("SUCCESS"), isNull());
    }

    /** SEC-08：普通用户列表按属主过滤，不走全局查询。 */
    @Test
    void listIsOwnerScopedForNormalUser() {
        when(serverMapper.selectByOwner(7L)).thenReturn(List.of(server(1L, 7L)));

        assertEquals(1, serverService.list(user(7)).size());

        verify(serverMapper, never()).selectAll();
        verify(audit, never()).record(any(), any(), any(), any(), any());
    }

    /** SEC-08：平台审计管理员列表走全局查询并留审计。 */
    @Test
    void globalViewerListsAllServersWithAudit() {
        when(accounts.hasPlatformCapability(user(9), "admin.audit")).thenReturn(true);
        when(serverMapper.selectAll()).thenReturn(List.of(server(1L, 7L), server(2L, null)));

        assertEquals(2, serverService.list(user(9)).size());

        verify(serverMapper, never()).selectByOwner(anyLong());
        verify(audit).record(eq(user(9)), eq("PLATFORM_INFRA_VIEW"), eq("server:list"), eq("SUCCESS"), isNull());
    }

    private static ServerEntity server(long id, Long ownerId) {
        ServerEntity entity = new ServerEntity();
        entity.setId(id);
        entity.setOwnerId(ownerId);
        entity.setName("s-" + id);
        return entity;
    }

    private static SessionUser user(long id) {
        return new SessionUser(id, "u" + id, "user", "user", false, 0);
    }
}
