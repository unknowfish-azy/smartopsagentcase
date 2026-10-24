package com.smartops.service.impl;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ServerMapper;
import com.smartops.module.server.ServerStatus;
import com.smartops.service.ServerService;
import com.smartops.vo.ServerVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional
public class ServerServiceImpl implements ServerService {

    private final ServerMapper serverMapper;

    @Override
    public ServerVO create(ServerCreateRequest request) {

        if (serverMapper.countByName(request.getName()) > 0) {
            throw new BusinessException("服务器名称已经存在");
        }

        LocalDateTime now = LocalDateTime.now();

        ServerEntity entity = ServerEntity.builder()
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
    public ServerVO update(Long id, ServerUpdateRequest request) {

        ServerEntity entity = serverMapper.selectById(id);
        if (entity == null) {
            throw new BusinessException("服务器不存在");
        }

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
    public ServerVO getById(Long id) {

        ServerEntity entity = serverMapper.selectById(id);
        if (entity == null) {
            throw new BusinessException("服务器不存在");
        }

        return toVO(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public List<ServerVO> list() {

        return serverMapper.selectAll()
                .stream()
                .map(this::toVO)
                .toList();
    }

    @Override
    public void delete(Long id) {

        if (serverMapper.selectById(id) == null) {
            throw new BusinessException("服务器不存在");
        }

        serverMapper.deleteById(id);
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
