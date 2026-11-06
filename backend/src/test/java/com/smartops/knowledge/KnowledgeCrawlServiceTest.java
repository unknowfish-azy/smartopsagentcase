package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.service.PersonalKnowledgeService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.net.ConnectException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

class KnowledgeCrawlServiceTest {

    private final SessionUser actor = new SessionUser(1L, "alice", "user");
    private final PersonalKnowledgeService knowledge = mock(PersonalKnowledgeService.class);

    @Test
    void createSourceRejectsTrailingDotLocalhostBeforePersisting() {
        KnowledgeCrawlService service = new KnowledgeCrawlService(new JdbcTemplate(), knowledge);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.createSource(actor, 1L, "docs", "http://localhost.:18080/", 10, 1));

        assertEquals(400, failure.getCode());
        assertEquals("KNOWLEDGE_CRAWL_URL_BLOCKED", failure.getMessage());
    }

    @Test
    void createSourceRejectsIpv4MappedLoopback() {
        KnowledgeCrawlService service = new KnowledgeCrawlService(new JdbcTemplate(), knowledge);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.createSource(actor, 1L, "docs", "http://[::ffff:127.0.0.1]:18080/", 10, 1));

        assertEquals("KNOWLEDGE_CRAWL_URL_BLOCKED", failure.getMessage());
    }

    /** TM-31：last_error 只落错误码，原始异常消息（可能含内部主机/端口）不落库。 */
    @Test
    void errorCodeNeverCarriesInternalHostOrPort() {
        String code = KnowledgeCrawlService.errorCode(
                new ConnectException("Connection refused: internal-db:3306"));

        assertFalse(code.contains("internal-db"));
        assertFalse(code.contains("3306"));
        assertEquals("NETWORK_ERROR:ConnectException", code);
        assertEquals("OUTBOUND_BLOCKED", KnowledgeCrawlService.errorCode(
                new java.io.IOException("目标地址不允许访问（NON_PUBLIC_ADDRESS）")));
    }

    /** TM-31：URL 的 query 可能携带 token，入库只保留去 query 的地址。 */
    @Test
    void storedCrawlUrlDropsQueryAndFragment() {
        assertEquals("https://docs.example.com/guide",
                KnowledgeCrawlService.stripQuery("https://docs.example.com/guide?token=abc123#section"));
    }

    @Test
    void runRejectsAStoredSeedThatIsNoLongerPublicBeforeAnyRequest() {
        KnowledgeCrawlService.CrawlSource stored = new KnowledgeCrawlService.CrawlSource(
                9L, 1L, "legacy", "http://169.254.169.254/latest/meta-data/", 10, 1,
                null, null, null, null);
        JdbcTemplate jdbc = new JdbcTemplate() {
            @Override
            @SuppressWarnings("unchecked")
            public <T> List<T> query(String sql, RowMapper<T> rowMapper, Object... args) {
                return (List<T>) List.of(stored);
            }
        };
        KnowledgeCrawlService service = new KnowledgeCrawlService(jdbc, knowledge);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.run(actor, 9L));

        assertEquals(400, failure.getCode());
        assertEquals("KNOWLEDGE_CRAWL_URL_BLOCKED", failure.getMessage());
    }
}
