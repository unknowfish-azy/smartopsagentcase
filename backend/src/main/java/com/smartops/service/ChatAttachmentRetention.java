package com.smartops.service;

import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.beans.factory.annotation.Value;

@Service
@EnableScheduling
public class ChatAttachmentRetention {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final boolean enabled;
    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(ChatAttachmentRetention.class);

    public ChatAttachmentRetention(JdbcTemplate jdbc, PlatformTransactionManager manager,
                                   @Value("${smartops.attachments.cleanup-enabled:true}") boolean enabled) {
        this.jdbc = jdbc;
        this.enabled = enabled;
        this.transactions = new TransactionTemplate(manager);
        this.transactions.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
    }

    @Scheduled(fixedDelayString = "${smartops.attachments.cleanup-interval-ms:3600000}", initialDelay = 60000)
    public void scheduledSweep() {
        if (!enabled) return;
        try { sweep(); }
        catch (RuntimeException failure) { log.warn("Chat attachment retention failed; check database connectivity and V007 migration", failure); }
    }

    public int sweep() {
        long cutoff = System.currentTimeMillis() - 86_400_000L;
        var scopes = jdbc.queryForList("SELECT DISTINCT c.scope_key FROM chat_attachment a JOIN chat_conversation c ON c.id=a.conversation_id WHERE a.message_id IS NULL AND a.created_at<? LIMIT 100", String.class, cutoff);
        int removed = 0;
        for (String scope : scopes) {
            Integer count = transactions.execute(status -> {
                if (scope.startsWith("user:")) jdbc.queryForList("SELECT id FROM app_user WHERE id=? FOR UPDATE", Long.class, Long.parseLong(scope.substring(5)));
                else if (scope.startsWith("team:")) jdbc.queryForList("SELECT id FROM team_workspace WHERE id=? FOR UPDATE", Long.class, Long.parseLong(scope.substring(5)));
                else throw new IllegalStateException("Invalid attachment scope");
                return jdbc.update("DELETE FROM chat_attachment WHERE message_id IS NULL AND created_at<? AND conversation_id IN (SELECT id FROM chat_conversation WHERE scope_key=?)", cutoff, scope);
            });
            removed += count == null ? 0 : count;
        }
        return removed;
    }
}
