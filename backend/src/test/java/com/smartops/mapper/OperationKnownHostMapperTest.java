package com.smartops.mapper;

import com.smartops.entity.OperationKnownHost;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;

@MybatisTest
class OperationKnownHostMapperTest {

    @Autowired
    private OperationKnownHostMapper mapper;

    @Test
    void replaces_every_persisted_host_key_field_for_the_same_session_host_and_port() {
        mapper.insert(knownHost("ssh-ed25519", "SHA256:first", "first-public-key"));
        mapper.update(knownHost("ecdsa-sha2-nistp256", "SHA256:replacement", "replacement-public-key"));

        OperationKnownHost saved = mapper.findBySessionHostAndPort(41L, "ops.example.test", 2222);

        assertThat(saved).isNotNull();
        assertThat(saved.getAlgorithm()).isEqualTo("ecdsa-sha2-nistp256");
        assertThat(saved.getFingerprint()).isEqualTo("SHA256:replacement");
        assertThat(saved.getPublicKey()).isEqualTo("replacement-public-key");
    }

    private static OperationKnownHost knownHost(String algorithm, String fingerprint, String publicKey) {
        OperationKnownHost knownHost = new OperationKnownHost();
        knownHost.setSessionId(41L);
        knownHost.setHost("ops.example.test");
        knownHost.setPort(2222);
        knownHost.setAlgorithm(algorithm);
        knownHost.setFingerprint(fingerprint);
        knownHost.setPublicKey(publicKey);
        return knownHost;
    }
}
