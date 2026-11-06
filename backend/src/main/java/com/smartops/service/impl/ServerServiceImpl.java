package com.smartops.service.impl;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ServerMapper;
import com.smartops.module.server.ServerStatus;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.UserAccountService;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

@Service
@RequiredArgsConstructor
@Transactional
public class ServerServiceImpl implements ServerService {

    /** 平台审计管理员能力：可读全局资产（含历史无属主行），读取留审计。 */
    private static final String GLOBAL_VIEW_CAPABILITY = "admin.audit";

    private final ServerMapper serverMapper;
    private final UserAccountService accounts;
    private final SecurityAuditService audit;

    @Override
    public ServerVO create(SessionUser actor, ServerCreateRequest request) {

        if (serverMapper.countByName(request.getName()) > 0) {
            throw new BusinessException("服务器名称已经存在");
        }

        LocalDateTime now = LocalDateTime.now();

        // SEC-08：创建即归属创建者，避免"任意登录用户可读全部资产"。
        ServerEntity entity = ServerEntity.builder()
                .ownerId(actor.id())
                .name(request.getName())
                .host(request.getHost())
                .port(request.getPort())
                .os(request.getOs())
                .description(request.getDescription())
                .status(ServerStatus.UNKNOWN)
                .createdAt(now)
                .updatedAt(now)
                .build();

        serverMapper.insert(entity);

        return toVO(entity);
    }

    @Override
    public ServerVO update(SessionUser actor, Long id, ServerUpdateRequest request) {

        ServerEntity entity = requireAccessibleEntity(actor, id);

        entity.setName(request.getName());
        entity.setHost(request.getHost());
        entity.setPort(request.getPort());
        entity.setOs(request.getOs());
        entity.setDescription(request.getDescription());
        entity.setUpdatedAt(LocalDateTime.now());

        serverMapper.update(entity);

        return toVO(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public ServerVO getById(SessionUser actor, Long id) {

        return toVO(requireAccessibleEntity(actor, id));
    }

    @Override
    @Transactional(readOnly = true)
    public List<ServerVO> list(SessionUser actor) {

        if (isGlobalViewer(actor)) {
            audit.record(actor, "PLATFORM_INFRA_VIEW", "server:list", "SUCCESS", null);
            return serverMapper.selectAll()
                    .stream()
                    .map(this::toVO)
                    .toList();
        }
        return serverMapper.selectByOwner(actor.id())
                .stream()
                .map(this::toVO)
                .toList();
    }

    @Override
    public void delete(SessionUser actor, Long id) {

        requireAccessibleEntity(actor, id);
        serverMapper.deleteById(id);
    }

    @Override
    @Transactional(readOnly = true)
    public void requireAccessible(SessionUser actor, Long id) {

        requireAccessibleEntity(actor, id);
    }

    private ServerEntity requireAccessibleEntity(SessionUser actor, Long id) {

        ServerEntity entity = serverMapper.selectById(id);
        // 统一返回"不存在"，避免向非属主泄露资产是否存在。
        if (entity == null) {
            throw new BusinessException(404, "服务器不存在");
        }
        if (Objects.equals(entity.getOwnerId(), actor.id())) {
            return entity;
        }
        if (isGlobalViewer(actor)) {
            audit.record(actor, "PLATFORM_INFRA_VIEW", "server:" + id, "SUCCESS", null);
            return entity;
        }
        throw new BusinessException(404, "服务器不存在");
    }

    private boolean isGlobalViewer(SessionUser actor) {
        return accounts.hasPlatformCapability(actor, GLOBAL_VIEW_CAPABILITY);
    }

    private ServerVO toVO(ServerEntity entity) {

        return ServerVO.builder()
                .id(entity.getId())
                .name(entity.getName())
                .host(entity.getHost())
                .port(entity.getPort())
                .os(entity.getOs())
                .status(entity.getStatus())
                .description(entity.getDescription())
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .build();
    }
}
