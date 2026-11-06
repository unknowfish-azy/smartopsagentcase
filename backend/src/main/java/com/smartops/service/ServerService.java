package com.smartops.service;

import com.smartops.dto.ServerCreateRequest;
import com.smartops.dto.ServerUpdateRequest;
import com.smartops.security.SessionUser;
import com.smartops.vo.ServerVO;

import java.util.List;

public interface ServerService {

    ServerVO create(SessionUser actor, ServerCreateRequest request);

    ServerVO update(SessionUser actor, Long id, ServerUpdateRequest request);

    ServerVO getById(SessionUser actor, Long id);

    List<ServerVO> list(SessionUser actor);

    void delete(SessionUser actor, Long id);

    /** SEC-08：供指标等子资源在访问前校验资产归属。 */
    void requireAccessible(SessionUser actor, Long id);
}
