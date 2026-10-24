package com.smartops.operations;

import com.smartops.entity.OperationKnownHost;
import com.smartops.mapper.OperationKnownHostMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MyBatisKnownHostStoreTest {

    @Test
    void inserts_when_no_known_host_exists_for_the_session_host_and_port() {
        RecordingMapper mapper = new RecordingMapper(0);

        new MyBatisKnownHostStore(mapper).save(knownHost());

        assertThat(mapper.updateCalls).isEqualTo(1);
        assertThat(mapper.insertCalls).isEqualTo(1);
    }

    @Test
    void updates_when_a_known_host_already_exists_for_the_session_host_and_port() {
        RecordingMapper mapper = new RecordingMapper(1);

        new MyBatisKnownHostStore(mapper).save(knownHost());

        assertThat(mapper.updateCalls).isEqualTo(1);
        assertThat(mapper.insertCalls).isZero();
    }

    private static OperationKnownHost knownHost() {
        OperationKnownHost knownHost = new OperationKnownHost();
        knownHost.setSessionId(41L);
        knownHost.setHost("ops.example.test");
        knownHost.setPort(2222);
        knownHost.setAlgorithm("ssh-ed25519");
        knownHost.setFingerprint("SHA256:trusted");
        knownHost.setPublicKey("AAAAC3NzaC1lZDI1NTE5AAAAITest");
        return knownHost;
    }

    private static final class RecordingMapper implements OperationKnownHostMapper {
        private final int updateResult;
        private int updateCalls;
        private int insertCalls;

        private RecordingMapper(int updateResult) {
            this.updateResult = updateResult;
        }

        @Override
        public OperationKnownHost findBySessionHostAndPort(Long sessionId, String host, int port) {
            return null;
        }

        @Override
        public int insert(OperationKnownHost knownHost) {
            insertCalls++;
            return 1;
        }

        @Override
        public int update(OperationKnownHost knownHost) {
            updateCalls++;
            return updateResult;
        }
    }
}
