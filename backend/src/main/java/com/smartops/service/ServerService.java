package com.smartops.service;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.vo.ServerVO;

import java.util.List;

public interface ServerService {

    ServerVO create(ServerCreateRequest request);

    ServerVO update(Long id, ServerUpdateRequest request);

    ServerVO getById(Long id);

    List<ServerVO> list();

    void delete(Long id);
}