package com.smartops.operations;

import com.smartops.entity.OperationKnownHost;
import com.smartops.mapper.OperationKnownHostMapper;
import org.springframework.stereotype.Component;

import java.util.Optional;

@Component
public class MyBatisKnownHostStore implements KnownHostStore {
    private final OperationKnownHostMapper mapper;

    public MyBatisKnownHostStore(OperationKnownHostMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Optional<OperationKnownHost> find(Long sessionId, String host, int port) {
        return Optional.ofNullable(mapper.findBySessionHostAndPort(sessionId, host, port));
    }

    @Override
    public void save(OperationKnownHost knownHost) {
        if (mapper.update(knownHost) == 0) {
            mapper.insert(knownHost);
        }
    }
}
