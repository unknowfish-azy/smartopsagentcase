package com.smartops.security;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SessionRevocationService {
    private final UserAccountService accounts;
    private final AccountSessionRegistry sessions;
    private final SecurityAuditService audit;

    public SessionRevocationService(UserAccountService accounts, AccountSessionRegistry sessions, SecurityAuditService audit) {
        this.accounts = accounts; this.sessions = sessions; this.audit = audit;
    }

    @Transactional
    public void revoke(SessionUser actor, String id, boolean management) {
        accounts.requireMutationAuthority(actor, management);
        Long owner = management ? null : actor.id();
        sessions.requireActive(id, owner);
        audit.record(actor, "REVOKE_SESSION", id, "SUCCESS");
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() { sessions.revokeIfPresent(id, owner); }
        });
    }
}
