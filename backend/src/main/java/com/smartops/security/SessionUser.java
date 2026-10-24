package com.smartops.security;

import java.io.Serializable;
import java.security.Principal;

public record SessionUser(Long id, String username, String role, String portal, boolean mustChangePassword, long authVersion) implements Principal, Serializable {
    public SessionUser(Long id, String username, String role) {
        this(id, username, role, "admin".equals(role) ? "admin" : "user", false, 0);
    }
    @Override public String getName() { return username; }
}
